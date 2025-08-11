"""Common utilities for the Winston project.

This module provides shared functionality including:
- Centralized configuration management with Config class
- MCP (Model Context Protocol) host management
- Intent database operations and queries
- Intent generation for tool discovery

All modules in this package follow Winston's core principles:
- Minimal cognitive architecture
- Trust model intelligence over orchestration
- Protocol-driven extensibility
"""

from .config import Config, setup_logging
from .mcp_host import MCPHost
from .intent_database import initialize_intent_database, query_intent_nodes
from .intent_generator import IntentGenerator
from .action_trace import (
    ActionTraceEntry,
    Episode,
    SummaryCheckpoint,
    ActionTraceManager,
)
from .cli_utils import (
    print_action_trace,
    print_episode_summary,
    print_episode_timeline,
    print_memory_status,
)

__all__ = [
    "Config",
    "setup_logging",
    "MCPHost",
    "initialize_intent_database",
    "query_intent_nodes",
    "IntentGenerator",
    "ActionTraceEntry",
    "Episode",
    "SummaryCheckpoint",
    "ActionTraceManager",
    "print_action_trace",
    "print_episode_summary",
    "print_episode_timeline",
    "print_memory_status",
]
