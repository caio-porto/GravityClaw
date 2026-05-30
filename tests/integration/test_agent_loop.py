import sys
from unittest.mock import patch, MagicMock

sys.modules['src.memory'] = MagicMock()
sys.modules['src.memory.core'] = MagicMock()
sys.modules['src.memory.buffer'] = MagicMock()
sys.modules['src.memory.core.CoreMemory'] = MagicMock()
sys.modules['src.memory.buffer.DailyBuffer'] = MagicMock()

import pytest
from src.agent.loop import AgentLoop

@pytest.fixture
def agent():
    with patch('src.agent.loop.ModelManager') as mock_model_manager, \
         patch('src.agent.loop.DailyBuffer') as mock_daily_buffer:

        mock_buffer_instance = MagicMock()
        mock_buffer_instance.get_recent_context.return_value = ""
        mock_daily_buffer.return_value = mock_buffer_instance

        agent_loop = AgentLoop()
        # Ensure our mock buffer is used
        agent_loop.short_term_memory = mock_buffer_instance
        # Mock the query response
        agent_loop.model_manager.query.return_value = "Mocked successful response."
        yield agent_loop

def test_agent_loop_process_input(agent):
    """Test that the agent loop properly receives input and returns a generated response."""
    user_input = "Hello, what's my name?"
    response = agent.process_input(user_input)
    
    # Check that model manager was called with the user input
    agent.model_manager.query.assert_called_once()
    # query() now receives a list of message dicts
    messages = agent.model_manager.query.call_args[0][0]
    assert isinstance(messages, list)
    
    # The last message should be the user's current input
    last_msg = messages[-1]
    assert last_msg["role"] == "user"
    assert user_input in last_msg["content"]
    
    # Check the return string
    assert response == "Mocked successful response."
