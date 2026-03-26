"""
Unit tests for agent/db_manager.py
Covers:
  - Existing tables (_master_catalog, _pending_actions, protocols)
  - New tables: script_inventory, plans, plan_steps, dev_logs
  - Row versioning (add_data, update_data)
  - HITL pending actions (propose, execute, reject)
  - Script inventory CRUD
  - Plan / plan_step lifecycle
  - Dev log iteration recording

All tests run against a fresh in-memory SQLite DB (tmp_path fixture).
No Redis, no Gemini, no external services required.
"""

import os
import sys
import json
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agent.db_manager import DBManager


# ── Fixture ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path):
    """Returns a fresh DBManager backed by a temp SQLite file."""
    return DBManager(db_path=str(tmp_path / "test.db"))


# ════════════════════════════════════════════════════════════════════════════
#  Schema — all tables must exist after _init_db
# ════════════════════════════════════════════════════════════════════════════

class TestSchema:
    REQUIRED_TABLES = [
        "_master_catalog",
        "_pending_actions",
        "daily_summaries",
        "tasks",
        "protocols",
        "processed_files",
        "script_inventory",
        "plans",
        "plan_steps",
        "dev_logs",
    ]

    def test_all_tables_created(self, db):
        tables = db.list_all_tables()
        for t in self.REQUIRED_TABLES:
            assert t in tables, f"Missing table: {t}"

    def test_db_is_idempotent(self, tmp_path):
        """Calling DBManager twice on the same file must not raise."""
        path = str(tmp_path / "idem.db")
        DBManager(db_path=path)
        DBManager(db_path=path)  # should not crash


# ════════════════════════════════════════════════════════════════════════════
#  Master Catalog & HITL
# ════════════════════════════════════════════════════════════════════════════

class TestMasterCatalog:
    def test_propose_and_approve_table_creation(self, db):
        action_id = db.propose_table_creation(
            table_name="contacts",
            description="Address book",
            columns={"name": "TEXT", "email": "TEXT"},
        )
        assert action_id

        # Check pending
        action = db.get_pending_action(action_id)
        assert action["status"] == "pending"
        assert action["payload"]["table_name"] == "contacts"

        # Approve
        ok = db.execute_action(action_id, approved=True)
        assert ok

        # Table must exist now
        tables = db.list_all_tables()
        assert "contacts" in tables

        # Catalog must have entry
        catalog = db.get_catalog()
        names = [r["table_name"] for r in catalog]
        assert "contacts" in names

    def test_reject_table_creation(self, db):
        action_id = db.propose_table_creation(
            table_name="rejected_table",
            description="Should not be created",
            columns={"col": "TEXT"},
        )
        ok = db.execute_action(action_id, approved=False)
        assert ok

        tables = db.list_all_tables()
        assert "rejected_table" not in tables

        action = db.get_pending_action(action_id)
        assert action["status"] == "rejected"

    def test_double_approve_is_safe(self, db):
        """Approving the same action twice must return False on second call."""
        action_id = db.propose_table_creation("t1", "x", {"c": "TEXT"})
        db.execute_action(action_id, approved=True)
        result = db.execute_action(action_id, approved=True)
        assert result is False

    def test_nonexistent_action_returns_false(self, db):
        assert db.execute_action("00000000-0000-0000-0000-000000000000") is False

    def test_propose_master_update(self, db):
        # First create a table so the catalog has an entry
        action_id = db.propose_table_creation("upd_table", "desc", {"c": "TEXT"})
        db.execute_action(action_id, approved=True)

        upd_id = db.propose_master_update("upd_table", {"status": "invalid"})
        assert upd_id
        ok = db.execute_action(upd_id, approved=True)
        assert ok

        catalog = {r["table_name"]: r for r in db.get_catalog()}
        assert catalog["upd_table"]["status"] == "invalid"


# ════════════════════════════════════════════════════════════════════════════
#  Row Versioning (add_data / update_data)
# ════════════════════════════════════════════════════════════════════════════

class TestRowVersioning:
    @pytest.fixture
    def versioned_table(self, db):
        """Creates a 'notes' table with versioning enabled."""
        action_id = db.propose_table_creation(
            table_name="notes",
            description="Test notes",
            columns={"title": "TEXT", "body": "TEXT"},
        )
        db.execute_action(action_id, approved=True)
        return db

    def test_add_data_creates_version_1(self, versioned_table):
        db = versioned_table
        row_id = db.add_data("notes", {"title": "Hello", "body": "World"})
        rows = db.query(f"SELECT * FROM notes WHERE row_id='{row_id}'")
        assert len(rows) == 1
        assert rows[0]["version"] == 1
        assert rows[0]["status"] == "valid"
        assert rows[0]["title"] == "Hello"

    def test_update_data_increments_version(self, versioned_table):
        db = versioned_table
        row_id = db.add_data("notes", {"title": "v1", "body": "original"})
        db.update_data("notes", row_id, {"body": "updated"})

        rows = db.query(f"SELECT * FROM notes WHERE row_id='{row_id}' ORDER BY version")
        assert len(rows) == 2
        assert rows[0]["version"] == 1
        assert rows[0]["status"] == "invalid"
        assert rows[1]["version"] == 2
        assert rows[1]["status"] == "valid"
        assert rows[1]["body"] == "updated"
        assert rows[1]["title"] == "v1"          # unchanged field carried forward

    def test_update_nonexistent_row_raises(self, versioned_table):
        db = versioned_table
        with pytest.raises(ValueError):
            db.update_data("notes", "nonexistent-id", {"title": "x"})

    def test_multiple_updates_chain(self, versioned_table):
        db = versioned_table
        row_id = db.add_data("notes", {"title": "A", "body": "1"})
        db.update_data("notes", row_id, {"body": "2"})
        db.update_data("notes", row_id, {"body": "3"})

        rows = db.query(
            f"SELECT * FROM notes WHERE row_id='{row_id}' ORDER BY version"
        )
        assert len(rows) == 3
        assert rows[-1]["version"] == 3
        assert rows[-1]["body"] == "3"
        # Only the latest is valid
        valid_rows = [r for r in rows if r["status"] == "valid"]
        assert len(valid_rows) == 1
        assert valid_rows[0]["version"] == 3


