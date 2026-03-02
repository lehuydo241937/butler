"""
Butler Playground — Streamlit chat interface with Redis memory.

Run:  streamlit run app.py
"""

import streamlit as st
from datetime import datetime, timezone
from agent.network_utils import force_ipv4

# Force IPv4 to prevent timeouts on environments with broken IPv6
force_ipv4()

from agent import ButlerAgent
from backend.chat_history import RedisChatHistory


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

# Sidebar Navigation
st.sidebar.title("🤵 Butler Dashboard")
page = st.sidebar.radio(
    "Navigation",
    ["💬 Agent Testing", "🗃️ SQL Schema View", "🕒 Redis History", "🧬 Vector Collections"]
)

# ── PAGE: Agent Testing ──────────────────────────────────────────────────
if page == "💬 Agent Testing":
    st.markdown(
        '<div class="butler-header">'
        "<h1>💬 Agent Testing</h1>"
        "<p>Test the Butler agent with a consistent chat session</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    
    # Use a specific session for testing
    TEST_SESSION_ID = "streamlit_test_session"
    
    # Check if we need to switch to test session
    if agent.session_id != TEST_SESSION_ID:
        try:
            agent.switch_session(TEST_SESSION_ID)
        except ValueError:
            agent.new_session(title="Test Session") # create_session is usually random, but switch_session checks metadata
            # Force set if creation doesn't allow custom SID easily
            agent.session_id = TEST_SESSION_ID
            agent.history.r.sadd(agent.history._SESSION_INDEX, TEST_SESSION_ID)
            agent.history.r.hset(agent.history._META_KEY.format(sid=TEST_SESSION_ID), mapping={
                "title": "Streamlit Test Session",
                "created_at": datetime.now(timezone.utc).isoformat()
            })

    if "messages" not in st.session_state or st.session_state.get("last_sid") != TEST_SESSION_ID:
        load_history_into_state(agent)
        st.session_state.last_sid = TEST_SESSION_ID

    st.markdown(f'<div class="session-pill">Test Session ID: `{TEST_SESSION_ID}`</div>', unsafe_allow_html=True)

    # Display chat messages
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Chat input
    if prompt := st.chat_input("Ask Butler anything…"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                try:
                    reply = agent.chat(prompt)
                except Exception as e:
                    reply = f"⚠️ Error: {e}"
            st.markdown(reply)
        st.session_state.messages.append({"role": "assistant", "content": reply})

# ── PAGE: SQL Schema View ──────────────────────────────────────────────
elif page == "🗃️ SQL Schema View":
    st.markdown(
        '<div class="butler-header">'
        "<h1>🗃️ SQL Schema View</h1>"
        "<p>Inspect tables, schemas, and run queries</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    
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
            preview_data = agent.db.query(f"SELECT * FROM {selected_table} LIMIT 100")
            if preview_data:
                st.dataframe(preview_data, use_container_width=True)
            else:
                st.write("Table is empty.")

    st.divider()
    
    st.subheader("💻 SQL Console")
    query_text = st.text_area("Write your SQL query", height=150, placeholder="SELECT * FROM _master_catalog")
    
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

# ── PAGE: Redis History ───────────────────────────────────────────────
elif page == "🕒 Redis History":
    st.markdown(
        '<div class="butler-header">'
        "<h1>🕒 Redis Chat History</h1>"
        "<p>View and manage conversational memory</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    
    sessions = agent.list_sessions()
    if not sessions:
        st.info("No chat sessions found in Redis.")
    else:
        # Create a display list for the selectbox
        session_options = {s["session_id"]: f"{s.get('title', '(untitled)')} - {s['session_id'][:8]}" for s in sessions}
        selected_sid = st.selectbox("Select a session to view", options=list(session_options.keys()), format_func=lambda x: session_options[x])
        
        if selected_sid:
            st.divider()
            history = agent.history.get_history(selected_sid)
            
            if not history:
                st.write("This session has no messages.")
            else:
                for msg in history:
                    role = msg.get("role", "unknown")
                    # Map role to cleaner label
                    role_label = "👤 Human" if role == "user" else "🤖 AI" if role == "assistant" else "⚙️ System"
                    
                    with st.container():
                        st.markdown(f"**{role_label}** <small>{msg.get('timestamp', '')}</small>", unsafe_allow_html=True)
                        st.markdown(msg.get("content", ""))
                        st.divider()

# ── PAGE: Vector Collections ──────────────────────────────────────────
elif page == "🧬 Vector Collections":
    st.markdown(
        '<div class="butler-header">'
        "<h1>🧬 Vector Collections</h1>"
        "<p>Inspect Qdrant vector database storage</p>"
        "</div>",
        unsafe_allow_html=True,
    )
    
    try:
        collections = agent.vector_db.list_collections()
        if not collections:
            st.info("No collections found in Qdrant.")
        else:
            selected_col = st.selectbox("Select a collection", collections)
            
            # Get collection details
            info = agent.vector_db.client.get_collection(selected_col)
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Points Count", info.points_count)
            col2.metric("Status", info.status.name)
            col3.metric("Vector Size", info.config.params.vectors.size)
            
            st.write("### Configuration")
            st.json(info.model_dump())

            st.divider()
            st.write("### 📤 Upload New Data")
            st.info("Upload a Zalo or Facebook message export (ZIP) to vectorize it into a new collection.")
            
            uploaded_file = st.file_uploader("Choose a ZIP file", type="zip")
            if uploaded_file is not None:
                if st.button("🚀 Process & Vectorize"):
                    with st.spinner("Extracting and indexing... this may take a minute"):
                        # Use BytesIO to handle the uploaded file
                        from io import BytesIO
                        zip_data = BytesIO(uploaded_file.read())
                        result = agent.ingester.process_zip(zip_data, filename=uploaded_file.name)
                        
                        if result["status"] == "success":
                            st.success(result["message"])
                            st.balloons()
                            st.rerun()
                        elif result["status"] == "skipped":
                            st.warning(result["message"])
                        else:
                            st.error(f"❌ Error: {result['message']}")
            
    except Exception as e:
        st.error(f"Error connecting to Qdrant: {e}")
