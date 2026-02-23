import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types

from chat_history import RedisChatHistory
from secrets_manager.redis_secrets import RedisSecretsManager
from agent.db_manager import DBManager

load_dotenv()

# ── Default system prompt ───────────────────────────────────────────────
DEFAULT_SYSTEM_PROMPT = (
    "You are Kuro, a helpful and friendly AI assistant. "
    "You have access to a SQL database via tools. "
    "Use these tools to store, retrieve, and manage structured data. "
    "When asked to create a table or update its status, use the proposal tools. "
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

        self.client = genai.Client(api_key=api_key)
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp") # Using a model that supports fc well

        # ── Tool Definitions ────────────────────────────────────────────
        self.tools = [
            self.get_database_metadata,
            self.query_database,
            self.propose_new_table,
            self.add_data_to_table,
            self.update_row_data,
            self.propose_table_update,
            self.store_daily_summary,
            self.get_daily_summary
        ]

    # ── Database Tools ──────────────────────────────────────────────────

    def get_database_metadata(self) -> List[Dict[str, Any]]:
        """Returns the list of tables available in the database and their schemas."""
        return self.db.get_catalog()

    def query_database(self, sql: str) -> List[Dict[str, Any]]:
        """Executes a SELECT SQL query on the database. Use this to retrieve data."""
        if not sql.strip().lower().startswith("select"):
            return [{"error": "Only SELECT queries are allowed for safety."}]
        return self.db.query(sql)

    def propose_new_table(self, table_name: str, description: str, columns: Dict[str, str]) -> str:
        """
        Stages a request to create a new table. 
        Columns should be a dictionary of {column_name: sqlite_type} (e.g. {"name": "TEXT", "age": "INTEGER"}).
        This action requires manual user approval.
        """
        action_id = self.db.propose_table_creation(table_name, description, columns)
        return f"HITL_PROPOSAL:table_creation:{action_id}:Table '{table_name}' creation proposed. Please approve/reject."

    def add_data_to_table(self, table_name: str, data: Dict[str, Any]) -> str:
        """Adds a new row of data to an existing table."""
        row_id = self.db.add_data(table_name, data)
        return f"Data added to '{table_name}'. Row ID: {row_id}"

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

    # ── Core chat method ────────────────────────────────────────────────
    def chat(self, user_message: str) -> str:
        """
        Send a message and get the agent's reply.
        Handles tool calling automatically.
        """
        # 1. Persist user message
        self.history.add_message(self.session_id, "user", user_message)

        # 2. Load today's conversation from Redis
        from datetime import datetime
        today_start = datetime.now().strftime("%Y-%m-%dT00:00:00")
        messages_raw = self.history.get_history_by_time_range(self.session_id, today_start)

        # 3. Build Gemini contents
        contents = self._build_contents(messages_raw)

        # 4. Call Gemini with Tools
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=self.system_prompt,
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