# ════════════════════════════════════════════════════════════════════════════
#  Script Inventory
# ════════════════════════════════════════════════════════════════════════════

class TestScriptInventory:
    def test_register_and_retrieve_script(self, db):
        sid = db.register_script(
            name="email_fetcher",
            description="Fetches recent emails",
            file_path="agent/workers/email_fetcher.py",
            input_schema={"count": "int"},
        )
        assert sid

        scripts = db.get_active_scripts()
        names = [s["name"] for s in scripts]
        assert "email_fetcher" in names

    def test_find_script_by_name(self, db):
        db.register_script("my_script", "does stuff", "path/to/my_script.py")
        result = db.find_script_by_name("my_script")
        assert result is not None
        assert result["file_path"] == "path/to/my_script.py"

    def test_find_nonexistent_script_returns_none(self, db):
        result = db.find_script_by_name("ghost_script")
        assert result is None

    def test_register_script_upserts(self, db):
        """Re-registering the same name must update, not duplicate."""
        db.register_script("dup", "v1", "path/v1.py")
        db.register_script("dup", "v2", "path/v2.py")

        scripts = [s for s in db.get_active_scripts() if s["name"] == "dup"]
        assert len(scripts) == 1
        assert scripts[0]["file_path"] == "path/v2.py"
        assert scripts[0]["description"] == "v2"

    def test_input_schema_is_parsed(self, db):
        db.register_script("typed", "typed script", "p.py", input_schema={"n": "int", "s": "str"})
        result = db.find_script_by_name("typed")
        assert isinstance(result["input_schema"], dict)
        assert result["input_schema"]["n"] == "int"

    def test_empty_inventory_returns_empty_list(self, db):
        assert db.get_active_scripts() == []


# ════════════════════════════════════════════════════════════════════════════
#  Plans & Plan Steps
# ════════════════════════════════════════════════════════════════════════════

class TestPlans:
    def test_create_plan(self, db):
        plan_id = db.create_plan("Send me a daily email digest", assigned_model="gemini-flash")
        assert plan_id

        plans = db.list_plans()
        assert any(p["plan_id"] == plan_id for p in plans)

    def test_plan_default_status_is_pending(self, db):
        plan_id = db.create_plan("test goal")
        plans = {p["plan_id"]: p for p in db.list_plans()}
        assert plans[plan_id]["status"] == "pending"

    def test_update_plan_status(self, db):
        plan_id = db.create_plan("goal")
        db.update_plan_status(plan_id, "running", "Started execution")
        plan = db.get_plan_with_steps(plan_id)
        assert plan["status"] == "running"
        assert plan["output_summary"] == "Started execution"

    def test_list_plans_filter_by_status(self, db):
        p1 = db.create_plan("g1")
        p2 = db.create_plan("g2")
        db.update_plan_status(p1, "done")

        done = db.list_plans(status="done")
        pending = db.list_plans(status="pending")

        assert any(p["plan_id"] == p1 for p in done)
        assert any(p["plan_id"] == p2 for p in pending)

    def test_add_and_retrieve_plan_steps(self, db):
        plan_id = db.create_plan("multi-step goal")
        s1 = db.add_plan_step(plan_id, 0, "Fetch emails", assigned_layer="script_run")
        s2 = db.add_plan_step(plan_id, 1, "Summarise with LLM", assigned_layer="llm_call", assigned_model="gemini-flash")
        s3 = db.add_plan_step(plan_id, 2, "Send Telegram message", assigned_layer="script_run")

        plan = db.get_plan_with_steps(plan_id)
        steps = plan["steps"]

        assert len(steps) == 3
        assert steps[0]["description"] == "Fetch emails"
        assert steps[1]["assigned_model"] == "gemini-flash"
        assert steps[2]["step_index"] == 2

    def test_update_plan_step_status(self, db):
        plan_id = db.create_plan("g")
        step_id = db.add_plan_step(plan_id, 0, "Do something")

        db.update_plan_step_status(step_id, "done", "Completed successfully")

        plan = db.get_plan_with_steps(plan_id)
        step = plan["steps"][0]
        assert step["status"] == "done"
        assert step["output_summary"] == "Completed successfully"

    def test_get_plan_with_steps_returns_none_for_missing(self, db):
        result = db.get_plan_with_steps("00000000-0000-0000-0000-000000000000")
        assert result is None

    def test_steps_ordered_by_index(self, db):
        plan_id = db.create_plan("order test")
        db.add_plan_step(plan_id, 2, "C")
        db.add_plan_step(plan_id, 0, "A")
        db.add_plan_step(plan_id, 1, "B")

        plan = db.get_plan_with_steps(plan_id)
        descs = [s["description"] for s in plan["steps"]]
        assert descs == ["A", "B", "C"]


