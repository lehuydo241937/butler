"""
Kuro OS — Interactive CLI Command Center
========================================
A rich terminal dashboard for the Butler AI agent.

Commands
--------
/new [title]        Create a new session
/sessions           List all saved sessions
/switch <id>        Switch to a session (paste first 8+ chars)
/history            Show current session history
/list-scripts       List all scripts in the inventory
/sync-inventory     Scan and register scripts in agent/workers/
/plans              Show recent plans and their status
/help               Show this help message
/quit               Exit

UI Color Scheme:
  Green  → Success / done
  Yellow → Pending / planning
  Red    → Failure / error
  Cyan   → Info / labels
"""

from agent.network_utils import force_ipv4

force_ipv4()

import os
import sys
import platform
from datetime import datetime
from typing import Optional

# ── Rich imports ────────────────────────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.live import Live
    from rich.spinner import Spinner
    from rich.columns import Columns
    from rich.rule import Rule
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# ── Prompt Toolkit imports ───────────────────────────────────────────────────
try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import InMemoryHistory
    from prompt_toolkit.styles import Style
    from prompt_toolkit.formatted_text import HTML
    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False

# ── psutil for hardware monitoring ──────────────────────────────────────────
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from agent import ButlerAgent
from agent.db_manager import DBManager

# ── Console singleton ────────────────────────────────────────────────────────
console = Console() if RICH_AVAILABLE else None


# ════════════════════════════════════════════════════════════════════════════
#  Rendering Helpers
# ════════════════════════════════════════════════════════════════════════════

def _get_hw_info() -> str:
    """Returns a compact hardware status string."""
    if not PSUTIL_AVAILABLE:
        return ""
    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    mem_used_gb = mem.used / (1024 ** 3)
    mem_total_gb = mem.total / (1024 ** 3)
    return f"CPU {cpu:.0f}%  RAM {mem_used_gb:.1f}/{mem_total_gb:.1f} GB"


def print_banner():
    """Renders the startup banner panel."""
    if not RICH_AVAILABLE:
        print("=" * 60)
        print("  Kuro OS — CLI Command Center")
        print("  Type /help for commands, /quit to exit")
        print("=" * 60)
        return

    hw = _get_hw_info()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")

    banner_text = Text.assemble(
        ("  🖤  KURO OS", "bold white"),
        ("  —  Command Center\n", "dim white"),
        ("  Model: ", "dim cyan"), ("gemini-3-flash-preview", "cyan"),
        ("  |  Time: ", "dim cyan"), (ts, "cyan"),
    )
    if hw:
        banner_text.append(f"\n  Hardware: {hw}", style="dim yellow")

    console.print(Panel(
        banner_text,
        title="[bold magenta]◆ BUTLER AI[/bold magenta]",
        subtitle="[dim]Type /help for commands[/dim]",
        border_style="magenta",
        padding=(0, 2),
    ))
    console.print()


def print_sessions(agent: ButlerAgent) -> None:
    """Renders sessions as a Rich table."""
    sessions = agent.list_sessions()
    if not sessions:
        if RICH_AVAILABLE:
            console.print("  [dim](no sessions yet)[/dim]\n")
        else:
            print("  (no sessions yet)\n")
        return

    if RICH_AVAILABLE:
        table = Table(
            "ID", "Title", "Active",
            title="[bold cyan]Sessions[/bold cyan]",
            box=box.SIMPLE_HEAD,
            border_style="cyan",
            show_lines=False,
        )
        for s in sessions:
            is_active = s["session_id"] == agent.session_id
            marker = "[green]●[/green]" if is_active else ""
            table.add_row(
                f"[dim]{s['session_id'][:10]}…[/dim]",
                s.get("title", "(untitled)"),
                marker,
            )
        console.print(table)
        console.print()
    else:
        for s in sessions:
            marker = " <--" if s["session_id"] == agent.session_id else ""
            print(f"  {s['session_id'][:8]}...  {s.get('title', '(untitled)')}{marker}")
        print()


