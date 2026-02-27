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

## Features

### 🧠 Conversational Memory
- Persistent, session-based chat history stored in **Redis**
- Multiple named sessions with session switching and deletion
- History scoped to the current UTC day per Gemini request

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
| `schedule_background_task` | Schedules a cron-based automated task (Telegram only) |

### 🔒 Row Versioning
Every agent-managed table uses a **composite primary key** `(row_id, version)` so updates are non-destructive. Old versions are marked `status = 'invalid'`; only the latest `valid` version is current.

### ✅ Human-in-the-Loop (HITL)
Destructive or structural changes (table creation, catalog updates) are staged as **pending actions** and require explicit user approval before execution. In Telegram, approval is done via inline **Approve ✅ / Reject ❌** buttons.

### ⏰ Background Tasks (Telegram)
Recurring tasks can be scheduled using **cron expressions**. The bot checks for due tasks every 60 seconds and executes them as agent prompts, sending results back to the user's chat.

### 📊 Observability
All agent calls and tool invocations are traced with **Langfuse** (optional). Credentials are loaded from Redis secrets.

---

## Project Structure

```
butler/
├── agent/
│   ├── __init__.py          # Exports ButlerAgent
│   ├── butler.py            # Core agent class (Gemini + tools + session)
│   └── db_manager.py        # SQLite backend (versioning, HITL, tasks)
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

## Setup

### 1. Start Redis

```bash
docker compose up -d
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Store API keys in Redis

```bash
# Required
python manage_keys.py set gemini YOUR_GEMINI_API_KEY

# For Telegram interface
python manage_keys.py set telegram YOUR_TELEGRAM_BOT_TOKEN

# Optional: Langfuse observability
python manage_keys.py set langfuse_public_key YOUR_LF_PUBLIC_KEY
python manage_keys.py set langfuse_secret_key YOUR_LF_SECRET_KEY
python manage_keys.py set langfuse_host https://cloud.langfuse.com
```

> **Tip:** You can also set `GEMINI_API_KEY` as a regular environment variable (`.env` file or shell) as a fallback.

---

## Running Butler

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
Or using the provided batch file:
```bash
run_bot.bat
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
