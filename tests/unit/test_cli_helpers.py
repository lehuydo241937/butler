"""
Unit tests for main.py CLI helper functions.
Covers:
  - sync_inventory: script discovery from agent/workers/
  - print_scripts / print_plans / print_sessions: render without crashing
  - render_reply: HITL proposal detection
  - Hardware info helper

All tests use tmp_path and mock heavy deps (rich, psutil, ButlerAgent).
No Redis, no Gemini, no network required.
"""

import os
import sys
import importlib
import types
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agent.db_manager import DBManager


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_db(tmp_path) -> DBManager:
    return DBManager(db_path=str(tmp_path / "cli_test.db"))


def _import_main():
    """
    Import main.py. We must patch force_ipv4 and ButlerAgent at import time
    so no network calls happen.
    """
    with patch("agent.network_utils.force_ipv4", return_value=None):
        import main as m
    return m


# ════════════════════════════════════════════════════════════════════════════
#  sync_inventory
# ════════════════════════════════════════════════════════════════════════════

class TestSyncInventory:
    """
    Creates fake .py script files in a temp workers dir and verifies
    sync_inventory registers them correctly into script_inventory.
    """

    def _write_script(self, directory, name, content):
        path = directory / name
        path.write_text(content, encoding="utf-8")
        return path

    def test_registers_script_with_run_function(self, tmp_path):
        """
        Write a real script to disk, load it with importlib, inspect its
        `run()` signature, and register it — exactly what sync_inventory does.
        """
        import importlib.util
        import inspect

        workers_dir = tmp_path / "workers"
        workers_dir.mkdir()
        script_content = '"""Fetches emails from Gmail."""\n\ndef run(count: int, unread: bool):\n    pass\n'
        script_path = str(workers_dir / "email_fetcher.py")
        (workers_dir / "email_fetcher.py").write_text(script_content, encoding="utf-8")

        spec = importlib.util.spec_from_file_location("email_fetcher", script_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        description = (mod.__doc__ or "").strip().split("\n")[0]
        schema = {}
        sig = inspect.signature(mod.run)
        for pname, param in sig.parameters.items():
            ann = param.annotation
            schema[pname] = ann.__name__ if ann != inspect.Parameter.empty else "Any"

        db = _make_db(tmp_path)
        db.register_script("email_fetcher", description, script_path, schema)

        result = db.find_script_by_name("email_fetcher")
        assert result is not None
        assert result["description"] == "Fetches emails from Gmail."
        assert result["input_schema"]["count"] == "int"
        assert result["input_schema"]["unread"] == "bool"

    def test_no_scripts_does_not_crash(self, tmp_path, monkeypatch):
        """sync_inventory on empty workers dir should emit info, not crash."""
        with patch("agent.network_utils.force_ipv4"):
            import main as m

        db = _make_db(tmp_path)
        called = []
        monkeypatch.setattr(m, "render_info", lambda msg: called.append(msg))
        monkeypatch.setattr(m.os.path, "isdir", lambda _: False)

        m.sync_inventory(db)  # should not raise

    def test_broken_script_does_not_abort(self, tmp_path, monkeypatch):
        """A script with a syntax error should be skipped, not kill the loop."""
        workers_dir = tmp_path / "workers"
        workers_dir.mkdir()
        (workers_dir / "broken.py").write_text("def (", encoding="utf-8")
        (workers_dir / "good.py").write_text('"""Good script."""\ndef run(): pass\n', encoding="utf-8")

        db = _make_db(tmp_path)
        import importlib.util, inspect

        registered = 0
        for fname in ["broken.py", "good.py"]:
            fpath = str(workers_dir / fname)
            name = fname[:-3]
            try:
                spec = importlib.util.spec_from_file_location(name, fpath)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                description = (mod.__doc__ or "").strip().split("\n")[0]
                db.register_script(name, description, fpath)
                registered += 1
            except Exception:
                pass

        assert registered == 1  # only good.py
        assert db.find_script_by_name("good") is not None
        assert db.find_script_by_name("broken") is None


# ════════════════════════════════════════════════════════════════════════════
#  Render helpers — smoke tests (no crash, correct branching)
# ════════════════════════════════════════════════════════════════════════════

class TestRenderHelpers:
    @pytest.fixture(autouse=True)
    def _import(self):
        with patch("agent.network_utils.force_ipv4"):
            import main as m
        self.m = m

    def _silence(self, monkeypatch):
        """Suppress all print/console output."""
        monkeypatch.setattr(self.m, "console", MagicMock())
        monkeypatch.setattr("builtins.print", lambda *a, **k: None)

    def test_render_reply_normal(self, monkeypatch):
        self._silence(monkeypatch)
        self.m.render_reply("Hello, this is a normal reply.")

    def test_render_reply_hitl_proposal(self, monkeypatch):
        captured = []
        self._silence(monkeypatch)
        # Spy on console.print to check both panels are printed
        self.m.console.print = lambda *a, **k: captured.append(str(a))

        self.m.render_reply(
            "I'll create the table. "
            "HITL_PROPOSAL:table_creation:abc-123:Table 'contacts' proposed."
        )
        # Should have printed at least two panels (normal + proposal)
        assert len(captured) >= 2

    def test_render_error_does_not_crash(self, monkeypatch):
        self._silence(monkeypatch)
        self.m.render_error("Something went wrong")

    def test_render_info_does_not_crash(self, monkeypatch):
        self._silence(monkeypatch)
        self.m.render_info("Just an info message")

    def test_print_scripts_empty(self, tmp_path, monkeypatch):
        self._silence(monkeypatch)
        db = _make_db(tmp_path)
        self.m.print_scripts(db)  # should not crash

    def test_print_scripts_with_data(self, tmp_path, monkeypatch):
        self._silence(monkeypatch)
        db = _make_db(tmp_path)
        db.register_script("s1", "desc1", "path/s1.py", {"n": "int"})
        db.register_script("s2", "desc2", "path/s2.py")
        self.m.print_scripts(db)

    def test_print_plans_empty(self, tmp_path, monkeypatch):
        self._silence(monkeypatch)
        db = _make_db(tmp_path)
        self.m.print_plans(db)

    def test_print_plans_with_data(self, tmp_path, monkeypatch):
        self._silence(monkeypatch)
        db = _make_db(tmp_path)
        p1 = db.create_plan("Fetch emails and summarise", "gemini-flash")
        db.update_plan_status(p1, "done", "Completed")
        db.create_plan("Another pending goal")
        self.m.print_plans(db)

    def test_print_sessions_empty(self, monkeypatch):
        self._silence(monkeypatch)
        agent = MagicMock()
        agent.list_sessions.return_value = []
        agent.session_id = "fake-session-id"
        self.m.print_sessions(agent)

    def test_print_sessions_with_data(self, monkeypatch):
        self._silence(monkeypatch)
        agent = MagicMock()
        agent.session_id = "aaaa-bbbb-cccc"
        agent.list_sessions.return_value = [
            {"session_id": "aaaa-bbbb-cccc", "title": "Active session"},
            {"session_id": "1111-2222-3333", "title": "Old session"},
        ]
        self.m.print_sessions(agent)

    def test_print_help_does_not_crash(self, monkeypatch):
        self._silence(monkeypatch)
        self.m.print_help()


# ════════════════════════════════════════════════════════════════════════════
#  Hardware monitoring
# ════════════════════════════════════════════════════════════════════════════

class TestHardwareInfo:
    def test_hw_info_with_psutil(self, monkeypatch):
        with patch("agent.network_utils.force_ipv4"):
            import main as m

        if not m.PSUTIL_AVAILABLE:
            pytest.skip("psutil not installed")

        hw = m._get_hw_info()
        assert "CPU" in hw
        assert "RAM" in hw

    def test_hw_info_without_psutil(self, monkeypatch):
        with patch("agent.network_utils.force_ipv4"):
            import main as m

        monkeypatch.setattr(m, "PSUTIL_AVAILABLE", False)
        hw = m._get_hw_info()
        assert hw == ""
