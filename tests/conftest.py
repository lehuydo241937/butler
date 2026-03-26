"""
conftest.py — shared pytest fixtures for the butler test suite.
"""
import os
import sys

# Ensure project root is always on sys.path so `from agent.xxx import ...` works
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
