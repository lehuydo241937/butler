
"""
Redis-backed secrets manager for AI Agents.
Stores API keys and other sensitive configuration in a dedicated Redis hash.
"""

import os
from typing import Optional
import redis
from dotenv import load_dotenv

load_dotenv()


class RedisSecretsManager:
    """Manage secret keys in Redis."""

    _SECRETS_KEY = "config:api_keys"

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        db: Optional[int] = None,
        redis_client: Optional[redis.Redis] = None,
    ):
        """
        Connect to Redis.
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

    def set_secret(self, key_name: str, value: str) -> None:
        """Store a secret key."""
        self.r.hset(self._SECRETS_KEY, key_name, value)

    def get_secret(self, key_name: str) -> Optional[str]:
        """Retrieve a secret key."""
        return self.r.hget(self._SECRETS_KEY, key_name)

    def delete_secret(self, key_name: str) -> None:
        """Delete a secret key."""
        self.r.hdel(self._SECRETS_KEY, key_name)

    def list_secrets(self) -> list[str]:
        """List names of stored secrets (not values)."""
        return self.r.hkeys(self._SECRETS_KEY)
