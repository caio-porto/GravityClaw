import pytest
from src.memory.buffer import DailyBuffer

def test_get_recent_context():
    buffer = DailyBuffer()
    result = buffer.get_recent_context()
    assert result == "Recent Context"

def test_get_recent_context_with_args():
    buffer = DailyBuffer()
    result = buffer.get_recent_context(lines=10, max_days=1)
    assert result == "Recent Context"

def test_add_interaction():
    buffer = DailyBuffer()
    # Currently add_interaction is just a 'pass', so it returns None
    result = buffer.add_interaction("user123", "Hello", "Hi there")
    assert result is None
