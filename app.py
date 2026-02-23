"""
Butler Playground — Streamlit chat interface with Redis memory.

Run:  streamlit run app.py
"""

import streamlit as st
from agent import ButlerAgent
from chat_history import RedisChatHistory


# ── Page config ─────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Butler AI",
    page_icon="🤵",
    layout="centered",
)

# ── Custom CSS ──────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    /* Global */
    .stApp {
        font-family: 'Inter', sans-serif;
    }

    /* Header */
    .butler-header {
        text-align: center;
        padding: 1.5rem 0 1rem;
    }
    .butler-header h1 {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .butler-header p {
        color: #888;
        font-size: 0.95rem;
    }

    /* Session pill */
    .session-pill {
        display: inline-block;
        background: linear-gradient(135deg, #667eea22, #764ba222);
        border: 1px solid #667eea44;
        border-radius: 20px;
        padding: 0.3rem 1rem;
        font-size: 0.8rem;
        color: #667eea;
        margin-bottom: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Helper: initialise agent once per Streamlit session ─────────────────
def init_agent() -> ButlerAgent:
    """Create or return the cached ButlerAgent instance."""
    if "agent" not in st.session_state:
        try:
            agent = ButlerAgent()
            st.session_state.agent = agent
            st.session_state.current_session_id = agent.session_id
        except (ConnectionError, ValueError) as e:
            st.error(f"❌ {e}")
            st.stop()
    return st.session_state.agent


def load_history_into_state(agent: ButlerAgent) -> None:
    """Sync Redis history into Streamlit session_state messages."""
    redis_msgs = agent.get_current_history()
    st.session_state.messages = []
    for msg in redis_msgs:
        role = "assistant" if msg["role"] == "assistant" else "user"
        if msg["role"] == "system":
            continue  # Skip system messages in UI
        st.session_state.messages.append(
            {"role": role, "content": msg["content"]}
        )


# ── Main UI ─────────────────────────────────────────────────────────────
agent = init_agent()

# Header
st.markdown(
    '<div class="butler-header">'
    "<h1>🤵 Butler AI</h1>"
    "<p>Your AI assistant with persistent memory</p>"
    "</div>",
    unsafe_allow_html=True,
)

# ── Tabs ────────────────────────────────────────────────────────────────
tab_chat, tab_db = st.tabs(["💬 Chat", "🗄️ Database"])

# ── TAB 1: Chat ──────────────────────────────────────────────────────────
with tab_chat:
    # ── Sidebar: session management (only show when in chat tab for clarity) ──
    with st.sidebar:
        st.markdown("### 📂 Sessions")

        # New session button
        if st.button("➕ New Session", use_container_width=True):
            new_sid = agent.new_session(title="Streamlit chat")
            st.session_state.current_session_id = new_sid
            st.session_state.messages = []
            st.rerun()

        st.divider()

        # List existing sessions
        sessions = agent.list_sessions()
        for s in sessions:
            sid = s["session_id"]
            title = s.get("title", "(untitled)")
            is_current = sid == agent.session_id
            label = f"{'▶ ' if is_current else ''}{title}"
            col1, col2 = st.columns([4, 1])
            with col1:
                if st.button(
                    label,
                    key=f"sess_{sid}",
                    use_container_width=True,
                    disabled=is_current,
                ):
                    agent.switch_session(sid)
                    st.session_state.current_session_id = sid
                    load_history_into_state(agent)
                    st.rerun()
            with col2:
                if st.button("🗑", key=f"del_{sid}", help="Delete session"):
                    agent.history.delete_session(sid)
                    if is_current:
                        new_sid = agent.new_session(title="Streamlit chat")
                        st.session_state.current_session_id = new_sid
                        st.session_state.messages = []
                    st.rerun()

        st.divider()
        st.caption(f"Session: `{agent.session_id[:12]}…`")
        meta = agent.history.get_session_metadata(agent.session_id)
        if meta.get("created_at"):
            st.caption(f"Created: {meta['created_at'][:19]}")
        msg_count = agent.history.count_messages(agent.session_id)
        st.caption(f"Messages: {msg_count}")

    # ── Load messages on first run / session switch ─────────────────────────
    if "messages" not in st.session_state:
        load_history_into_state(agent)

    # Session indicator
    st.markdown(
        f'<div class="session-pill">Session: {agent.session_id[:12]}…</div>',
        unsafe_allow_html=True,
    )

    # ── Display chat messages ───────────────────────────────────────────────
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # ── Chat input ──────────────────────────────────────────────────────────
    if prompt := st.chat_input("Ask Butler anything…"):
        # Show user message immediately
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Get agent response (this saves to Redis internally)
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                try:
                    reply = agent.chat(prompt)
                except Exception as e:
                    reply = f"⚠️ Error: {e}"
            st.markdown(reply)

        st.session_state.messages.append({"role": "assistant", "content": reply})

# ── TAB 2: Database ──────────────────────────────────────────────────────
with tab_db:
    st.header("🗄️ SQL Database Management")
    
    # ── Table Explorer ──
    st.subheader("📋 Table Explorer")
    tables = agent.db.list_all_tables()
    
    if not tables:
        st.info("No tables found in the database.")
    else:
        selected_table = st.selectbox("Select a table to inspect", tables)
        
        col_meta, col_preview = st.columns([1, 2])
        
        with col_meta:
            st.write("**Schema**")
            schema = agent.db.get_table_schema(selected_table)
            st.table(schema)
            
        with col_preview:
            st.write(f"**Data Preview (Latest 100 rows)**")
            # For preview, we might want to order by created_at if it exists
            preview_data = agent.db.query(f"SELECT * FROM {selected_table} LIMIT 100")
            if preview_data:
                st.dataframe(preview_data, use_container_width=True)
            else:
                st.write("Table is empty.")

    st.divider()
    
    # ── SQL Console ──
    st.subheader("💻 SQL Console")
    query_text = st.text_area("Write your SQL query (SELECT, CREATE, INSERT, etc.)", height=150, placeholder="SELECT * FROM _master_catalog")
    
    if st.button("🚀 Run Query"):
        if query_text.strip():
            with st.spinner("Executing..."):
                result = agent.db.execute_raw_query(query_text)
                
                if result["success"]:
                    st.success("Query executed successfully!")
                    if "data" in result:
                        if result["data"]:
                            st.dataframe(result["data"], use_container_width=True)
                        else:
                            st.write("Query returned no results.")
                    elif "rows_affected" in result:
                        st.write(f"Rows affected: {result['rows_affected']}")
                else:
                    st.error(f"❌ SQL Error: {result['error']}")
        else:
            st.warning("Please enter a query.")
