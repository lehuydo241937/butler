import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Add the project root to sys.path
sys.path.append(os.getcwd())

from backend.secrets_manager.redis_secrets import RedisSecretsManager

class TestRedisSecretsManager:
    @patch("backend.secrets_manager.redis_secrets.redis.Redis")
    def test_init(self, mock_redis):
        manager = RedisSecretsManager()
        assert manager.r is not None
        mock_redis.assert_called_once()

    @patch("backend.secrets_manager.redis_secrets.redis.Redis")
    def test_get_secret(self, mock_redis):
        mock_r = MagicMock()
        mock_r.hget.return_value = "test_value"
        mock_redis.return_value = mock_r
        
        manager = RedisSecretsManager()
        val = manager.get_secret("test_key")
        assert val == "test_value"
        mock_r.hget.assert_called_with("config:api_keys", "test_key")

    @patch("backend.secrets_manager.redis_secrets.redis.Redis")
    def test_set_secret(self, mock_redis):
        mock_r = MagicMock()
        mock_redis.return_value = mock_r
        
        manager = RedisSecretsManager()
        manager.set_secret("test_key", "test_value")
        mock_r.hset.assert_called_with("config:api_keys", "test_key", "test_value")
