import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from langfuse import observe

from backend.chat_history import RedisChatHistory
from backend.secrets_manager.redis_secrets import RedisSecretsManager
from agent.db_manager import DBManager
from agent.gmail_tools import GmailTools
from agent.vector_db import VectorDB
from agent.data_ingester import DataIngester

load_dotenv()

# ── Default system prompt ───────────────────────────────────────────────
def load_system_prompt(file_path="prompts/system_prompt.txt"):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "You are a helpful AI assistant."

DEFAULT_SYSTEM_PROMPT = load_system_prompt()


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
        self.gmail = GmailTools(self.secrets)
        self.vector_db = VectorDB(
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", 6333))
        )

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
        self.model = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
        print(f"[Butler] Agent initialised with model: {self.model}")
        self.ingester = DataIngester(self.db, self.vector_db, self.client)

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
            self.schedule_background_task,
            # ── Gmail tools ──────────────────────────────────────────────
            self.list_emails,
            self.get_email,
            self.search_emails,
            self.add_label_to_email,
            self.remove_label_from_email,
            self.semantic_search_emails,
            self.index_recent_emails,
            # ── Message Ingestion tools ──────────────────────────────────
            self.sync_data_folder,
            self.semantic_search_messages,
            # ── Protocol tools ───────────────────────────────────────────
            self.register_email_digest,
            self.create_protocol,
            self.list_protocols,
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

    # ── Gmail Tools ──────────────────────────────────────────────────────

    @observe()
    def list_emails(self, max_results: int = 10, unread_only: bool = False):
        """
        List recent emails from the Gmail inbox.

        Args:
            max_results: How many emails to return (default 10, max 50).
            unread_only: If True, return only unread emails.

        Returns:
            List of email summaries with id, subject, from, date, snippet, labels.
        """
        return self.gmail.list_emails(max_results=max_results, unread_only=unread_only)

    @observe()
    def get_email(self, email_id: str):
        """
        Get the full content of an email by its ID.

        Args:
            email_id: The Gmail message ID (obtained from list_emails or search_emails).

        Returns:
            Dict with id, subject, from, to, date, body, labels.
        """
        return self.gmail.get_email(email_id=email_id)

    @observe()
    def search_emails(self, query: str, max_results: int = 10):
        """
        Search Gmail using a query string (supports Gmail search operators).

        Example queries:
          - "from:boss@company.com is:unread"
          - "subject:invoice after:2024/01/01"
          - "has:attachment"

        Args:
            query: Gmail search query.
            max_results: Max results to return (default 10, max 50).

        Returns:
            List of email summary dicts.
        """
        return self.gmail.search_emails(query=query, max_results=max_results)

    @observe()
    def add_label_to_email(self, email_id: str, label_name: str) -> str:
        """
        Add a label (tag) to a Gmail message. Creates the label if it doesn't exist.

        Args:
            email_id: Gmail message ID.
            label_name: Name of the label to add (e.g. "Butler/Review").

        Returns:
            Confirmation message.
        """
        return self.gmail.add_label_to_email(email_id=email_id, label_name=label_name)

    @observe()
    def remove_label_from_email(self, email_id: str, label_name: str) -> str:
        """
        Remove a label from a Gmail message.

        Args:
            email_id: Gmail message ID.
            label_name: Name of the label to remove.

        Returns:
            Confirmation message.
        """
        return self.gmail.remove_label_from_email(email_id=email_id, label_name=label_name)

    @observe()
    def semantic_search_emails(self, query: str, limit: int = 5) -> str:
        """
        Perform a semantic (RAG) search across indexed emails.
        Use this when the user asks a question about the content of their emails,
        especially when keywords might not match exactly.

        Args:
            query: The search query or question.
            limit: Number of results to return (default 5).
        """
        results = self.vector_db.search_emails(query, self.client, limit=limit)
        if not results:
            return "No relevant emails found in the vector database."
        
        output = "Relevant emails found:\n\n"
        for r in results:
            output += f"- *{r['subject']}* (From: {r['from']}, Date: {r['date']})\n"
            output += f"  Snippet: {r['text']}...\n"
            output += f"  ID: {r['email_id']}\n\n"
        return output

    @observe()
    def index_recent_emails(self, count: int = 20) -> str:
        """
        Indexes the most recent emails into the vector database for future RAG searches.
        You should run this if the user asks to 'index my emails' or 'update search'.

        Args:
            count: Number of recent emails to index (default 20).
        """
        emails = self.gmail.list_emails(max_results=count)
        indexed_count = 0
        for e in emails:
            if "error" in e: continue
            
            # Fetch full content to index better
            full = self.gmail.get_email(e["id"])
            if "error" in full:
                body = e.get("snippet", "")
            else:
                body = full.get("body", "")

            # Prepare metadata
            metadata = {
                "subject": e.get("subject"),
                "from": e.get("from"),
                "date": e.get("date")
            }
            
            # Prepare text for embedding: combine subject and body
            index_text = f"Subject: {e.get('subject')}\n\n{body}"
            
            success = self.vector_db.upsert_email(e["id"], index_text, metadata, self.client)
            if success:
                indexed_count += 1
        
        return f"Successfully indexed {indexed_count} emails into the vector database."

    @observe()
    def sync_data_folder(self, folder_path: Optional[str] = None) -> str:
        """
        Scans a local folder for new Zalo/Facebook ZIP exports and indexes them.
        Use this if the user says 'sync my data' or 'update my messages'.

        Args:
            folder_path: Override for the default DATA_INGEST_DIR.
        """
        path = folder_path or os.getenv("DATA_INGEST_DIR", "./data_ingest")
        result = self.ingester.scan_folder(path)
        
        if result["status"] == "info":
            return result["message"]
            
        summary = ""
        for r in result.get("results", []):
            summary += f"- {r.get('message', 'Processing done.')}\n"
            
        return f"Data sync complete in {path}:\n{summary or 'No new files found.'}"

    @observe()
    def semantic_search_messages(self, query: str, source: str = "all", limit: int = 5) -> str:
        """
        Searches through indexed Zalo and Facebook messages using semantic search.
        Use this when the user asks about chats, Zalo history, or Facebook messages.

        Args:
            query: The search question.
            source: 'zalo', 'facebook', or 'all' (default).
            limit: Number of results (default 5).
        """
        collections = []
        if source == "zalo":
            collections = ["zalo"]
        elif source == "facebook":
            collections = ["facebook"]
        else:
            collections = ["zalo", "facebook"]

        all_results = []
        for col in collections:
            res = self.vector_db.search_documents(col, query, self.client, limit=limit)
            all_results.extend(res)

        # Sort by score and limit
        all_results.sort(key=lambda x: x.get("score", 0), reverse=True)
        results = all_results[:limit]

        if not results:
            return f"No relevant {source} messages found."

        output = f"Top {len(results)} relevant messages found:\n\n"
        for r in results:
            src = r.get("source", "unknown").upper()
            sender = r.get("sender", "Unknown")
            date_str = ""
            if r.get("timestamp"):
                from datetime import datetime
                date_str = f" on {datetime.fromtimestamp(r['timestamp']).strftime('%Y-%m-%d %H:%M')}"
            
            output += f"--- [{src}] From {sender}{date_str} ---\n"
            output += f"{r.get('text', '')}\n\n"
            
        return output

    # ── Protocol Tools ───────────────────────────────────────────────────

    @observe()
    def register_email_digest(self) -> str:
        """
        Registers the built-in daily email digest protocol.
        It runs daily at 6:00 AM, fetches emails since the last run, filters spam with AI,
        and sends a summary to the user's Telegram.

        Returns:
            Confirmation string.
        """
        try:
            chat_id = int(self.session_id.split("_")[1])
        except (IndexError, ValueError):
            return "Error: Could not determine chat_id. Protocols require Telegram."

        import agent.email_digest as ed
        return ed.register(self.db, chat_id)

    @observe()
    def list_protocols(self) -> List[Dict[str, Any]]:
        """
        Lists all active background protocols (multi-step tasks).
        """
        return self.db.list_protocols()

    @observe()
    def create_protocol(
        self, name: str, description: str, steps: List[Dict[str, Any]], cron_expression: str
    ) -> str:
        """
        Proposes the creation of a generic multi-step protocol. Requires HITL approval.
        'steps' must be A JSON array of step dictionaries.
        """
        # We abuse propose_master_update or create a new HITL action type if we wanted purely generic.
        # But for now we just insert it, since the user usually asks for it directly.
        try:
            chat_id = int(self.session_id.split("_")[1])
        except (IndexError, ValueError):
            return "Error: Could not determine chat_id."

        pid = self.db.add_protocol(name, description, steps, cron_expression, chat_id)
        return f"Protocol '{name}' created with ID {pid}, cron '{cron_expression}'."

    # ── Core chat method ────────────────────────────────────────────────
    @observe()
    def chat(self, user_message: str, image_bytes: Optional[bytes] = None) -> str:
        """
        Send a message and get the agent's reply.
        Handles tool calling automatically.
        """
        # 1. Persist user message (Redis history only stores text for now)
        self.history.add_message(self.session_id, "user", user_message)

        # 2. Load today's conversation from Redis using UTC
        from datetime import datetime, timezone
        today_start = datetime.now(timezone.utc).strftime("%Y-%m-%dT00:00:00")
        messages_raw = self.history.get_history_by_time_range(self.session_id, today_start)

        # 3. Build Gemini contents (including image if provided for the last turn)
        contents = self._build_contents(messages_raw, current_image_bytes=image_bytes)

        # 4. Call Gemini with Tools
        try:
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
        except Exception as e:
            print(f"[Butler] Gemini API Error: {e}")
            raise

        # Debug print
        print(f"[Butler] Model: {self.model}, Response candidates: {len(response.candidates or [])}")
        
        reply = response.text or "(no response)"
        if not response.text and response.candidates:
            # Check if there's a finish reason that explains it
            finish_reason = response.candidates[0].finish_reason
            print(f"[Butler] Warning: Empty text response. Finish reason: {finish_reason}")
            if finish_reason == "SAFETY":
                reply = "⚠️ I cannot answer this due to safety filters."
            elif finish_reason == "OTHER":
                 reply = "⚠️ Something went wrong with the model generation."

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
    def _build_contents(messages: List[Dict[str, Any]], current_image_bytes: Optional[bytes] = None) -> list:
        contents = []
        for i, msg in enumerate(messages):
            role = msg["role"]
            text = msg["content"]
            is_last = (i == len(messages) - 1)

            if role == "system":
                contents.append(types.Content(role="user", parts=[types.Part.from_text(text=f"[System] {text}")]))
                contents.append(types.Content(role="model", parts=[types.Part.from_text(text="Understood.")]))
            elif role == "assistant":
                contents.append(types.Content(role="model", parts=[types.Part.from_text(text=text)]))
            else:  # user
                parts = [types.Part.from_text(text=text)]
                # Only attach image to the very last message in the sequence (the current one)
                if is_last and current_image_bytes:
                    parts.append(types.Part.from_bytes(data=current_image_bytes, mime_type="image/jpeg"))
                contents.append(types.Content(role="user", parts=parts))

        return contents
