import yaml
import os
import logging
from typing import Dict
from src.tools.mcp_client import MCPClient

logger = logging.getLogger(__name__)

class ToolRegistry:
    """Loads and manages all active MCP clients based on configuration."""
    
    def __init__(self, config_path: str = "config.yaml"):
        self.clients: Dict[str, MCPClient] = {}
        self.load_configs(config_path)

    def load_configs(self, config_path: str):
        if not os.path.exists(config_path):
            logger.warning(f"Config file {config_path} not found.")
            return

        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        
        mcp_config = config.get("mcp", {})
        
        # Load clients dynamically
        for tool_id, tool_settings in mcp_config.items():
            if tool_settings.get("enabled"):
                # Here we could map tool_id to specific local paths or docker containers
                self.clients[tool_id] = MCPClient(
                    stdio_command=["npx", f"@modelcontextprotocol/server-{tool_id}"]
                )
                logger.info(f"Registered MCP tool: {tool_id}")

    def get_client(self, tool_id: str) -> MCPClient:
        return self.clients.get(tool_id)

    def list_tools(self) -> list:
        return list(self.clients.keys())
