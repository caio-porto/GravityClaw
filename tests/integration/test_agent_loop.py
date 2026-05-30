import sys
from unittest.mock import patch, MagicMock

# 1. Save original modules to prevent test pollution
_orig_modules = {
    'src.memory': sys.modules.get('src.memory'),
    'src.memory.core': sys.modules.get('src.memory.core'),
    'src.memory.buffer': sys.modules.get('src.memory.buffer'),
    'src.memory.core.CoreMemory': sys.modules.get('src.memory.core.CoreMemory'),
    'src.memory.buffer.DailyBuffer': sys.modules.get('src.memory.buffer.DailyBuffer'),
}

# 2. Temporarily mock src.memory for importing AgentLoop
sys.modules['src.memory'] = MagicMock()
sys.modules['src.memory.core'] = MagicMock()
sys.modules['src.memory.buffer'] = MagicMock()
sys.modules['src.memory.core.CoreMemory'] = MagicMock()
sys.modules['src.memory.buffer.DailyBuffer'] = MagicMock()

try:
    import pytest
    from src.agent.loop import AgentLoop
finally:
    # 3. Restore original modules immediately to preserve test isolation
    for name, orig in _orig_modules.items():
        if orig is not None:
            sys.modules[name] = orig
        else:
            sys.modules.pop(name, None)

@pytest.fixture
def agent():
    with patch('src.agent.loop.ModelManager') as mock_model_manager, \
         patch('src.agent.loop.CoreMemory') as mock_core, \
         patch('src.agent.loop.DailyBuffer') as mock_daily:
        agent_loop = AgentLoop()
        agent_loop.core_memory = MagicMock()
        agent_loop.core_memory.get_context.return_value = 'Mocked core context'
        agent_loop.daily_buffer = MagicMock()
        agent_loop.daily_buffer.get_recent_context.return_value = '### [12:00] Interaction with User\nUser: hi\nGravityClaw: hello'
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
