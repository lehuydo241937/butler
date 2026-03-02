import sqlite3
import json
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

class DBManager:
    """Manages the SQL database for the Butler agent."""

    def __init__(self, db_path: str = "butler_sql.db"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            # Master catalog tracks all data tables
            conn.execute("""
                CREATE TABLE IF NOT EXISTS _master_catalog (
                    table_name TEXT PRIMARY KEY,
                    description TEXT,
                    schema_json TEXT,
                    status TEXT DEFAULT 'valid', -- 'valid' or 'invalid'
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Pending actions for HITL
            conn.execute("""
                CREATE TABLE IF NOT EXISTS _pending_actions (
                    action_id TEXT PRIMARY KEY,
                    action_type TEXT, -- 'create_table', 'update_master'
                    payload TEXT,
                    status TEXT DEFAULT 'pending', -- 'pending', 'approved', 'rejected'
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Daily summaries for historical context
            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_summaries (
                    day TEXT PRIMARY KEY, -- YYYY-MM-DD
                    summary TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Background tasks table (legacy single-step tasks)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    task_description TEXT NOT NULL,
                    cron_expression TEXT NOT NULL,
                    last_run TIMESTAMP,
                    next_run TIMESTAMP,
                    target_chat_id INTEGER,
                    status TEXT DEFAULT 'active', -- 'active', 'paused'
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Protocols table — multi-step execution pipelines
            conn.execute("""
                CREATE TABLE IF NOT EXISTS protocols (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    name            TEXT UNIQUE NOT NULL,
                    description     TEXT,
                    steps           TEXT NOT NULL,       -- JSON array of step definitions
                    cron_expression TEXT,
                    target_chat_id  INTEGER,
                    status          TEXT DEFAULT 'active', -- 'active' | 'paused'
                    last_run        TIMESTAMP,
                    next_run        TIMESTAMP,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # ── Processed Files tracking ─────────────────────────────────────────
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_files (
                    filename TEXT PRIMARY KEY,
                    processed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    source TEXT
                )
            """)
            conn.commit()

    # ── Master Catalog Operations ────────────────────────────────────────

    def get_catalog(self) -> List[Dict[str, Any]]:
        """Returns all entries in the master catalog."""
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM _master_catalog")
            return [dict(row) for row in cursor.fetchall()]

    def propose_table_creation(self, table_name: str, description: str, columns: Dict[str, str]) -> str:
        """Stages a new table for creation. Returns an action_id."""
        action_id = str(uuid.uuid4())
        payload = json.dumps({
            "table_name": table_name,
            "description": description,
            "columns": columns
        })
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO _pending_actions (action_id, action_type, payload) VALUES (?, ?, ?)",
                (action_id, "create_table", payload)
            )
        return action_id

    def propose_master_update(self, table_name: str, updates: Dict[str, Any]) -> str:
        """Stages an update to the master catalog. Returns an action_id."""
        action_id = str(uuid.uuid4())
        payload = json.dumps({
            "table_name": table_name,
            "updates": updates
        })
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO _pending_actions (action_id, action_type, payload) VALUES (?, ?, ?)",
                (action_id, "update_master", payload)
            )
        return action_id

    def get_pending_action(self, action_id: str) -> Optional[Dict[str, Any]]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM _pending_actions WHERE action_id = ?", (action_id,)).fetchone()
            if row:
                res = dict(row)
                res["payload"] = json.loads(res["payload"])
                return res
        return None

    def execute_action(self, action_id: str, approved: bool = True):
        """Executes or rejects a pending action."""
        action = self.get_pending_action(action_id)
        if not action or action["status"] != "pending":
            return False

        if not approved:
            with self._get_conn() as conn:
                conn.execute("UPDATE _pending_actions SET status = 'rejected' WHERE action_id = ?", (action_id,))
            return True

        # Process approval
        try:
            if action["action_type"] == "create_table":
                self._execute_create_table(action["payload"])
            elif action["action_type"] == "update_master":
                self._execute_update_master(action["payload"])
            
            with self._get_conn() as conn:
                conn.execute("UPDATE _pending_actions SET status = 'approved' WHERE action_id = ?", (action_id,))
            return True
        except Exception as e:
            print(f"Error executing action {action_id}: {e}")
            return False

    def _execute_create_table(self, payload: Dict[str, Any]):
        table_name = payload["table_name"]
        columns = payload["columns"]
        description = payload["description"]

        # Build column definitions
        # Every table has: row_id (PK), version (INT), status (valid/invalid), created_at
        col_defs = ["row_id TEXT", "version INTEGER", "status TEXT DEFAULT 'valid'", "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"]
        for col_name, col_type in columns.items():
            # Sanitize col_type: remove PRIMARY KEY if present to avoid conflict with composite PK
            sanitized_type = col_type.replace("PRIMARY KEY", "").replace("primary key", "").strip()
            col_defs.append(f"{col_name} {sanitized_type}")

        sql = f"CREATE TABLE {table_name} ({', '.join(col_defs)}, PRIMARY KEY (row_id, version))"
        
        with self._get_conn() as conn:
            conn.execute(sql)
            # Add to catalog
            conn.execute(
                "INSERT INTO _master_catalog (table_name, description, schema_json) VALUES (?, ?, ?)",
                (table_name, description, json.dumps(columns))
            )

    def _execute_update_master(self, payload: Dict[str, Any]):
        table_name = payload["table_name"]
        updates = payload["updates"]
        
        set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
        params = list(updates.values()) + [table_name]
        
        with self._get_conn() as conn:
            conn.execute(f"UPDATE _master_catalog SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE table_name = ?", params)

    # ── Data Operations ──────────────────────────────────────────────────

    def add_data(self, table_name: str, data: Dict[str, Any]):
        """Adds a new row of data. Sets version=1 and status='valid'."""
        row_id = str(uuid.uuid4())
        cols = ["row_id", "version", "status"] + list(data.keys())
        placeholders = ["?", "?", "?"] + (["?"] * len(data))
        values = [row_id, 1, "valid"] + list(data.values())

        with self._get_conn() as conn:
            conn.execute(
                f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({', '.join(placeholders)})",
                values
            )
        return row_id

    def update_data(self, table_name: str, row_id: str, new_data: Dict[str, Any]):
        """
        Updates an existing row by creating a new version.
        Marks the old version as 'invalid'.
        """
        with self._get_conn() as conn:
            # Get latest version
            row = conn.execute(
                f"SELECT MAX(version) as max_v FROM {table_name} WHERE row_id = ?", 
                (row_id,)
            ).fetchone()
            
            if not row or row["max_v"] is None:
                raise ValueError(f"Row {row_id} not found in {table_name}")
            
            latest_version = row["max_v"]

            # Mark old version as invalid
            conn.execute(
                f"UPDATE {table_name} SET status = 'invalid' WHERE row_id = ? AND version = ?",
                (row_id, latest_version)
            )

            # Create new version
            # First, fetch the existing data from the latest version to carry forward unchanged fields?
            # Or assume new_data is complete? Let's carry forward to be safe if desired, 
            # but usually 'update' provides the delta or the whole thing.
            # Requirement: "A row is invalid to use if the data has a newer version"
            
            full_row = conn.execute(
                f"SELECT * FROM {table_name} WHERE row_id = ? AND version = ?",
                (row_id, latest_version)
            ).fetchone()
            
            data_to_insert = dict(full_row)
            # Remove system cols to avoid overwriting or confusion
            for k in ["row_id", "version", "status", "created_at"]:
                data_to_insert.pop(k, None)
            
            # Update with new data
            data_to_insert.update(new_data)

            new_version = latest_version + 1
            cols = ["row_id", "version", "status"] + list(data_to_insert.keys())
            placeholders = ["?", "?", "?"] + (["?"] * len(data_to_insert))
            values = [row_id, new_version, "valid"] + list(data_to_insert.values())

            conn.execute(
                f"INSERT INTO {table_name} ({', '.join(cols)}) VALUES ({', '.join(placeholders)})",
                values
            )
        return row_id

    def query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Executes a SELECT query."""
        with self._get_conn() as conn:
            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]

    def get_table_schema(self, table_name: str) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            cursor = conn.execute(f"PRAGMA table_info({table_name})")
            return [dict(row) for row in cursor.fetchall()]

    def execute_raw_query(self, sql: str, params: tuple = ()) -> Dict[str, Any]:
        """Executes any SQL query (including DDL/DML) and returns results or error."""
        try:
            with self._get_conn() as conn:
                cursor = conn.execute(sql, params)
                if sql.strip().lower().startswith("select") or sql.strip().lower().startswith("pragma"):
                    return {"success": True, "data": [dict(row) for row in cursor.fetchall()]}
                else:
                    conn.commit()
                    return {"success": True, "rows_affected": conn.total_changes}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_all_tables(self) -> List[str]:
        """Returns a list of all user-defined table names in the database."""
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            return [row["name"] for row in cursor.fetchall()]

    # ── Background Task Operations ────────────────────────────────────────

    def add_background_task(self, name: str, description: str, cron: str, chat_id: int):
        """Adds a new background task."""
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO tasks (name, task_description, cron_expression, target_chat_id) VALUES (?, ?, ?, ?)",
                (name, description, cron, chat_id)
            )

    def get_active_tasks(self) -> List[Dict[str, Any]]:
        """Returns all active tasks."""
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM tasks WHERE status = 'active'")
            return [dict(row) for row in cursor.fetchall()]

    def update_task_run_times(self, task_id: int, last_run: datetime, next_run: datetime):
        """Updates the run times for a task."""
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE tasks SET last_run = ?, next_run = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (last_run.isoformat(), next_run.isoformat(), task_id)
            )

    # ── Protocol Operations ─────────────────────────────────────────────────────

    def add_protocol(
        self,
        name: str,
        description: str,
        steps: list,
        cron_expression: str,
        chat_id: int,
    ) -> int:
        """Inserts a new protocol. Returns its id."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                """
                INSERT INTO protocols (name, description, steps, cron_expression, target_chat_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, description, json.dumps(steps), cron_expression, chat_id),
            )
            return cursor.lastrowid

    def get_active_protocols(self) -> List[Dict[str, Any]]:
        """Returns all active protocols, with steps parsed from JSON."""
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM protocols WHERE status = 'active'")
            rows = [dict(r) for r in cursor.fetchall()]
        for row in rows:
            row["steps"] = json.loads(row["steps"])
        return rows

    def get_protocol_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Returns a single protocol by name, or None."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM protocols WHERE name = ?", (name,)
            ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["steps"] = json.loads(result["steps"])
        return result

    def update_protocol_run_times(
        self, protocol_id: int, last_run: datetime, next_run: datetime
    ):
        """Updates last_run / next_run after a protocol execution."""
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE protocols SET last_run = ?, next_run = ? WHERE id = ?",
                (last_run.isoformat(), next_run.isoformat(), protocol_id),
            )

    def list_protocols(self) -> List[Dict[str, Any]]:
        """Returns name, description, cron, status, last_run for all protocols."""
        with self._get_conn() as conn:
            cursor = conn.execute(
                "SELECT id, name, description, cron_expression, status, last_run, next_run FROM protocols"
            )
            return [dict(r) for r in cursor.fetchall()]
