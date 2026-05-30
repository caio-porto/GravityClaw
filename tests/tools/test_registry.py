import pytest
from unittest.mock import patch, mock_open
from src.tools.registry import ToolRegistry
from src.tools.mcp_client import MCPClient

def test_registry_init_file_not_found():
    """Test ToolRegistry initialization when config file does not exist."""
    with patch('os.path.exists', return_value=False) as mock_exists:
        registry = ToolRegistry(config_path="non_existent_config.yaml")
        assert registry.clients == {}
        mock_exists.assert_called_once_with("non_existent_config.yaml")

def test_registry_load_configs():
    """Test loading configuration from a mock yaml file."""
    mock_yaml_data = {
        "mcp": {
            "tool_a": {"enabled": True},
            "tool_b": {"enabled": False},
            "tool_c": {"enabled": True, "path": "/some/path"}
        }
    }

    with patch('os.path.exists', return_value=True):
        with patch('builtins.open', mock_open(read_data="dummy")):
            with patch('yaml.safe_load', return_value=mock_yaml_data):
                registry = ToolRegistry()

                # Should only load enabled tools
                assert "tool_a" in registry.clients
                assert "tool_b" not in registry.clients
                assert "tool_c" in registry.clients

                assert isinstance(registry.clients["tool_a"], MCPClient)
                assert registry.clients["tool_a"].stdio_command == ["npx", "@modelcontextprotocol/server-tool_a"]

def test_registry_get_client():
    """Test getting an existing and non-existing client."""
    mock_yaml_data = {
        "mcp": {
            "tool_a": {"enabled": True}
        }
    }

    with patch('os.path.exists', return_value=True):
        with patch('builtins.open', mock_open(read_data="dummy")):
            with patch('yaml.safe_load', return_value=mock_yaml_data):
                registry = ToolRegistry()

                client = registry.get_client("tool_a")
                assert isinstance(client, MCPClient)

                missing_client = registry.get_client("tool_b")
                assert missing_client is None

def test_registry_list_tools():
    """Test listing all registered tools."""
    mock_yaml_data = {
        "mcp": {
            "tool_a": {"enabled": True},
            "tool_b": {"enabled": True}
        }
    }

    with patch('os.path.exists', return_value=True):
        with patch('builtins.open', mock_open(read_data="dummy")):
            with patch('yaml.safe_load', return_value=mock_yaml_data):
                registry = ToolRegistry()

                tools = registry.list_tools()
                assert len(tools) == 2
                assert "tool_a" in tools
                assert "tool_b" in tools