# ════════════════════════════════════════════════════════════════════════════
#  Dev Logs (Agent Self-Correction History)
# ════════════════════════════════════════════════════════════════════════════

class TestDevLogs:
    def test_log_single_iteration(self, db):
        plan_id = db.create_plan("build a script")
        step_id = db.add_plan_step(plan_id, 0, "Write script")

        log_id = db.log_dev_iteration(
            plan_step_id=step_id,
            branch_name="dev/kuro-abc123",
            iteration=1,
            code_written="def run(): pass",
            test_output="1 passed",
            error_summary="",
            status="success",
        )
        assert log_id

        logs = db.get_dev_logs(step_id)
        assert len(logs) == 1
        assert logs[0]["iteration"] == 1
        assert logs[0]["status"] == "success"
        assert logs[0]["branch_name"] == "dev/kuro-abc123"

    def test_log_multiple_iterations(self, db):
        plan_id = db.create_plan("iterative build")
        step_id = db.add_plan_step(plan_id, 0, "Write and fix")

        for i in range(1, 4):
            status = "success" if i == 3 else "in_progress"
            db.log_dev_iteration(
                plan_step_id=step_id,
                branch_name="dev/kuro-xyz",
                iteration=i,
                code_written=f"# attempt {i}",
                test_output=f"{'1 passed' if i == 3 else '1 failed'}",
                error_summary="" if i == 3 else f"AssertionError at iter {i}",
                status=status,
            )

        logs = db.get_dev_logs(step_id)
        assert len(logs) == 3
        # Must be returned in iteration order
        assert [l["iteration"] for l in logs] == [1, 2, 3]
        assert logs[-1]["status"] == "success"
        assert logs[0]["error_summary"] == "AssertionError at iter 1"

    def test_logs_empty_for_unknown_step(self, db):
        logs = db.get_dev_logs("00000000-0000-0000-0000-000000000000")
        assert logs == []

    def test_default_status_is_in_progress(self, db):
        plan_id = db.create_plan("g")
        step_id = db.add_plan_step(plan_id, 0, "s")
        log_id = db.log_dev_iteration(step_id, "branch", 1, "code", "output", "")

        logs = db.get_dev_logs(step_id)
        assert logs[0]["status"] == "in_progress"


# ════════════════════════════════════════════════════════════════════════════
#  Daily Summaries (existing feature — regression guard)
# ════════════════════════════════════════════════════════════════════════════

class TestDailySummaries:
    def test_store_and_retrieve(self, db):
        with db._get_conn() as conn:
            conn.execute(
                "INSERT INTO daily_summaries (day, summary) VALUES (?, ?)",
                ("2026-03-27", "A great day"),
            )
        with db._get_conn() as conn:
            row = conn.execute(
                "SELECT summary FROM daily_summaries WHERE day=?", ("2026-03-27",)
            ).fetchone()
        assert row["summary"] == "A great day"

    def test_upsert_updates_existing(self, db):
        with db._get_conn() as conn:
            conn.execute(
                """INSERT INTO daily_summaries (day, summary)
                   VALUES (?, ?)
                   ON CONFLICT(day) DO UPDATE SET summary=excluded.summary""",
                ("2026-03-27", "v1"),
            )
            conn.execute(
                """INSERT INTO daily_summaries (day, summary)
                   VALUES (?, ?)
                   ON CONFLICT(day) DO UPDATE SET summary=excluded.summary""",
                ("2026-03-27", "v2"),
            )
        with db._get_conn() as conn:
            row = conn.execute(
                "SELECT summary FROM daily_summaries WHERE day=?", ("2026-03-27",)
            ).fetchone()
        assert row["summary"] == "v2"


# ════════════════════════════════════════════════════════════════════════════
#  Query Safety Guard
# ════════════════════════════════════════════════════════════════════════════

class TestQuerySafety:
    def test_select_query_works(self, db):
        results = db.query("SELECT name FROM sqlite_master WHERE type='table'")
        assert isinstance(results, list)

    def test_raw_execute_ddl(self, db):
        result = db.execute_raw_query(
            "CREATE TABLE IF NOT EXISTS raw_test (id INTEGER PRIMARY KEY)"
        )
        assert result["success"] is True

    def test_raw_execute_bad_sql_returns_error(self, db):
        result = db.execute_raw_query("THIS IS NOT SQL")
        assert result["success"] is False
        assert "error" in result
