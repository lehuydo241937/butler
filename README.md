# 🤵 Butler AI (Agent: Kuro)

A powerful conversational AI agent named **Kuro**, powered by **Google Gemini 3.0 Flash**, with persistent Redis memory, a versioned SQLite database, a vector storage backend (Qdrant) for RAG, a Human-in-the-Loop (HITL) approval system, and support for scheduled background protocols.

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
         │  - Gemini 3.0 Flash Preview    │
         │  - Automatic function calling  │
         │  - Langfuse observability      │
         └──────┬────────┬────────┬───────┘
                │        │        │
    ┌───────────▼──┐ ┌───▼────┐ ┌─▼─────────────┐
    │  Backend Layer │ │DBManager│ │   VectorDB    │
    │  (backend/)    │ │(agent/) │ │(Qdrant 6333)  │
    │- Chat History  │ │- SQLite  │ │- RAG Search    │
    │- Redis Secrets │ │- HITL    │ │- Email Index   │
    └────────────────┘ └──────────┘ └───────────────┘
```

---

## Core Technologies

### 🧠 Persistent Conversational Memory
- Session-based chat history stored in **Redis**.
- Multiple named sessions with easy switching.
- History is scoped by daily UTC time ranges for optimized LLM context.

### 🗄️ SQL Database with Row Versioning
- Non-destructive updates using a **composite primary key** `(row_id, version)`.
- Updates create new `valid` versions, while old ones are marked `invalid`.
- Structural changes (DDL) require Human-in-the-Loop approval.

### 🔍 Vector Search (RAG)
- Powered by **Qdrant** for semantic retrieval of emails and chat messages.
- Uses `gemini-embedding-001` for heavy-duty semantic indexing.
- Supports indexing of Gmail inboxes and Zalo/Facebook message exports.

---

## Agent Capabilities

### 🛠️ Strategic Tools
The agent (Kuro) has access to a wide variety of tools:

| Category | Description | Tools |
|---|---|---|
| **SQL DB** | Manage structured data & tables | `get_database_metadata`, `query_database`, `propose_new_table`, `add_data_to_table`, `update_row_data` |
| **HITL** | Approve/Reject structural changes | `confirm_action`, `list_pending_actions` |
| **Gmail** | Read, label, & search emails | `list_emails`, `get_email`, `search_emails`, `add_label_to_email`, `semantic_search_emails`, `index_recent_emails` |
| **Ingestion** | Sync & search chat messages | `sync_data_folder`, `semantic_search_messages` (Zalo & Facebook) |
| **Protocols** | Multi-step background pipelines | `register_email_digest`, `create_protocol`, `list_protocols` |

---

## Project Structure

```
butler/
├── agent/                   # Agentic logic & Tool wrappers
│   ├── butler.py            # Core agent class (Kuro)
│   ├── db_manager.py        # SQLite backend (versioning, HITL)
│   ├── vector_db.py         # Qdrant wrapper (semantic search)
│   ├── data_ingester.py     # ZIP extraction & message parsing (Zalo/FB)
│   ├── gmail_tools.py       # Gmail API integration
│   ├── email_digest.py      # Logic for the Daily Email Digest protocol
│   └── protocol_runner.py   # Multi-step pipeline executor
├── backend/                 # Core Infrastructure & Persistence
│   ├── chat_history/        # Redis session & history store
│   └── secrets_manager/     # Redis-backed secrets manager
├── prompts/                 # Externalized AI prompts
│   └── system_prompt.txt    # Default system instruction
├── tests/                   # Test suite
│   └── unit/                # Unit tests for core functions
├── run_bot.bat              # Run Telegram Bot
├── run_api.bat              # Run REST API
├── run_streamlit.bat        # Run Streamlit UI
├── run_all.bat              # Run all components
├── app.py                   # Streamlit web UI
├── main.py                  # CLI interface
├── telegram_bot.py          # Telegram bot script
└── butler_sql.db            # SQLite database (auto-created)
```

---

## Quick Setup

### 1. Requirements
- **Docker** (for Redis & Qdrant)
- **Python 3.10+**
- **Google Gemini API Key**

### 2. Launch Infrastructure
```bash
docker compose up -d
```
*Note: Ensure your `docker-compose.yml` includes both Redis and Qdrant.*

### 3. Install & Configure
```bash
pip install -r requirements.txt
python manage_keys.py set gemini YOUR_GEMINI_API_KEY
python manage_keys.py set telegram YOUR_TELEGRAM_BOT_TOKEN
```

### 4. Gmail Ingestion (Optional)
If you want to use Gmail tools, load your client secret:
```bash
python manage_keys.py set-file gmail_credentials path/to/credentials.json
```

---

## Running Butler

### Telegram Bot
```bash
run_bot.bat
```

### Streamlit UI
```bash
run_streamlit.bat
```

### REST API
```bash
run_api.bat
```

### All Components
```bash
run_all.bat
```

---

## Status Overview

| Component | Status |
|---|---|
| Core Agent (Kuro) | ✅ Stable |
| Redis Chat History | ✅ Stable |
| SQLite Versioning | ✅ Stable |
| Vector Search (RAG) | ✅ Working (Qdrant) |
| Gmail Integration | ✅ Working |
| Message Ingestion | ✅ Working (ZIP imports) |
| Protocols (HITL) | ✅ Working |
| Telegram Bot | ✅ Working |
| Streamlit / CLI | ✅ Working |

---