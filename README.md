# 🤵 Butler AI

A conversational AI agent powered by **Google Gemini**, with persistent Redis memory, a versioned SQLite database backend, a Human-in-the-Loop (HITL) approval system, and support for scheduled background tasks.

Butler can be operated via three interfaces: a **CLI**, a **Streamlit web app**, or a **Telegram bot**.

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│                   Interfaces                     │
│  CLI (main.py) │ Streamlit (app.py) │ Telegram   │
└────────────────┬─────────────────┬──────────────┘
                 │                 │
         ┌───────▼─────────────────▼──────┐
         │         ButlerAgent            │
         │  (agent/butler.py)             │
         │  - Gemini 2.0 Flash            │
         │  - Automatic function calling  │
         │  - Langfuse observability      │
         └──────┬──────────────┬──────────┘
                │              │
   ┌────────────▼──┐   ┌───────▼──────────┐
   │ RedisChatHistory│   │   DBManager      │
   │ (chat_history/) │   │ (agent/db_manager│
   │ - Session mgmt  │   │  .py)            │
   │ - Msg history   │   │ - SQLite backend │
   └─────────────────┘   │ - Row versioning │
                         │ - HITL actions   │
                         │ - Background tasks│
                         └──────────────────┘
```

---

## Agent Technology

### 🧠 Conversational Memory
- Persistent, session-based chat history stored in **Redis**
- Multiple named sessions with session switching and deletion
- History scoped to the current UTC day per Gemini request

### 🔒 Row Versioning
Every agent-managed table uses a **composite primary key** `(row_id, version)` so updates are non-destructive. Old versions are marked `status = 'invalid'`; only the latest `valid` version is current.

### 📊 Observability
All agent calls and tool invocations are traced with **Langfuse** (optional). Credentials are loaded from Redis secrets.

---

## Agent Capabilities

### 🗄️ SQL Database Tools
The agent has direct access to a set of tools to manage a local **SQLite** database (`butler_sql.db`):

| Tool | Description |
|---|---|
| `get_database_metadata` | Lists all tables and schemas |
| `query_database` | Executes `SELECT` queries |
| `propose_new_table` | Stages table creation (requires HITL approval) |
| `add_data_to_table` | Inserts a new row |
| `update_row_data` | Updates a row via new versioning (old version marked `invalid`) |
| `propose_table_update` | Stages a master catalog metadata update (requires HITL approval) |
| `store_daily_summary` | Stores/upserts a plain-text summary for a given day |
| `get_daily_summary` | Retrieves the stored summary for a given day |
| `list_pending_actions` | Lists all pending HITL approvals |
| `confirm_action` | Approves or rejects a pending HITL action |

### ✅ Human-in-the-Loop (HITL)
Destructive or structural changes (table creation, catalog updates) are staged as **pending actions** and require explicit user approval before execution. In Telegram, approval is done via inline **Approve ✅ / Reject ❌** buttons.

### ⏰ Background Tasks & Protocols (Telegram)
- **Tasks**: Recurring tasks can be scheduled using **cron expressions**. The bot checks for due tasks every 60 seconds and executes them as agent prompts.
- **Protocols**: Multi-step AI pipelines (like the Daily Email Digest) that execute complex sequential workflows in the background.

### 📧 Gmail Integration
The agent can read and tag emails from your Gmail inbox via the Gmail API.

| Tool | Description |
|---|---|
| `list_emails` | List recent inbox emails (all or unread only) |
| `get_email` | Fetch full body of an email by ID |
| `search_emails` | Search using Gmail query operators (e.g. `from:boss is:unread`) |
| `add_label_to_email` | Add a label/tag to an email; creates label if it doesn't exist |
| `remove_label_from_email` | Remove a label from an email |

All OAuth credentials (client secret + access token) are stored **in Redis** — no credential files ever live on disk at runtime.

---

## Project Structure

```
butler/
├── agent/
│   ├── __init__.py          # Exports ButlerAgent
│   ├── butler.py            # Core agent class (Gemini + tools + session)
│   ├── db_manager.py        # SQLite backend (versioning, HITL, tasks)
│   └── gmail_tools.py       # Gmail API wrapper (OAuth via Redis)
├── chat_history/
│   ├── __init__.py
│   └── redis_history.py     # Redis-backed session and message store
├── secrets_manager/
│   └── redis_secrets.py     # Redis-backed API key/secret store
├── app.py                   # Streamlit web UI (chat + DB explorer tabs)
├── main.py                  # CLI interface with session management
├── telegram_bot.py          # Telegram bot with HITL buttons and background tasks
├── manage_keys.py           # CLI tool for managing secrets in Redis
├── docker-compose.yml       # Redis container setup
├── requirements.txt         # Python dependencies
└── butler_sql.db            # SQLite database (auto-created on first run)
```

---

## To-Do: Configuration & Testing

This section covers exactly what you need to configure and how you can test the new features.

### 1. Mandatory Setup (Done)
1. **Start Redis**:
   ```bash
   docker compose up -d
   ```
2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

### 2. Configure Required Secrets (Done)
Run the key manager to store your API keys in Redis:
```bash
python manage_keys.py set gemini YOUR_GEMINI_API_KEY
python manage_keys.py set telegram YOUR_TELEGRAM_BOT_TOKEN
```

*(Optional Langfuse keys)*: (Done)
```bash
python manage_keys.py set langfuse_public_key YOUR_LF_PUBLIC_KEY
python manage_keys.py set langfuse_secret_key YOUR_LF_SECRET_KEY
```

### 3. Configure Gmail (Required for Email Digest)
To use the email capabilities, you must provide an OAuth Desktop client ID.
1. Download your `credentials.json` from the Google Cloud Console.
2. Load it securely into Redis:
   ```bash
   python manage_keys.py set-file gmail_credentials path/to/credentials.json
   ```
3. *(You can now delete the `credentials.json` file).*

### 4. Test the Daily Email Digest Protocol
To verify the multi-step background pipeline is working:
1. Start the Telegram Bot: `python telegram_bot.py`
2. Message your Butler bot on Telegram: **"Set up my daily email digest"**
   - *Butler will register the protocol and provide an ID.*
   - *(Note: The first time a Gmail tool is used, a browser will open on your host machine to complete the OAuth login — the final token is saved to Redis).*
3. **Trigger it immediately**: Tell Butler *"Change the cron for email_daily_digest to run every minute ( * * * * * )"*
4. **Verify the workflow**:
   - Check the `emails/YYYY-MM-DD/` folder in your project directory (JSON files should appear).
   - Check your Telegram chat (you should receive a formatted digest from the agent).
5. **Revert the schedule**: Tell Butler *"Change the email_daily_digest cron back to 6:00 AM (0 6 * * *)"*.
---

## Running Butler
TLDR: just use the provided batch file:
```bash
run_bot.bat
```

### CLI
```bash
python main.py
```
Supports session commands: `/new`, `/sessions`, `/switch <id>`, `/history`, `/quit`.

### Streamlit Web App
```bash
streamlit run app.py
```
Opens a browser UI with a **Chat tab** (session sidebar) and a **Database tab** (table explorer + SQL console).

### Telegram Bot
```bash
python telegram_bot.py
```

---

## Key Design Decisions

- **No raw DDL from users**: Table creation always goes through the HITL proposal → approval flow, preventing accidental schema changes.
- **Versioned rows over mutable updates**: Data history is preserved; no row is ever truly deleted by the agent.
- **Secrets in Redis**: API keys are stored encrypted in Redis, not in `.env` files, enabling runtime updates without restarts.
- **Per-interface session isolation**: CLI and Streamlit use UUID sessions; Telegram uses `telegram_{chat_id}` as the session key so each chat has its own persistent context.

---

## Current Status

| Component | Status |
|---|---|
| Core agent (`ButlerAgent`) | ✅ Stable |
| Redis chat history | ✅ Stable |
| SQLite DB with versioning | ✅ Stable |
| HITL action system | ✅ Stable |
| Streamlit UI | ✅ Working |
| CLI interface | ✅ Working |
| Telegram bot | ✅ Working |
| Background task scheduling | ✅ Working (Telegram only) |
| Langfuse observability | ✅ Optional / configurable |
| Gmail integration | ✅ Working (requires OAuth setup) |

---