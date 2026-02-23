import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from langfuse import observe

from chat_history import RedisChatHistory
from secrets_manager.redis_secrets import RedisSecretsManager
from agent.db_manager import DBManager

load_dotenv()

# ── Default system prompt ───────────────────────────────────────────────
DEFAULT_SYSTEM_PROMPT = (
    "You are Kuro, a helpful and friendly AI assistant. "
    "You have access to a SQL database via tools. "
    "Use these tools to store, retrieve, and manage structured data. "
    "When asked to create a table, DO NOT include 'PRIMARY KEY' in your column definitions, as the system automatically uses a composite (row_id, version) primary key for versioning. "
    "Row versioning is handled automatically when you use the update tool. "
    "Always check the database metadata first to understand available tables. "
    "Be concise but thorough."
)


class ButlerAgent:
    """Conversational agent with persistent Redis memory and SQL support."""

    def __init__(
        self,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        history: Optional[RedisChatHistory] = None,
        secrets: Optional[RedisSecretsManager] = None,
    ):
        """
        Initialise the agent.
        """
        # ── Redis components ────────────────────────────────────────────
        self.history = history or RedisChatHistory()
        self.secrets = secrets or RedisSecretsManager()
        self.db = DBManager()

        if not self.history.ping():
            raise ConnectionError(
                "Cannot reach Redis — is the container running? "
                "(docker compose up -d)"
            )

        # ── Session ─────────────────────────────────────────────────────
        if session_id:
            self.session_id = session_id
        else:
            self.session_id = self.history.create_session(title="New conversation")

        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT

        # ── Gemini client ───────────────────────────────────────────────
        api_key = self.secrets.get_secret("gemini")
        if not api_key:
            api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY not found in Redis secrets or environment variables."
            )

        # ── Langfuse Configuration ──────────────────────────────────────
        self.configure_langfuse(self.secrets)

        self.client = genai.Client(api_key=api_key)
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")

        # ── Tool Definitions ────────────────────────────────────────────
        self.tools = [
            self.get_database_metadata,
            self.query_database,
            self.propose_new_table,
            self.add_data_to_table,
            self.update_row_data,
            self.propose_table_update,
            self.store_daily_summary,
            self.get_daily_summary,
            self.list_pending_actions,
            self.confirm_action,
            self.schedule_background_task
        ]

    @staticmethod
    def configure_langfuse(secrets: RedisSecretsManager):
        """Globally configure Langfuse environment variables."""
        lf_pk = secrets.get_secret("langfuse_public_key")
        lf_sk = secrets.get_secret("langfuse_secret_key")
        lf_host = secrets.get_secret("langfuse_host") or "https://cloud.langfuse.com"
        
        if lf_pk and lf_sk:
            os.environ["LANGFUSE_PUBLIC_KEY"] = lf_pk
            os.environ["LANGFUSE_SECRET_KEY"] = lf_sk
            os.environ["LANGFUSE_HOST"] = lf_host

    # ── Database Tools ──────────────────────────────────────────────────

    @observe()
    def get_database_metadata(self) -> List[Dict[str, Any]]:
        """Returns the list of tables available in the database and their schemas."""
        return self.db.get_catalog()

    @observe()
    def query_database(self, sql: str) -> List[Dict[str, Any]]:
        """Executes a SELECT SQL query on the database. Use this to retrieve data."""
        if not sql.strip().lower().startswith("select"):
            return [{"error": "Only SELECT queries are allowed for safety."}]
        return self.db.query(sql)

    @observe()
    def propose_new_table(self, table_name: str, description: str, columns: Dict[str, str]) -> str:
        """
        Stages a request to create a new table. 
        Columns should be a dictionary of {column_name: sqlite_type} (e.g. {"name": "TEXT", "age": "INTEGER"}).
        This action requires manual user approval.
        """
        action_id = self.db.propose_table_creation(table_name, description, columns)
        return f"HITL_PROPOSAL:table_creation:{action_id}:Table '{table_name}' creation proposed. Please approve/reject."

    @observe()
    def add_data_to_table(self, table_name: str, data: Dict[str, Any]) -> str:
        """Adds a new row of data to an existing table."""
        row_id = self.db.add_data(table_name, data)
        return f"Data added to '{table_name}'. Row ID: {row_id}"

    @observe()
    def update_row_data(self, table_name: str, row_id: str, new_data: Dict[str, Any]) -> str:
        """Updates an existing row by creating a new version and marking the old one as invalid."""
        new_row_id = self.db.update_data(table_name, row_id, new_data)
        return f"Data updated in '{table_name}'. New version created for Row ID: {new_row_id}"

    def propose_table_update(self, table_name: str, updates: Dict[str, Any]) -> str:
        """
        Stages an update to the table's metadata in the master catalog (e.g., {"status": "invalid"}).
        This action requires manual user approval.
        """
        action_id = self.db.propose_master_update(table_name, updates)
        return f"HITL_PROPOSAL:master_update:{action_id}:Update to master catalog for '{table_name}' proposed. Please approve/reject."

    def store_daily_summary(self, day: str, summary: str) -> str:
        """
        Stores or updates a summary for a specific day.
        'day' should be in YYYY-MM-DD format.
        """
        with self.db._get_conn() as conn:
            conn.execute("""
                INSERT INTO daily_summaries (day, summary, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(day) DO UPDATE SET
                    summary=excluded.summary,
                    updated_at=CURRENT_TIMESTAMP
            """, (day, summary))
        return f"Summary for {day} stored successfully."

    def get_daily_summary(self, day: str) -> str:
        """
        Retrieves the summary for a specific day (YYYY-MM-DD).
        """
        with self.db._get_conn() as conn:
            row = conn.execute("SELECT summary FROM daily_summaries WHERE day = ?", (day,)).fetchone()
            if row:
                return row["summary"]
        return f"No summary found for {day}."

    def list_pending_actions(self) -> List[Dict[str, Any]]:
        """Returns a list of all pending actions (table creations, catalog updates) that require approval."""
        with self.db._get_conn() as conn:
            cursor = conn.execute("SELECT * FROM _pending_actions WHERE status = 'pending'")
            return [dict(row) for row in cursor.fetchall()]

    def confirm_action(self, action_id: str, approve: bool) -> str:
        """Confirms (approves or rejects) a pending action. Use this when the user says 'I approve' or 'Reject it' in text."""
        success = self.db.execute_action(action_id, approved=approve)
        if success:
            return f"Action {action_id} {'approved' if approve else 'rejected'} successfully."
        else:
            return f"Failed to confirm action {action_id}. It may not exist or is already processed."

    @observe()
    def schedule_background_task(self, name: str, task_description: str, cron_expression: str) -> str:
        """
        Schedules a background task to be executed periodically.
        - name: A short name for the task.
        - task_description: The actual instruction for the agent (e.g., 'Check the weather and notify me').
        - cron_expression: Standard cron syntax (e.g., '0 9 * * *' for every day at 9 AM).
        """
        # We need the chat_id to know where to send the result.
        # However, tools are called within a session. 
        # In telegram_bot.py, session_id is "telegram_{chat_id}".
        try:
            chat_id = int(self.session_id.split("_")[1])
        except (IndexError, ValueError):
            return "Error: Could not determine chat_id from session_id. Background tasks are only supported via Telegram."

        self.db.add_background_task(name, task_description, cron_expression, chat_id)
        return f"Task '{name}' scheduled successfully with cron '{cron_expression}'."

    # ── Core chat method ────────────────────────────────────────────────
    @observe()
    def chat(self, user_message: str) -> str:
        """
        Send a message and get the agent's reply.
        Handles tool calling automatically.
        """
        # 1. Persist user message
        self.history.add_message(self.session_id, "user", user_message)

        # 2. Load today's conversation from Redis using UTC
        from datetime import datetime, timezone
        today_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
        messages_raw = self.history.get_history_by_time_range(self.session_id, today_start)

        # 3. Build Gemini contents
        contents = self._build_contents(messages_raw)

        # 4. Call Gemini with Tools
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=self.system_prompt + "\n\nCRITICAL: If you call a proposal tool, you MUST include the exact HITL_PROPOSAL:... string in your final response text so the system can show buttons to the user. If a user approves an action in text, use list_pending_actions to find the ID and confirm_action to execute it.",
                tools=self.tools,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=False,
                ),
            ),
        )

        reply = response.text or "(no response)"

        # 5. Persist assistant reply
        self.history.add_message(self.session_id, "assistant", reply)

        return reply

    # ── Session helpers ─────────────────────────────────────────────────
    def new_session(self, title: Optional[str] = None) -> str:
        """Create a new session and switch to it. Returns the new session ID."""
        self.session_id = self.history.create_session(title=title or "New conversation")
        return self.session_id

    def switch_session(self, session_id: str) -> None:
        """Switch to an existing session."""
        meta = self.history.get_session_metadata(session_id)
        if not meta:
            raise ValueError(f"Session '{session_id}' not found.")
        self.session_id = session_id

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Return all saved sessions with metadata."""
        return self.history.list_sessions()

    def get_current_history(self) -> List[Dict[str, Any]]:
        """Return the full message history for the current session."""
        return self.history.get_history(self.session_id)

    # ── Internal helpers ────────────────────────────────────────────────
    @staticmethod
    def _build_contents(messages: List[Dict[str, Any]]) -> list:
        contents = []
        for msg in messages:
            role = msg["role"]
            text = msg["content"]

            if role == "system":
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=f"[System] {text}")]))
                contents.append(types.Content(role="model", parts=[types.Part.from_text(text="Understood.")]))
            elif role == "assistant":
                contents.append(types.Content(role="model", parts=[types.Part.from_text(text=text)]))
            else:  # user
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=text)]))

        return contents
