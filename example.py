"""
Quick smoke-test: create a session, add messages, reload history.
Run after 'docker compose up -d' and 'pip install -r requirements.txt'.
"""

from chat_history import RedisChatHistory


def main():
    history = RedisChatHistory()

    # 1. Check connectivity
    if not history.ping():
        print("[FAIL] Cannot reach Redis - is the container running?")
        return
    print("[OK] Connected to Redis\n")

    # 2. Create a session
    sid = history.create_session(title="Demo conversation")
    print(f"[NEW] Created session: {sid}")

    # 3. Add a few messages
    history.add_message(sid, "system", "You are a helpful assistant.")
    history.add_message(sid, "user", "What is Redis?")
    history.add_message(
        sid,
        "assistant",
        "Redis is an open-source, in-memory data store used as a database, "
        "cache, and message broker.",
    )
    history.add_message(sid, "user", "How does it persist data?")
    history.add_message(
        sid,
        "assistant",
        "Redis supports RDB snapshots and AOF (append-only file) for persistence.",
    )
    print(f"[MSG] Added {history.count_messages(sid)} messages\n")

    # 4. Load full history
    print("-- Full history ------------------------------------")
    for msg in history.get_history(sid):
        print(f"  [{msg['role'].upper():>9}]  {msg['content']}")

    # 5. Load last 2 messages only
    print("\n-- Last 2 messages ---------------------------------")
    for msg in history.get_history(sid, limit=2):
        print(f"  [{msg['role'].upper():>9}]  {msg['content']}")

    # 6. List sessions
    print("\n-- All sessions ------------------------------------")
    for s in history.list_sessions():
        print(f"  {s['session_id']}  title={s.get('title', '(none)')}")

    # 7. Cleanup demo session
    history.delete_session(sid)
    print(f"\n[DEL] Deleted demo session {sid}")


if __name__ == "__main__":
    main()
