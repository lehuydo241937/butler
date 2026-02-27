"""
Gmail tools for ButlerAgent.

All OAuth credentials live in Redis:
  - gmail_credentials  : the raw JSON from credentials.json (OAuth2 client secret)
  - gmail_token        : the OAuth2 token JSON (written back after first login)

No credential files are ever required on disk.
"""

from __future__ import annotations

import base64
import json
import re
import logging
from email import message_from_bytes
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Gmail requires these scopes for reading + labelling.
_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.modify",
]


class GmailTools:
    """Wraps the Gmail API and exposes callable tools for the Gemini agent."""

    def __init__(self, secrets_manager):
        """
        :param secrets_manager: An instance of RedisSecretsManager.
        """
        self._secrets = secrets_manager
        self._service = None  # lazy-initialised on first use

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _load_credentials_json(self) -> Optional[dict]:
        """Load the OAuth2 client-secret JSON stored in Redis."""
        raw = self._secrets.get_secret("gmail_credentials")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error("'gmail_credentials' in Redis is not valid JSON.")
            return None

    def _load_token(self) -> Optional[dict]:
        """Load the OAuth2 token JSON stored in Redis (may be None on first run)."""
        raw = self._secrets.get_secret("gmail_token")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _save_token(self, token_dict: dict) -> None:
        """Persist the OAuth2 token back to Redis."""
        self._secrets.set_secret("gmail_token", json.dumps(token_dict))

    def _build_service(self):
        """Build (or return cached) Gmail API service object."""
        if self._service is not None:
            return self._service

        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds_info = self._load_credentials_json()
        if not creds_info:
            raise RuntimeError(
                "Gmail credentials not found in Redis. "
                "Run: python manage_keys.py set-file gmail_credentials <path/to/credentials.json>"
            )

        token_dict = self._load_token()
        creds = None

        if token_dict:
            creds = Credentials.from_authorized_user_info(token_dict, _SCOPES)

        # Refresh if expired, or do first-time OAuth dance.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_config(creds_info, _SCOPES)
                creds = flow.run_local_server(port=0)

            # Always save the latest token back to Redis.
            self._save_token(json.loads(creds.to_json()))

        self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def _available(self) -> bool:
        """Return True if gmail_credentials are configured in Redis."""
        return bool(self._secrets.get_secret("gmail_credentials"))

    def _not_configured_msg(self) -> str:
        return (
            "Gmail is not configured. "
            "Store your OAuth credentials with: "
            "python manage_keys.py set-file gmail_credentials <path/to/credentials.json>"
        )

    # ------------------------------------------------------------------ #
    #  Agent-facing tools                                                  #
    # ------------------------------------------------------------------ #

    def list_emails(
        self,
        max_results: int = 10,
        unread_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        List recent emails from Gmail inbox.

        Args:
            max_results: Number of emails to return (default 10, max 50).
            unread_only: If True, only return unread emails.

        Returns:
            A list of dicts with keys: id, subject, from, date, snippet, labels.
        """
        if not self._available():
            return [{"error": self._not_configured_msg()}]
        try:
            service = self._build_service()
            query = "is:unread" if unread_only else ""
            result = service.users().messages().list(
                userId="me",
                maxResults=min(max_results, 50),
                q=query,
                labelIds=["INBOX"],
            ).execute()

            messages = result.get("messages", [])
            emails = []
            for msg_ref in messages:
                emails.append(self._fetch_summary(service, msg_ref["id"]))
            return emails
        except Exception as exc:
            logger.exception("list_emails failed")
            return [{"error": str(exc)}]

    def get_email(self, email_id: str) -> Dict[str, Any]:
        """
        Get the full content of a single email by its ID.

        Args:
            email_id: The Gmail message ID (from list_emails or search_emails).

        Returns:
            A dict with keys: id, subject, from, to, date, body, labels.
        """
        if not self._available():
            return {"error": self._not_configured_msg()}
        try:
            service = self._build_service()
            msg = service.users().messages().get(
                userId="me", id=email_id, format="raw"
            ).execute()

            raw_bytes = base64.urlsafe_b64decode(msg["raw"] + "==")
            email_msg = message_from_bytes(raw_bytes)

            body = ""
            if email_msg.is_multipart():
                for part in email_msg.walk():
                    if part.get_content_type() == "text/plain":
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                            break
            else:
                payload = email_msg.get_payload(decode=True)
                if payload:
                    body = payload.decode(email_msg.get_content_charset() or "utf-8", errors="replace")

            return {
                "id": email_id,
                "subject": email_msg.get("Subject", "(no subject)"),
                "from": email_msg.get("From", ""),
                "to": email_msg.get("To", ""),
                "date": email_msg.get("Date", ""),
                "labels": msg.get("labelIds", []),
                "body": body[:4000],  # truncate for context window safety
            }
        except Exception as exc:
            logger.exception("get_email failed")
            return {"error": str(exc)}

    def search_emails(
        self,
        query: str,
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search emails using a Gmail query string.

        Supports standard Gmail search operators, e.g.:
          - "from:boss@company.com is:unread"
          - "subject:invoice after:2024/01/01"
          - "has:attachment"

        Args:
            query: Gmail search query string.
            max_results: Max number of results to return (default 10, max 50).

        Returns:
            A list of email summary dicts (same format as list_emails).
        """
        if not self._available():
            return [{"error": self._not_configured_msg()}]
        try:
            service = self._build_service()
            result = service.users().messages().list(
                userId="me",
                q=query,
                maxResults=min(max_results, 50),
            ).execute()

            messages = result.get("messages", [])
            return [self._fetch_summary(service, m["id"]) for m in messages]
        except Exception as exc:
            logger.exception("search_emails failed")
            return [{"error": str(exc)}]

    def add_label_to_email(self, email_id: str, label_name: str) -> str:
        """
        Add a label to an email. Creates the label if it does not exist.

        Args:
            email_id: Gmail message ID.
            label_name: Display name of the label to add (e.g. "Butler/Todo").

        Returns:
            Confirmation string.
        """
        if not self._available():
            return self._not_configured_msg()
        try:
            service = self._build_service()
            label_id = self._get_or_create_label(service, label_name)
            service.users().messages().modify(
                userId="me",
                id=email_id,
                body={"addLabelIds": [label_id]},
            ).execute()
            return f"Label '{label_name}' added to email {email_id}."
        except Exception as exc:
            logger.exception("add_label_to_email failed")
            return f"Error: {exc}"

    def remove_label_from_email(self, email_id: str, label_name: str) -> str:
        """
        Remove a label from an email.

        Args:
            email_id: Gmail message ID.
            label_name: Display name of the label to remove.

        Returns:
            Confirmation string.
        """
        if not self._available():
            return self._not_configured_msg()
        try:
            service = self._build_service()
            label_id = self._find_label_id(service, label_name)
            if not label_id:
                return f"Label '{label_name}' not found in your Gmail account."
            service.users().messages().modify(
                userId="me",
                id=email_id,
                body={"removeLabelIds": [label_id]},
            ).execute()
            return f"Label '{label_name}' removed from email {email_id}."
        except Exception as exc:
            logger.exception("remove_label_from_email failed")
            return f"Error: {exc}"

    # ------------------------------------------------------------------ #
    #  Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _fetch_summary(self, service, msg_id: str) -> Dict[str, Any]:
        """Fetch a lightweight summary (headers + snippet) for one message."""
        msg = service.users().messages().get(
            userId="me", id=msg_id, format="metadata",
            metadataHeaders=["Subject", "From", "Date"],
        ).execute()

        headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
        return {
            "id": msg_id,
            "subject": headers.get("Subject", "(no subject)"),
            "from": headers.get("From", ""),
            "date": headers.get("Date", ""),
            "snippet": msg.get("snippet", ""),
            "labels": msg.get("labelIds", []),
        }

    def _list_labels(self, service) -> List[Dict[str, str]]:
        result = service.users().labels().list(userId="me").execute()
        return result.get("labels", [])

    def _find_label_id(self, service, label_name: str) -> Optional[str]:
        for lbl in self._list_labels(service):
            if lbl["name"].lower() == label_name.lower():
                return lbl["id"]
        return None

    def _get_or_create_label(self, service, label_name: str) -> str:
        label_id = self._find_label_id(service, label_name)
        if label_id:
            return label_id
        new_label = service.users().labels().create(
            userId="me",
            body={
                "name": label_name,
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            },
        ).execute()
        return new_label["id"]
