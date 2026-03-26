# 🖤 Butler AI — Kuro OS (Agentic Operating System)

**Kuro** is a self-evolving, tri-layered Agentic OS powered by **Google Gemini 3.0 Flash**. It has graduated from a reactive chatbot into a strategic orchestrator that plans, routes, and autonomously builds its own capabilities.

Butler can be operated via a **rich interactive CLI**, a **Streamlit web app**, or a **Telegram bot**.

---

## Architecture

```
┌────────────────────────────────────────────────────────┐
│              CLI Dashboard (main.py)                   │
│  rich panels · live logs · HITL approval tables        │
└──────────────────────┬─────────────────────────────────┘
                       │
┌──────────────────────▼─────────────────────────────────┐
│           Layer 1 — Strategic Manager (Kuro)           │
│  agent/butler.py · Gemini 3.0 Flash                    │
│  1. Check script_inventory                             │
│  2. Compose multi-step plan                            │
│  3. Delegate to agent_dev if capability gap found      │
└──────────┬──────────────────────────────────────────────┘
           │
┌──────────▼──────────────────────────────────────────────┐
│           Layer 2 — Dispatcher (agent/dispatcher.py)   │
│  Routes plan steps → execution units                   │
│  Gemini Flash (planning) · Qwen2.5-Coder (coding)      │
└──────────┬──────────────┬──────────────────────────────┘
           │              │
┌──────────▼────┐  ┌──────▼──────────────────────────────┐
│  Layer 3A     │  │  Layer 3B — Agent Dev               │
│  script_run   │  │  agent/workers/dev_agent.py         │
│  Executes     │  │  Git branch → Write & Pytest →      │
│  verified py  │  │  Self-Correction Loop → Merge       │
└───────────────┘  └─────────────────────────────────────┘
           │              │
┌──────────▼──────────────▼──────────────────────────────┐
│                    Data Layer                          │
│  SQLite (butler_sql.db) · Redis (memory) · Qdrant (RAG)│
└────────────────────────────────────────────────────────┘
```

---

## Core Technologies

### 🧠 Persistent Conversational Memory
- Session-based chat history stored in **Redis**.
- Multiple named sessions with easy switching.
- History scoped by daily UTC time ranges for optimized LLM context.

### 🗄️ SQL Database with Row Versioning
- Non-destructive updates via composite primary key `(row_id, version)`.
- Updates create new `valid` versions; old ones are marked `invalid`.
- Structural changes (DDL) require Human-in-the-Loop (HITL) approval.

### 🔍 Vector Search (RAG)
- Powered by **Qdrant** for semantic retrieval of emails and chat messages.
- Uses `gemini-embedding-001` for semantic indexing.
- Supports Gmail inboxes and Zalo/Facebook message exports.

---

## Database Schema

| Table | Purpose |
|---|---|
| `_master_catalog` | Registry of all user-defined tables |
| `_pending_actions` | HITL queue (table creation, catalog updates) |
| `daily_summaries` | Historical daily context |
| `tasks` | Legacy single-step background tasks |
| `protocols` | Multi-step scheduled pipelines |
| `processed_files` | ZIP import tracking |
| `script_inventory` | ✨ Verified callable scripts (Kuro OS) |
| `plans` | ✨ High-level task decompositions |
| `plan_steps` | ✨ Per-step routing (layer + model) |
| `dev_logs` | ✨ Agent self-correction history |

> ✨ = Added in the Kuro OS upgrade.

---

## Agent Capabilities

### 🛠️ Strategic Tools

| Category | Tools |
|---|---|
| **SQL DB** | `get_database_metadata`, `query_database`, `propose_new_table`, `add_data_to_table`, `update_row_data` |
| **HITL** | `confirm_action`, `list_pending_actions` |
| **Gmail** | `list_emails`, `get_email`, `search_emails`, `add_label_to_email`, `semantic_search_emails`, `index_recent_emails` |
| **Ingestion** | `sync_data_folder`, `semantic_search_messages` |
| **Protocols** | `register_email_digest`, `create_protocol`, `list_protocols` |