def print_scripts(db: DBManager) -> None:
    """Renders the script_inventory table."""
    scripts = db.get_active_scripts()
    if not scripts:
        if RICH_AVAILABLE:
            console.print("  [yellow]No scripts registered yet. Use /sync-inventory to scan.[/yellow]\n")
        else:
            print("  No scripts registered yet.\n")
        return

    if RICH_AVAILABLE:
        table = Table(
            "Name", "Description", "Path", "Input Schema",
            title="[bold green]Script Inventory[/bold green]",
            box=box.SIMPLE_HEAD,
            border_style="green",
            show_lines=True,
        )
        for s in scripts:
            schema_str = ", ".join(f"{k}:{v}" for k, v in s["input_schema"].items()) or "—"
            table.add_row(
                f"[bold]{s['name']}[/bold]",
                s.get("description", "—"),
                f"[dim]{s['file_path']}[/dim]",
                schema_str,
            )
        console.print(table)
        console.print()
    else:
        for s in scripts:
            print(f"  [{s['name']}] {s.get('description', '')} → {s['file_path']}")
        print()


def print_plans(db: DBManager) -> None:
    """Renders recent plans and their steps."""
    plans = db.list_plans()
    if not plans:
        if RICH_AVAILABLE:
            console.print("  [dim]No plans recorded yet.[/dim]\n")
        else:
            print("  No plans recorded yet.\n")
        return

    STATUS_COLOR = {
        "pending": "yellow",
        "running": "cyan",
        "done": "green",
        "failed": "red",
    }

    if RICH_AVAILABLE:
        table = Table(
            "#", "Goal", "Status", "Model", "Created",
            title="[bold magenta]Plans[/bold magenta]",
            box=box.SIMPLE_HEAD,
            border_style="magenta",
            show_lines=False,
        )
        for i, p in enumerate(plans[:10], 1):
            color = STATUS_COLOR.get(p["status"], "white")
            table.add_row(
                str(i),
                p["goal"][:55] + ("…" if len(p["goal"]) > 55 else ""),
                f"[{color}]{p['status']}[/{color}]",
                p.get("assigned_model") or "—",
                p["created_at"][:16],
            )
        console.print(table)
        console.print()
    else:
        for p in plans[:10]:
            print(f"  [{p['status'].upper()}] {p['goal'][:60]}")
        print()


def render_reply(reply: str) -> None:
    """Renders Kuro's reply in a styled panel."""
    if RICH_AVAILABLE:
        # Parse HITL proposals to highlight them
        if "HITL_PROPOSAL:" in reply:
            parts = reply.split("HITL_PROPOSAL:")
            clean = parts[0].strip()
            proposal_line = "HITL_PROPOSAL:" + parts[1].split(":")[0] + ":…"
            console.print(Panel(
                Text(clean),
                title="[bold green]◆ Kuro[/bold green]",
                border_style="green",
                padding=(0, 2),
            ))
            console.print(Panel(
                Text(reply.partition("HITL_PROPOSAL:")[2], style="yellow"),
                title="[bold yellow]⚠ HITL Proposal[/bold yellow]",
                border_style="yellow",
                padding=(0, 2),
            ))
        else:
            console.print(Panel(
                Text(reply),
                title="[bold green]◆ Kuro[/bold green]",
                border_style="green",
                padding=(0, 2),
            ))
    else:
        print(f"\nKuro > {reply}\n")


def render_error(msg: str) -> None:
    if RICH_AVAILABLE:
        console.print(Panel(
            Text(msg, style="bold red"),
            title="[bold red]✖ Error[/bold red]",
            border_style="red",
            padding=(0, 2),
        ))
    else:
        print(f"\n[ERROR] {msg}\n")


def render_info(msg: str) -> None:
    if RICH_AVAILABLE:
        console.print(f"  [cyan]ℹ[/cyan]  {msg}\n")
    else:
        print(f"  {msg}\n")


# ════════════════════════════════════════════════════════════════════════════
#  Session Management
# ════════════════════════════════════════════════════════════════════════════

