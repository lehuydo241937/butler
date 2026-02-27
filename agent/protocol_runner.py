"""
ProtocolRunner — executes multi-step protocols defined as JSON step arrays.

Each step has the shape:
    {
        "id":         str,          # unique step identifier
        "name":       str,          # human-readable label
        "type":       "code_function" | "agent_prompt",
        "function":   str,          # (code_function only) name in FUNCTION_REGISTRY
        "prompt":     str,          # (agent_prompt only) template with {{key}} placeholders
        "params":     dict,         # extra params passed to code functions
        "output_key": str | null    # key in context dict to store this step's output
    }

A shared `context` dict flows through all steps:
  - code_function steps receive context + params and return a value stored at output_key
  - agent_prompt steps have {{key}} tokens resolved from context, call Gemini, and store the reply
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── type alias ──────────────────────────────────────────────────────────────
StepFn = Callable[[Dict[str, Any], Dict[str, Any]], Any]
# (context, params) -> result


class ProtocolRunner:
    """
    Runs a protocol (ordered list of steps) and returns the final context dict.

    Args:
        gemini_client:   google.genai.Client instance (for agent_prompt steps)
        gemini_model:    model name string
        gmail_tools:     GmailTools instance (for email functions)
        secrets:         RedisSecretsManager (for Redis-based state tracking)
        emails_root:     base folder where emails are saved (default: "emails/")
        telegram_bot:    python-telegram-bot Bot instance (for send_telegram_result)
    """

    def __init__(
        self,
        gemini_client,
        gemini_model: str,
        gmail_tools,
        secrets,
        emails_root: str = "emails",
        telegram_bot=None,
    ):
        self.client = gemini_client
        self.model = gemini_model
        self.gmail = gmail_tools
        self.secrets = secrets
        self.emails_root = Path(emails_root)
        self.bot = telegram_bot

        # Registry maps function name → callable(context, params) -> Any
        self._registry: Dict[str, StepFn] = {
            "fetch_emails_by_date": self._fn_fetch_emails_by_date,
            "send_telegram_result": self._fn_send_telegram_result,
        }

    # ── Public API ───────────────────────────────────────────────────────────

    def run(self, protocol: Dict[str, Any], chat_id: int) -> Dict[str, Any]:
        """
        Execute every step in order. Returns the final context dict.
        chat_id is injected into context so steps can reference it.
        """
        context: Dict[str, Any] = {"_chat_id": chat_id}
        steps: List[Dict[str, Any]] = protocol.get("steps", [])

        for step in steps:
            step_id = step.get("id", "?")
            step_name = step.get("name", step_id)
            step_type = step.get("type", "")
            output_key = step.get("output_key")

            logger.info("Protocol '%s' → step '%s' (%s)", protocol["name"], step_name, step_type)

            try:
                if step_type == "code_function":
                    fn_name = step.get("function", "")
                    fn = self._registry.get(fn_name)
                    if fn is None:
                        raise RuntimeError(f"Unknown function '{fn_name}' in step '{step_id}'")
                    result = fn(context, step.get("params", {}))

                elif step_type == "agent_prompt":
                    prompt_template = step.get("prompt", "")
                    prompt = self._resolve_template(prompt_template, context)
                    result = self._call_gemini(prompt)

                else:
                    raise RuntimeError(f"Unknown step type '{step_type}' in step '{step_id}'")

                if output_key:
                    context[output_key] = result

            except Exception as exc:
                logger.exception("Protocol step '%s' failed: %s", step_name, exc)
                context[f"_error_{step_id}"] = str(exc)
                # Propagate so the caller can surface the error to Telegram
                raise RuntimeError(f"Step '{step_name}' failed: {exc}") from exc

        return context

    # ── Template resolver ────────────────────────────────────────────────────

    @staticmethod
    def _resolve_template(template: str, context: Dict[str, Any]) -> str:
        """Replace {{key}} placeholders with context values (JSON-serialised if not str)."""
        def replacer(m):
            key = m.group(1).strip()
            val = context.get(key, "")
            if isinstance(val, (dict, list)):
                return json.dumps(val, ensure_ascii=False, default=str)
            return str(val)

        return re.sub(r"\{\{(\w+)\}\}", replacer, template)

    # ── Gemini helper ────────────────────────────────────────────────────────

    def _call_gemini(self, prompt: str) -> str:
        """Call Gemini with a standalone prompt (not via agent.chat, no history)."""
        from google.genai import types
        response = self.client.models.generate_content(
            model=self.model,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
        )
        return response.text or ""

    # ── Built-in code functions ──────────────────────────────────────────────

    def _fn_fetch_emails_by_date(
        self, context: Dict[str, Any], params: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Determine which dates are missing (between last-fetched and yesterday),
        fetch emails for those dates from Gmail, save them to disk.
        Returns a list of all fetched email dicts (subject, from, snippet, body).
        """
        # ── 1. Determine date range to fetch ────────────────────────────────
        today = date.today()
        yesterday = today - timedelta(days=1)

        # Redis set stores fetched dates as "YYYY-MM-DD" strings
        REDIS_KEY = "gmail:fetched_dates"
        fetched_raw = self.secrets.r.smembers(REDIS_KEY) or set()
        fetched_dates = {d for d in fetched_raw}

        # Compute last fetched date from Redis (oldest we need to check from)
        last_fetch_str = self.secrets.get_secret("gmail_last_digest_run")
        if last_fetch_str:
            try:
                start_date = datetime.fromisoformat(last_fetch_str).date()
            except ValueError:
                start_date = yesterday
        else:
            start_date = yesterday  # first run: only yesterday

        # Collect dates that are missing
        missing_dates: List[date] = []
        cursor_date = start_date
        while cursor_date <= yesterday:
            if cursor_date.isoformat() not in fetched_dates:
                missing_dates.append(cursor_date)
            cursor_date += timedelta(days=1)

        if not missing_dates:
            logger.info("No missing email dates to fetch.")
            return []

        all_emails: List[Dict[str, Any]] = []

        for fetch_date in missing_dates:
            date_str = fetch_date.isoformat()
            next_date_str = (fetch_date + timedelta(days=1)).isoformat()

            # Gmail date query: messages received on this specific day
            query = f"after:{date_str} before:{next_date_str}"
            logger.info("Fetching emails for %s with query: %s", date_str, query)

            emails = self.gmail.search_emails(query=query, max_results=50)

            # Filter out API errors
            valid_emails = [e for e in emails if "error" not in e]

            # Fetch full body for each email
            enriched = []
            for summary in valid_emails:
                try:
                    full = self.gmail.get_email(summary["id"])
                    if "error" not in full:
                        enriched.append(full)
                except Exception as exc:
                    logger.warning("Could not fetch body for %s: %s", summary["id"], exc)
                    enriched.append(summary)  # fall back to summary

            # ── Save to disk ─────────────────────────────────────────────
            day_folder = self.emails_root / date_str
            day_folder.mkdir(parents=True, exist_ok=True)

            for email in enriched:
                file_path = day_folder / f"{email['id']}.json"
                if not file_path.exists():
                    file_path.write_text(
                        json.dumps(email, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8",
                    )

            # Mark date as fetched in Redis
            self.secrets.r.sadd(REDIS_KEY, date_str)
            all_emails.extend(enriched)
            logger.info("Saved %d emails for %s", len(enriched), date_str)

        # Update last-run timestamp
        self.secrets.set_secret("gmail_last_digest_run", today.isoformat())

        return all_emails

    def _fn_send_telegram_result(
        self, context: Dict[str, Any], params: Dict[str, Any]
    ) -> None:
        """
        Send a message to Telegram. Reads content from context[message_key].
        This is called synchronously from a thread, so we use asyncio.run_coroutine_threadsafe.
        """
        if self.bot is None:
            logger.warning("send_telegram_result: no bot instance available.")
            return

        message_key = params.get("message_key", "summary")
        header = params.get("header", "")
        text = context.get(message_key, "(no content)")
        chat_id = context.get("_chat_id")

        if not chat_id:
            logger.warning("send_telegram_result: no chat_id in context.")
            return

        full_text = f"{header}\n\n{text}" if header else text

        import asyncio
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                self.bot.send_message(chat_id=chat_id, text=full_text, parse_mode="Markdown")
            )
        finally:
            loop.close()
