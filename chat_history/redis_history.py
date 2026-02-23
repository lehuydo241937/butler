"""
Redis-backed chat history for AI Agents.

Data model
----------
- chat:sessions              → Redis SET of all session IDs
- chat:{sid}:messages         → Redis LIST of JSON-encoded messages (oldest first)
- chat:{sid}:meta             → Redis HASH with session metadata
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis
from dotenv import load_dotenv

load_dotenv()


class RedisChatHistory:
    """Save and load AI-agent chat sessions in Redis."""

    # ── Key prefixes ────────────────────────────────────────────────────
    _SESSION_INDEX = "chat:sessions"
    _MSG_KEY = "chat:{sid}:messages"
    _META_KEY = "chat:{sid}:meta"

    # ── Init ────────────────────────────────────────────────────────────
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        db: Optional[int] = None,
        redis_client: Optional[redis.Redis] = None,
    ):
        """
        Connect to Redis.

        Parameters
        ----------
        host / port / db : Override values; defaults read from env vars
                           REDIS_HOST, REDIS_PORT, REDIS_DB.
        redis_client     : Pass your own ``redis.Redis`` instance to reuse
                           an existing connection.
        """
        if redis_client:
            self.r = redis_client
        else:
            self.r = redis.Redis(
                host=host or os.getenv("REDIS_HOST", "localhost"),
                port=int(port or os.getenv("REDIS_PORT", 6379)),
                db=int(db or os.getenv("REDIS_DB", 0)),
                decode_responses=True,
            )

    # ── Session management ──────────────────────────────────────────────
    def create_session(self, title: Optional[str] = None) -> str:
        """
        Start a new chat session.

        Returns the generated session ID (UUID-4).
        """
        sid = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()

        # Register in the session index
        self.r.sadd(self._SESSION_INDEX, sid)

        # Store default metadata
        meta = {"created_at": now, "updated_at": now}
        if title:
            meta["title"] = title
        self.r.hset(self._META_KEY.format(sid=sid), mapping=meta)

        return sid

    def list_sessions(self) -> List[Dict[str, Any]]:
        """Return a list of ``{"session_id": ..., **metadata}`` dicts."""
        sids = self.r.smembers(self._SESSION_INDEX)
        sessions = []
        for sid in sorted(sids):
            meta = self.r.hgetall(self._META_KEY.format(sid=sid))
            sessions.append({"session_id": sid, **meta})
        return sessions

    def delete_session(self, session_id: str) -> None:
        """Permanently delete a session and all its messages."""
        pipe = self.r.pipeline()
        pipe.delete(self._MSG_KEY.format(sid=session_id))
        pipe.delete(self._META_KEY.format(sid=session_id))
        pipe.srem(self._SESSION_INDEX, session_id)
        pipe.execute()

    # ── Metadata ────────────────────────────────────────────────────────
    def set_session_metadata(self, session_id: str, metadata: Dict[str, str]) -> None:
        """
        Merge *metadata* into the session's existing metadata hash.

        Values must be strings (Redis hash constraint).
        """
        metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.r.hset(self._META_KEY.format(sid=session_id), mapping=metadata)

    def get_session_metadata(self, session_id: str) -> Dict[str, str]:
        """Return the full metadata hash for a session."""
        return self.r.hgetall(self._META_KEY.format(sid=session_id))

    # ── Messages ────────────────────────────────────────────────────────
    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Append a message to the session.

        Parameters
        ----------
        role    : "user", "assistant", or "system"
        content : The message text
        extra   : Any additional fields to store alongside the message

        Returns the stored message dict.
        """
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            msg.update(extra)

        self.r.rpush(self._MSG_KEY.format(sid=session_id), json.dumps(msg))

        # Touch session updated_at
        self.r.hset(
            self._META_KEY.format(sid=session_id),
            "updated_at",
            msg["timestamp"],
        )
        return msg

    def get_history(
        self,
        session_id: str,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve messages for a session.

        Parameters
        ----------
        limit : If set, return only the *last* N messages.
                If None, return the full history.
        """
        key = self._MSG_KEY.format(sid=session_id)

        if limit is not None:
            raw = self.r.lrange(key, -limit, -1)
        else:
            raw = self.r.lrange(key, 0, -1)

        return [json.loads(m) for m in raw]

    def get_history_by_time_range(
        self,
        session_id: str,
        start_iso: str,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve messages for a session that occurred after *start_iso*.
        
        Parameters
        ----------
        start_iso : ISO-8601 timestamp string.
        """
        all_msgs = self.get_history(session_id)
        return [m for m in all_msgs if m["timestamp"] >= start_iso]

    def count_messages(self, session_id: str) -> int:
        """Return the number of messages in a session."""
        return self.r.llen(self._MSG_KEY.format(sid=session_id))

    # ── Utility ─────────────────────────────────────────────────────────
    def ping(self) -> bool:
        """Return True if Redis is reachable."""
        try:
            return self.r.ping()
        except redis.ConnectionError:
            return False
