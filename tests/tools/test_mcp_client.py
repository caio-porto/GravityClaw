import pytest
from src.tools.mcp_client import MCPClient

def test_mcp_client_init():
    """Test initialization of MCPClient with different parameters."""
    # Test with no parameters
    client_empty = MCPClient()
    assert client_empty.server_url is None
    assert client_empty.stdio_command is None

    # Test with server_url
    url = "http://localhost:8080"
    client_url = MCPClient(server_url=url)
    assert client_url.server_url == url
    assert client_url.stdio_command is None

    # Test with stdio_command
    cmd = ["python", "-m", "my_mcp_server"]
    client_cmd = MCPClient(stdio_command=cmd)
    assert client_cmd.server_url is None
    assert client_cmd.stdio_command == cmd

def test_mcp_client_call_tool():
    """Test calling a tool via MCPClient."""
    client = MCPClient()
    tool_name = "test_tool"
    arguments = {"arg1": "value1", "arg2": 123}

    result = client.call_tool(tool_name, arguments)

    assert isinstance(result, dict)
    assert result.get("status") == "success"
    assert result.get("result") == f"Executed {tool_name} mockly."

def test_mcp_client_read_resource():
    """Test reading a resource via MCPClient."""
    client = MCPClient()
    uri = "test://resource/1"

    result = client.read_resource(uri)

    assert isinstance(result, str)
    assert result == f"Mock resource content for {uri}"
