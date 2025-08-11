"""Centralized tool identity management for Winston.

This module provides a single source of truth for tool naming, URIs, and namespacing
across the entire Winston system. It ensures consistency between MCP servers, intent
indexing, and tool execution.
"""

from typing import Any


class ToolIdentity:
    """Manages tool identity and URI formatting across Winston."""
    
    TOOL_URI_PREFIX = "tool"
    URI_SEPARATOR = "::"
    
    @staticmethod
    def create_tool_uri(server_name: str, tool_name: str) -> str:
        """Create a standardized tool URI.
        
        Parameters
        ----------
        server_name : str
            The name of the MCP server
        tool_name : str
            The name of the tool (without server prefix)
            
        Returns
        -------
        str
            Tool URI in format: tool::server_name::tool_name
        """
        return f"{ToolIdentity.TOOL_URI_PREFIX}{ToolIdentity.URI_SEPARATOR}{server_name}{ToolIdentity.URI_SEPARATOR}{tool_name}"
    
    @staticmethod
    def parse_tool_uri(tool_uri: str) -> tuple[str, str]:
        """Parse a tool URI into server and tool names.
        
        Parameters
        ----------
        tool_uri : str
            Tool URI in format: tool::server_name::tool_name
            
        Returns
        -------
        tuple[str, str]
            (server_name, tool_name)
            
        Raises
        ------
        ValueError
            If the URI format is invalid
        """
        parts = tool_uri.split(ToolIdentity.URI_SEPARATOR)
        if len(parts) != 3 or parts[0] != ToolIdentity.TOOL_URI_PREFIX:
            raise ValueError(f"Invalid tool URI format: '{tool_uri}' (expected 'tool::server_name::tool_name')")
        return parts[1], parts[2]
    
    @staticmethod
    def create_namespaced_tool_name(server_name: str, tool_name: str, is_multi_server: bool) -> str:
        """Create the namespaced tool name for MCP calls.
        
        FastMCP automatically namespaces tools when multiple servers are present.
        This method centralizes that logic.
        
        Parameters
        ----------
        server_name : str
            The name of the MCP server
        tool_name : str
            The name of the tool (without prefix)
        is_multi_server : bool
            Whether multiple servers are connected
            
        Returns
        -------
        str
            Namespaced tool name (server_tool) if multi-server, otherwise just tool name
        """
        if is_multi_server:
            return f"{server_name}_{tool_name}"
        return tool_name
    
    @staticmethod
    def parse_namespaced_tool_name(namespaced_name: str, enabled_servers: list[str]) -> tuple[str, str]:
        """Parse a namespaced tool name from FastMCP.
        
        Parameters
        ----------
        namespaced_name : str
            The tool name from FastMCP (might be server_tool format)
        enabled_servers : list[str]
            List of enabled server names
            
        Returns
        -------
        tuple[str, str]
            (server_name, tool_name)
        """
        # Try to match server prefix
        for server in enabled_servers:
            if namespaced_name.startswith(f"{server}_"):
                tool_name = namespaced_name[len(server) + 1:]
                return server, tool_name
        
        # No server prefix found - single server scenario
        if len(enabled_servers) == 1:
            return enabled_servers[0], namespaced_name
        
        # Unable to determine server
        raise ValueError(f"Could not determine server for tool: {namespaced_name}")
    
    @staticmethod
    def create_intent_id(intent_type: str, server_name: str, tool_name: str) -> str:
        """Create a standardized intent ID.
        
        Parameters
        ----------
        intent_type : str
            Type of intent (L1 or L2)
        server_name : str
            The name of the MCP server
        tool_name : str
            The name of the tool
            
        Returns
        -------
        str
            Intent ID in format: intent::type::server_name::tool_name
        """
        return f"intent{ToolIdentity.URI_SEPARATOR}{intent_type}{ToolIdentity.URI_SEPARATOR}{server_name}{ToolIdentity.URI_SEPARATOR}{tool_name}"
    
    @staticmethod
    def validate_tool_uri(tool_uri: str) -> bool:
        """Check if a string is a valid tool URI.
        
        Parameters
        ----------
        tool_uri : str
            String to validate
            
        Returns
        -------
        bool
            True if valid tool URI format
        """
        try:
            ToolIdentity.parse_tool_uri(tool_uri)
            return True
        except ValueError:
            return False