def choose_or_create_session(agent: ButlerAgent) -> None:
    """On startup: let the user pick a session or create a new one."""
    sessions = agent.list_sessions()
    if not sessions:
        render_info("No sessions found — starting a new one.")
        return

    print_sessions(agent)

    if PROMPT_TOOLKIT_AVAILABLE:
        try:
            choice = PromptSession().prompt(
                HTML("<ansicyan>Resume session ID prefix (Enter for new): </ansicyan>")
            ).strip()
        except (EOFError, KeyboardInterrupt):
            choice = ""
    else:
        choice = input("Resume session ID prefix (Enter for new): ").strip()

    if choice:
        match = [s for s in sessions if s["session_id"].startswith(choice)]
        if match:
            agent.switch_session(match[0]["session_id"])
            title = match[0].get("title", "(untitled)")
            render_info(f"Resumed session: [bold]{title}[/bold]" if RICH_AVAILABLE else f"Resumed: {title}")
            recent = agent.get_current_history()[-5:]
            if recent and RICH_AVAILABLE:
                console.print(Rule("[dim]Recent messages[/dim]", style="dim"))
                for msg in recent:
                    role_style = "green" if msg["role"] == "assistant" else "cyan"
                    console.print(
                        f"  [{role_style}]{msg['role'].upper():>9}[/{role_style}]  "
                        f"[dim]{msg['content'][:120]}[/dim]"
                    )
                console.print()
        else:
            render_info(f"No session matching '{choice}' — starting new.")
    else:
        render_info("Starting a new session.")


# ════════════════════════════════════════════════════════════════════════════
#  Inventory Sync
# ════════════════════════════════════════════════════════════════════════════

def sync_inventory(db: DBManager) -> None:
    """
    Scan agent/workers/*.py for Python scripts and auto-register them.
    Reads the module docstring as the description and inspects top-level
    functions for a simple input schema heuristic.
    """
    import importlib.util
    import inspect

    workers_dir = os.path.join(os.path.dirname(__file__), "agent", "workers")
    if not os.path.isdir(workers_dir):
        render_info("agent/workers/ directory not found. Create scripts there first.")
        return

    py_files = [f for f in os.listdir(workers_dir) if f.endswith(".py") and not f.startswith("_")]
    if not py_files:
        render_info("No scripts found in agent/workers/")
        return

    registered = 0
    for fname in py_files:
        fpath = os.path.join(workers_dir, fname)
        name = fname[:-3]
        try:
            spec = importlib.util.spec_from_file_location(name, fpath)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            description = (mod.__doc__ or "").strip().split("\n")[0]
            # Infer input schema from `run()` function if present
            schema = {}
            if hasattr(mod, "run"):
                sig = inspect.signature(mod.run)
                for pname, param in sig.parameters.items():
                    ann = param.annotation
                    schema[pname] = ann.__name__ if ann != inspect.Parameter.empty else "Any"

            db.register_script(name=name, description=description, file_path=fpath, input_schema=schema)
            registered += 1
            if RICH_AVAILABLE:
                console.print(f"  [green]✔[/green] Registered: [bold]{name}[/bold]")
            else:
                print(f"  Registered: {name}")
        except Exception as e:
            if RICH_AVAILABLE:
                console.print(f"  [red]✖[/red] Failed to load {fname}: {e}")
            else:
                print(f"  Failed: {fname} — {e}")

    render_info(f"Sync complete — {registered}/{len(py_files)} scripts registered.")


# ════════════════════════════════════════════════════════════════════════════
#  Help Panel
# ════════════════════════════════════════════════════════════════════════════

def print_help() -> None:
    if RICH_AVAILABLE:
        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        table.add_column("Command", style="bold cyan", no_wrap=True)
        table.add_column("Description", style="white")
        commands = [
            ("/new [title]",      "Create a new session"),
            ("/sessions",         "List all saved sessions"),
            ("/switch <id>",      "Switch to a session by ID prefix"),
            ("/history",          "Show current session history"),
            ("/list-scripts",     "Show the script inventory"),
            ("/sync-inventory",   "Scan agent/workers/ and register scripts"),
            ("/plans",            "Show recent task plans"),
            ("/help",             "Show this help message"),
            ("/quit",             "Exit Kuro OS"),
        ]
        for cmd, desc in commands:
            table.add_row(cmd, desc)
        console.print(Panel(table, title="[bold cyan]Commands[/bold cyan]", border_style="cyan"))
        console.print()
    else:
        print("  /new [title]       Create a new session")
        print("  /sessions          List all sessions")
        print("  /switch <id>       Switch session")
        print("  /history           Show session messages")
        print("  /list-scripts      Show script inventory")
        print("  /sync-inventory    Register scripts from agent/workers/")
        print("  /plans             Show recent plans")
        print("  /quit              Exit")
        print()


