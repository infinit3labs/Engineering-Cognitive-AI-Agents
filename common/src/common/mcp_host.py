"""FastMCP-idiomatic MCPHost implementation."""

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from loguru import logger
from mcp import Tool
from fastmcp.client import Client

from .config import Config, substitute_config_variables
from .tool_identity import ToolIdentity


class MCPHost:
    """Manages MCP servers using FastMCP's Client."""
    
    def __init__(self, mcp_config_path: Path | str, app_config: Config):
        """Initialize with an MCP config file path and application configuration.
        
        Parameters
        ----------
        mcp_config_path : Path | str
            Path to the MCP servers configuration JSON file
        app_config : Config
            Application configuration object for variable substitution and path resolution
        """
        self.mcp_config_path = Path(mcp_config_path)
        self.app_config = app_config
        self.client: Client | None = None
        self._raw_config: dict[str, Any] = {}
        self._enabled_servers: list[str] = []
        self._shutdown_complete = False
        
        # Register cleanup at interpreter exit
        import atexit
        atexit.register(self._force_cleanup)
    
    def _ensure_server_directories(self, config: dict[str, Any]) -> None:
        """Ensure all directories referenced in MCP config exist.
        
        Parses the MCP configuration to find directory paths in args and env
        variables, then creates them if they don't exist.
        
        Parameters
        ----------
        config : dict
            The MCP configuration after variable substitution
        """
        for server_name, server_config in config.get("mcpServers", {}).items():
            # Check args for directory paths (e.g., filesystem server)
            if "args" in server_config:
                for arg in server_config["args"]:
                    if isinstance(arg, str) and "/" in arg:
                        # This looks like a path - ensure it exists
                        path = Path(arg)
                        if path.is_absolute() and not path.exists():
                            path.mkdir(parents=True, exist_ok=True)
                            logger.trace(f"Created directory for {server_name}: {path}")
            
            # Check env variables for directory paths
            if "env" in server_config:
                for env_key, env_value in server_config["env"].items():
                    if isinstance(env_value, str) and "/" in env_value:
                        path = Path(env_value)
                        if path.is_absolute() and not path.exists():
                            path.mkdir(parents=True, exist_ok=True)
                            logger.trace(f"Created {env_key} directory for {server_name}: {path}")
    
    async def startup(self) -> None:
        """Load config and connect to all servers."""
        logger.trace(f"Loading MCP config from: {self.mcp_config_path}")
        
        # Load and preprocess the config
        with self.mcp_config_path.open("r") as f:
            raw_mcp_config = json.load(f)
        
        logger.trace(f"Raw MCP config: {raw_mcp_config}")
        
        # Apply variable substitution
        mcp_config = substitute_config_variables(raw_mcp_config, self.app_config)
        logger.trace(f"MCP config after variable substitution: {mcp_config}")
        
        # Ensure required directories exist after substitution
        self._ensure_server_directories(mcp_config)
        
        self._raw_config = mcp_config
        
        # Filter out disabled servers (Winston-specific)
        servers = mcp_config.get("mcpServers", {})
        enabled_servers = {
            name: server_config 
            for name, server_config in servers.items() 
            if server_config.get("enabled", True)
        }
        
        self._enabled_servers = list(enabled_servers.keys())
        logger.trace(f"Enabled servers: {self._enabled_servers}")
        
        # Create clean config and let FastMCP handle everything
        clean_mcp_config = {"mcpServers": enabled_servers}
        logger.trace(f"Clean MCP config for FastMCP: {clean_mcp_config}")
        
        try:
            self.client = Client(clean_mcp_config)
            await self.client.__aenter__()
            logger.success(f"Connected to {len(enabled_servers)} servers")
        except Exception as e:
            logger.error(f"Failed to connect to MCP servers: {e}")
            raise
    
    async def shutdown(self) -> None:
        """Disconnect from all servers and cleanup to prevent hanging.
        
        This method handles the FastMCP stdio transport bug where keep_alive=True
        causes subprocesses to hang. Once FastMCP supports keep_alive=False in
        the config format, the cleanup can be simplified.
        
        See: https://github.com/modelcontextprotocol/python-sdk/issues/817
        """
        if self._shutdown_complete:
            return
            
        logger.trace("Shutting down MCP Host...")
        
        if self.client:
            try:
                await self.client.__aexit__(None, None, None)
                await self.client.close()
            except Exception as e:
                logger.warning(f"Error during client shutdown: {e}")
            finally:
                # Keep the client reference so atexit can detect incomplete shutdown
                pass
        
        # Clean up pending tasks to prevent hanging
        await self._cleanup_pending_tasks()
        
        self._shutdown_complete = True
        logger.trace("MCP Host shut down successfully")
    
    async def _cleanup_pending_tasks(self) -> None:
        """Clean up pending asyncio tasks (FastMCP workaround)."""
        # Short delay to allow normal cleanup
        await asyncio.sleep(0.1)

        # Find and cancel any remaining tasks
        loop = asyncio.get_running_loop()
        pending = asyncio.all_tasks(loop)
        current = asyncio.current_task()
        pending.discard(current)

        if pending:
            logger.debug(f"Found {len(pending)} pending tasks after MCP shutdown:")
            for t in pending:
                logger.debug(f"  - {t.get_name()}: {t}")

            # Cancel all pending tasks
            for t in pending:
                t.cancel()

            # Wait for cancellation with a timeout
            try:
                await asyncio.wait_for(
                    asyncio.gather(*pending, return_exceptions=True), timeout=2.0
                )
            except asyncio.TimeoutError:
                logger.warning("Some tasks did not respond to cancellation in time")
    
    def _force_cleanup(self) -> None:
        """Force process termination if needed (called by atexit).
        
        This is the nuclear option for the FastMCP stdio transport bug.
        """
        # If we ever initialized MCP servers, force exit to prevent hanging
        # The bug affects both CLI and REPL modes
        if self._enabled_servers:
            logger.trace(
                "Forcing process termination due to FastMCP keep_alive=True bug. "
                "See: https://github.com/modelcontextprotocol/python-sdk/issues/817"
            )
            os._exit(0)
    
    async def get_all_tools(self) -> dict[str, list[Tool]]:
        """Get tools from all connected servers."""
        if not self.client:
            logger.warning("No client available in get_all_tools")
            return {}
            
        all_tools = {}
        
        try:
            # Get all tools from the unified client
            logger.trace(f"Listing tools from client with {len(self._enabled_servers)} servers")
            tools = await self.client.list_tools()
            logger.trace(f"Retrieved {len(tools)} tools from client")
            
            if len(self._enabled_servers) > 1:
                # Multiple servers - tools are namespaced as server_tool
                for tool in tools:
                    try:
                        server_name, tool_name = ToolIdentity.parse_namespaced_tool_name(
                            tool.name, self._enabled_servers
                        )
                        original_tool = Tool(
                            name=tool_name,
                            description=tool.description,
                            inputSchema=tool.inputSchema
                        )
                        all_tools.setdefault(server_name, []).append(original_tool)
                    except ValueError as e:
                        logger.warning(str(e))
            else:
                # Single server - no namespace
                server_name = self._enabled_servers[0] if self._enabled_servers else "unknown"
                all_tools[server_name] = tools
                
            for name, server_tools in all_tools.items():
                logger.trace(f"Server '{name}' has {len(server_tools)} tools")
                
        except Exception as e:
            logger.error(f"Failed to list tools: {e}")
            
        return all_tools
    
    async def call_tool(
        self, 
        server_name: str, 
        tool_name: str, 
        arguments: dict[str, Any] | None = None
    ) -> Any:
        """Call a tool on a specific server."""
        if not self.client:
            raise RuntimeError("Not connected to any servers")
            
        # Handle FastMCP's automatic namespacing
        namespaced_tool = ToolIdentity.create_namespaced_tool_name(
            server_name, tool_name, len(self._enabled_servers) > 1
        )
            
        # Use call_tool_mcp to get raw MCP result
        return await self.client.call_tool_mcp(namespaced_tool, arguments or {})
    
    @property
    def server_names(self) -> list[str]:
        """Get list of connected server names."""
        return self._enabled_servers
    
    @property
    def config(self) -> dict[str, Any]:
        """Get the processed configuration."""
        return self._raw_config