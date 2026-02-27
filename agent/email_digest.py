"""
Email Digest Protocol definition.

This module defines the step list for the built-in 'email_daily_digest' protocol
and a helper to register it in the database.
"""

from __future__ import annotations

from typing import Any, Dict, List

# ── Protocol metadata ────────────────────────────────────────────────────────

PROTOCOL_NAME = "email_daily_digest"
PROTOCOL_DESCRIPTION = (
    "Fetches unread emails since last run, saves them by date, filters spam/ads, "
    "and sends a Telegram summary of action items for the day."
)
PROTOCOL_CRON = "0 6 * * *"  # 6:00 AM every day (server local time / UTC)

# ── Step definitions ─────────────────────────────────────────────────────────

STEPS: List[Dict[str, Any]] = [
    {
        "id": "fetch_emails",
        "name": "Fetch new emails by date",
        "type": "code_function",
        "function": "fetch_emails_by_date",
        "params": {},
        "output_key": "emails",
    },
    {
        "id": "filter_spam",
        "name": "Filter spam and advertisements",
        "type": "agent_prompt",
        "prompt": (
            "You are an email assistant. "
            "Below is a JSON list of emails received recently.\n\n"
            "{{emails}}\n\n"
            "Task: Filter out all spam, promotional newsletters, advertisements, automated "
            "notifications (e.g. account alerts, shipping updates with no action needed), "
            "and social-media digests.\n"
            "Return ONLY the emails that require the user's attention or action as a JSON array "
            "with the same structure. If all emails are spam/promo, return an empty JSON array []."
        ),
        "output_key": "filtered_emails",
    },
    {
        "id": "summarize",
        "name": "Extract action items",
        "type": "agent_prompt",
        "prompt": (
            "You are an executive assistant. "
            "Below are emails that need the user's attention today:\n\n"
            "{{filtered_emails}}\n\n"
            "Task: Produce a concise Telegram-friendly daily digest.\n"
            "Format rules:\n"
            "- Start with a greeting line: '📬 *Good morning! Here is your email digest for today.*'\n"
            "- Then list each item as: '• [Sender] — [one-line action or key info]'\n"
            "- Group related items under a short bold header if there are >3 from the same topic.\n"
            "- Close with a summary line: 'You have N emails needing attention.'\n"
            "- Keep the whole message under 30 lines.\n"
            "- If filtered_emails is empty or [], write: "
            "'📬 *Good morning! No new emails needing your attention today.*'"
        ),
        "output_key": "summary",
    },
    {
        "id": "send_digest",
        "name": "Send digest via Telegram",
        "type": "code_function",
        "function": "send_telegram_result",
        "params": {
            "message_key": "summary",
            "header": "",
        },
        "output_key": None,
    },
]


# ── Registration helper ───────────────────────────────────────────────────────

def register(db_manager, chat_id: int) -> str:
    """
    Register the email_daily_digest protocol in the database.
    Returns a message string suitable for the agent to relay to the user.
    """
    existing = db_manager.get_protocol_by_name(PROTOCOL_NAME)
    if existing:
        return (
            f"The '{PROTOCOL_NAME}' protocol is already registered "
            f"(cron: {existing['cron_expression']}, status: {existing['status']})."
        )

    protocol_id = db_manager.add_protocol(
        name=PROTOCOL_NAME,
        description=PROTOCOL_DESCRIPTION,
        steps=STEPS,
        cron_expression=PROTOCOL_CRON,
        chat_id=chat_id,
    )
    return (
        f"✅ Daily email digest scheduled! (Protocol ID: {protocol_id})\n"
        f"It will run every day at 6:00 AM and send you a Telegram summary."
    )
