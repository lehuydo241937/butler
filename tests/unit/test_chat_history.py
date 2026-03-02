import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Add the project root to sys.path
sys.path.append(os.getcwd())

from backend.chat_history.redis_history import RedisChatHistory

class TestRedisChatHistory:
    @patch("backend.chat_history.redis_history.redis.Redis")
    def test_init(self, mock_redis):
        history = RedisChatHistory()
        assert history.r is not None
        mock_redis.assert_called_once()

    @patch("backend.chat_history.redis_history.redis.Redis")
    def test_create_session(self, mock_redis):
        mock_r = MagicMock()
        mock_redis.return_value = mock_r
        
        history = RedisChatHistory()
        sid = history.create_session("Test")
        assert sid is not None
        assert mock_r.sadd.called
        # hset is called with mapping in create_session
        args, kwargs = mock_r.hset.call_args
        assert "chat:{sid}:meta".format(sid=sid) in args[0]
        assert kwargs["mapping"]["title"] == "Test"

    @patch("backend.chat_history.redis_history.redis.Redis")
    def test_add_message(self, mock_redis):
        mock_r = MagicMock()
        mock_redis.return_value = mock_r
        
        history = RedisChatHistory()
        history.add_message("session1", "user", "hello")
        assert mock_r.rpush.called
        assert mock_r.hset.called # Updates updated_at
