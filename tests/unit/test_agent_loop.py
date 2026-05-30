import pytest
import sys
from unittest.mock import MagicMock

# Mock the missing src.memory module before importing AgentLoop
sys.modules['src.memory'] = MagicMock()
sys.modules['src.memory.core'] = MagicMock()
sys.modules['src.memory.buffer'] = MagicMock()

from src.agent.loop import AgentLoop

def test_parse_history_to_turns_basic():
    agent = AgentLoop()
    raw_history = """
### [10:00:00] Interaction with user123

**User**: Hello there!

**GravityClaw**: Hi! How can I help you?
### [10:05:00] Interaction with user123

**User**: What is my name?

**GravityClaw**: You are user123.
"""
    turns = agent._parse_history_to_turns(raw_history)
    assert len(turns) == 4
    assert turns[0] == {"role": "user", "content": "Hello there!"}
    assert turns[1] == {"role": "assistant", "content": "Hi! How can I help you?"}
    assert turns[2] == {"role": "user", "content": "What is my name?"}
    assert turns[3] == {"role": "assistant", "content": "You are user123."}

def test_parse_history_to_turns_empty_or_whitespace():
    agent = AgentLoop()
    assert agent._parse_history_to_turns("") == []
    assert agent._parse_history_to_turns("   \n  \n") == []

def test_parse_history_to_turns_no_assistant_response():
    agent = AgentLoop()
    raw_history = """
### [10:00:00] Interaction with user123

**User**: Hello there!
"""
    turns = agent._parse_history_to_turns(raw_history)
    assert len(turns) == 1
    assert turns[0] == {"role": "user", "content": "Hello there!"}

def test_parse_history_to_turns_mocked_response_filtered():
    agent = AgentLoop()
    raw_history = """
### [10:00:00] Interaction with user123

**User**: Hello there!

**GravityClaw**: Mocked successful response.
"""
    turns = agent._parse_history_to_turns(raw_history)
    assert len(turns) == 1
    assert turns[0] == {"role": "user", "content": "Hello there!"}

def test_parse_history_to_turns_replace_temp_files():
    agent = AgentLoop()
    raw_history = """
### [10:00:00] Interaction with user123

**User**: Check this photo @temp_photo_12345!

**GravityClaw**: I got the @temp_photo_12345. And a voice note @temp_voice_abcde.
"""
    turns = agent._parse_history_to_turns(raw_history)
    assert len(turns) == 2
    assert turns[0] == {"role": "user", "content": "Check this photo [Attached File]"}
    assert turns[1] == {"role": "assistant", "content": "I got the [Attached File] And a voice note [Attached File]"}

def test_parse_history_to_turns_edge_cases():
    agent = AgentLoop()
    # Missing "**GravityClaw**:" or missing "**User**:" or malformed
    raw_history = """
### [10:00:00] Interaction with user123
Just some random text
**GravityClaw**: Hi
"""
    turns = agent._parse_history_to_turns(raw_history)
    assert len(turns) == 1
    assert turns[0] == {"role": "assistant", "content": "Hi"}