---

## Project Structure

```
butler/
├── agent/
│   ├── butler.py            # Layer 1: Strategic Manager (Kuro)
│   ├── dispatcher.py        # Layer 2: Intelligent Dispatcher [🔲 WIP]
│   ├── db_manager.py        # SQLite backend (versioning, HITL, plans)
│   ├── vector_db.py         # Qdrant wrapper (semantic search)
│   ├── data_ingester.py     # ZIP extraction & message parsing
│   ├── gmail_tools.py       # Gmail API integration
│   ├── email_digest.py      # Daily Email Digest protocol
│   ├── protocol_runner.py   # Multi-step pipeline executor
│   └── workers/             # Script inventory (auto-discovered)
│       └── dev_agent.py     # Layer 3B: Self-evolving builder [🔲 WIP]
├── backend/
│   ├── chat_history/        # Redis session & history store
│   └── secrets_manager/     # Redis-backed secrets manager
├── prompts/
│   └── system_prompt.txt    # Kuro OS orchestrator identity
├── tests/
│   ├── conftest.py          # sys.path setup
│   └── unit/
│       ├── test_db_manager.py    # 34 tests — DB core + new tables
│       ├── test_cli_helpers.py   # 16 tests — CLI dashboard helpers
│       ├── test_butler_core.py   # System prompt loading
│       ├── test_chat_history.py  # Redis session management
│       └── test_secrets_manager.py
├── pytest.ini               # Test discovery config
├── main.py                  # CLI Command Center (rich + prompt_toolkit)
├── app.py                   # Streamlit web UI
├── telegram_bot.py          # Telegram bot
├── api.py                   # REST API (FastAPI)
└── butler_sql.db            # SQLite database (auto-created)
```

---

## CLI Command Center

Run with:
```bash
python main.py
```

### Commands

| Command | Description |
|---|---|
| `/new [title]` | Create a new session |
| `/sessions` | List all sessions |
| `/switch <id>` | Switch session by ID prefix |
| `/history` | Show current session history |
| `/list-scripts` | Show the script inventory |
| `/sync-inventory` | Auto-discover & register scripts from `agent/workers/` |
| `/plans` | Show recent task plans and their status |
| `/help` | Show command reference |
| `/quit` | Exit |

**UI color scheme:** 🟢 Green = Success · 🟡 Yellow = Pending/HITL · 🔴 Red = Error

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

### 3. Install & Configure
```bash
pip install -r requirements.txt
python manage_keys.py set gemini YOUR_GEMINI_API_KEY
python manage_keys.py set telegram YOUR_TELEGRAM_BOT_TOKEN
```

### 4. Gmail Ingestion (Optional)
```bash
python manage_keys.py set-file gmail_credentials path/to/credentials.json
```

---

## Running Butler

```bash
# CLI (primary interface)
python main.py

# Telegram Bot
run_bot.bat

# Streamlit UI
run_streamlit.bat

# REST API
run_api.bat

# All components
run_all.bat
```

---

## Running Tests

```bash
pytest
# or explicitly:
pytest tests/unit/ -v
```

---

## Status Overview

| Component | Status |
|---|---|
| Core Agent (Kuro) | ✅ Stable |
| Redis Chat History | ✅ Stable |
| SQLite Versioning | ✅ Stable |
| Vector Search (RAG) | ✅ Working |
| Gmail Integration | ✅ Working |
| Message Ingestion | ✅ Working |
| Protocols (HITL) | ✅ Working |
| Telegram Bot | ✅ Working |
| Streamlit / REST API | ✅ Working |
| **CLI Dashboard (rich)** | ✅ **New** |
| **Script Inventory DB** | ✅ **New** |
| **Plans & Dev Logs DB** | ✅ **New** |
| **Unit Test Suite (50 tests)** | ✅ **New** |
| Dispatcher (Layer 2) | 🔲 WIP |
| Agent Dev (Layer 3B) | 🔲 WIP |

---