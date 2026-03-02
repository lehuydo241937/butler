import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Add the project root to sys.path
sys.path.append(os.getcwd())

from agent.butler import load_system_prompt

def test_load_system_prompt_exists(tmp_path):
    prompt_file = tmp_path / "system_prompt.txt"
    content = "You are a test assistant."
    prompt_file.write_text(content, encoding="utf-8")
    
    loaded = load_system_prompt(str(prompt_file))
    assert loaded == content

def test_load_system_prompt_missing():
    # Should return default
    loaded = load_system_prompt("non_existent_file.txt")
    assert "helpful AI assistant" in loaded