# ════════════════════════════════════════════════════════════════════════════
#  Main Loop
# ════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print_banner()

    try:
        agent = ButlerAgent()
        db = agent.db  # reuse the same DBManager instance
    except ConnectionError as e:
        render_error(str(e))
        return
    except ValueError as e:
        render_error(str(e))
        return

    choose_or_create_session(agent)

    # ── Set up prompt_toolkit session ────────────────────────────────────
    if PROMPT_TOOLKIT_AVAILABLE:
        pt_style = Style.from_dict({
            "prompt": "bold cyan",
        })
        pt_session = PromptSession(history=InMemoryHistory(), style=pt_style)

    def get_input() -> str:
        if PROMPT_TOOLKIT_AVAILABLE:
            sid_short = agent.session_id[:6]
            return pt_session.prompt(HTML(f"<ansicyan>you@kuro</ansicyan>[<ansimagenta>{sid_short}</ansimagenta>]<ansicyan> » </ansicyan>")).strip()
        else:
            return input("You > ").strip()

    # ── Main loop ────────────────────────────────────────────────────────
    while True:
        try:
            user_input = get_input()
        except (EOFError, KeyboardInterrupt):
            if RICH_AVAILABLE:
                console.print("\n[dim]Goodbye![/dim]\n")
            else:
                print("\nGoodbye!")
            break

        if not user_input:
            continue

        # ── Commands ─────────────────────────────────────────────────────
        if user_input.startswith("/"):
            cmd = user_input.split()
            command = cmd[0].lower()

            if command == "/quit":
                if RICH_AVAILABLE:
                    console.print("[dim]Goodbye![/dim]\n")
                else:
                    print("Goodbye!")
                break

            elif command == "/new":
                title = " ".join(cmd[1:]) or None
                agent.new_session(title=title)
                render_info(f"New session: [bold]{agent.session_id[:10]}…[/bold]")

            elif command == "/sessions":
                print_sessions(agent)

            elif command == "/switch":
                if len(cmd) < 2:
                    render_info("Usage: /switch <session-id-prefix>")
                else:
                    sessions = agent.list_sessions()
                    match = [s for s in sessions if s["session_id"].startswith(cmd[1])]
                    if match:
                        agent.switch_session(match[0]["session_id"])
                        render_info(f"Switched to {agent.session_id[:10]}…")
                    else:
                        render_error(f"No session matching '{cmd[1]}'")

            elif command == "/history":
                if RICH_AVAILABLE:
                    console.print(Rule("[dim]Session History[/dim]", style="dim"))
                for msg in agent.get_current_history():
                    role = msg["role"].upper()
                    content = msg["content"][:200]
                    if RICH_AVAILABLE:
                        r_style = "green" if msg["role"] == "assistant" else "cyan"
                        console.print(f"  [{r_style}]{role:>9}[/{r_style}]  [dim]{content}[/dim]")
                    else:
                        print(f"  [{role:>9}]  {content}")
                if RICH_AVAILABLE:
                    console.print()

            elif command == "/list-scripts":
                print_scripts(db)

            elif command == "/sync-inventory":
                sync_inventory(db)

            elif command == "/plans":
                print_plans(db)

            elif command == "/help":
                print_help()

            else:
                render_error(f"Unknown command: {command}  (type /help)")

            continue

        # ── Chat ───────────────────────────────────────────────────────────
        if RICH_AVAILABLE:
            with console.status("[yellow]Kuro is thinking…[/yellow]", spinner="dots"):
                try:
                    reply = agent.chat(user_input)
                except Exception as e:
                    render_error(str(e))
                    continue
        else:
            try:
                reply = agent.chat(user_input)
            except Exception as e:
                render_error(str(e))
                continue

        render_reply(reply)


if __name__ == "__main__":
    main()
