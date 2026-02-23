"""
Butler CLI — interactive terminal chat with Redis memory.

Commands
--------
/new            Create a new session
/sessions       List all saved sessions
/switch <id>    Switch to a session (paste the first 8+ chars)
/history        Show current session history
/quit           Exit
"""

from agent import ButlerAgent


def print_sessions(agent: ButlerAgent) -> None:
    """Pretty-print session list."""
    sessions = agent.list_sessions()
    if not sessions:
        print("  (no sessions yet)")
        return
    for s in sessions:
        marker = " ◀" if s["session_id"] == agent.session_id else ""
        title = s.get("title", "(untitled)")
        print(f"  {s['session_id'][:8]}…  {title}{marker}")


def choose_or_create_session(agent: ButlerAgent) -> None:
    """On startup: let the user pick a session or create a new one."""
    sessions = agent.list_sessions()
    if not sessions:
        print("No sessions found — starting a new one.\n")
        return

    print("Existing sessions:")
    print_sessions(agent)
    print()
    choice = input("Enter session ID prefix to resume (or press Enter for new): ").strip()

    if choice:
        # Find matching session
        match = [s for s in sessions if s["session_id"].startswith(choice)]
        if match:
            agent.switch_session(match[0]["session_id"])
            title = match[0].get("title", "(untitled)")
            print(f"Resumed session: {title}\n")

            # Show recent history
            recent = agent.get_current_history()[-5:]
            if recent:
                print("— Recent messages —")
                for msg in recent:
                    role = msg["role"].upper()
                    print(f"  [{role:>9}]  {msg['content'][:120]}")
                print()
        else:
            print(f"No session matching '{choice}' — starting a new one.\n")
    else:
        print("Starting a new session.\n")


def main() -> None:
    print("=" * 60)
    print("  Butler AI — Chat with Redis Memory")
    print("  Type /quit to exit, /help for commands")
    print("=" * 60)
    print()

    try:
        agent = ButlerAgent()
    except ConnectionError as e:
        print(f"[ERROR] {e}")
        return
    except ValueError as e:
        print(f"[ERROR] {e}")
        return

    choose_or_create_session(agent)

    while True:
        try:
            user_input = input("You > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        # ── Commands ────────────────────────────────────────────────
        if user_input.startswith("/"):
            cmd = user_input.split()
            command = cmd[0].lower()

            if command == "/quit":
                print("Goodbye!")
                break
            elif command == "/new":
                title = " ".join(cmd[1:]) or None
                agent.new_session(title=title)
                print(f"New session created: {agent.session_id[:8]}…\n")
            elif command == "/sessions":
                print_sessions(agent)
                print()
            elif command == "/switch":
                if len(cmd) < 2:
                    print("Usage: /switch <session-id-prefix>\n")
                else:
                    try:
                        agent.switch_session(cmd[1])
                        print(f"Switched to {agent.session_id[:8]}…\n")
                    except ValueError as e:
                        # Try prefix match
                        sessions = agent.list_sessions()
                        match = [s for s in sessions if s["session_id"].startswith(cmd[1])]
                        if match:
                            agent.switch_session(match[0]["session_id"])
                            print(f"Switched to {agent.session_id[:8]}…\n")
                        else:
                            print(f"  {e}\n")
            elif command == "/history":
                for msg in agent.get_current_history():
                    role = msg["role"].upper()
                    print(f"  [{role:>9}]  {msg['content'][:200]}")
                print()
            elif command == "/help":
                print("  /new [title]     Create a new session")
                print("  /sessions        List all sessions")
                print("  /switch <id>     Switch session")
                print("  /history         Show session messages")
                print("  /quit            Exit")
                print()
            else:
                print(f"  Unknown command: {command}  (type /help)\n")
            continue

        # ── Chat ────────────────────────────────────────────────────
        try:
            reply = agent.chat(user_input)
            print(f"\nButler > {reply}\n")
        except Exception as e:
            print(f"\n[ERROR] {e}\n")


if __name__ == "__main__":
    main()
