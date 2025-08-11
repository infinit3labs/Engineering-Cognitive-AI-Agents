"""
Experiential Memory MCP Server.

This server provides episodic memory capabilities for Winston,
enabling storage and retrieval of experiences with semantic search.
"""

import os
import sys
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from loguru import logger
from openai import AsyncOpenAI
from jinja2 import Environment, FileSystemLoader

from common.action_trace import ActionTraceManager

# Configure logging
logger.remove()  # Remove default handler
logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level} | {message}")

# Create server instance
server = FastMCP("experiential_memory")


@server.tool
async def recall_episodes(query: str, agent_id: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search for past experiences relevant to the current query.

    Parameters
    ----------
    query : str
        Natural language query to search for
    agent_id : str
        The agent requesting the recall
    limit : int
        Maximum number of episodes to return (default: 5)

    Returns
    -------
    list[dict]
        List of relevant episodes with summaries and lessons
    """
    logger.info(f"recall_episodes called with: query='{query}', agent_id='{agent_id}', limit={limit}")
    try:
        # Get paths from environment - these must be set by the calling process
        episodes_path_str = os.environ.get("EPISODES_PATH")
        chroma_path_str = os.environ.get("CHROMA_PATH")
        
        if not episodes_path_str or not chroma_path_str:
            raise ValueError(
                "EPISODES_PATH and CHROMA_PATH environment variables are required. "
                "These must be absolute paths to the episodes and ChromaDB directories."
            )
        
        # Use the paths as-is - they're already absolute from Config
        episodes_path = Path(episodes_path_str)
        chroma_path = Path(chroma_path_str)
        
        # Verify they're absolute (they should be from Config)
        if not episodes_path.is_absolute() or not chroma_path.is_absolute():
            raise ValueError(
                f"Paths must be absolute. Got episodes={episodes_path}, chroma={chroma_path}. "
                "This indicates a bug in Config variable substitution."
            )
        
        # Load agent from disk
        manager = ActionTraceManager.get_agent(
            agent_id=agent_id,
            episodes_path=episodes_path,
            chroma_path=chroma_path,
        )
        episodes = await manager.search_episodes(query, limit)
        logger.info(f"Found {len(episodes)} episodes for agent {agent_id} with query: '{query}'")
        
        # Format episodes for return
        results = []
        for episode in episodes:
            result = {
                "id": episode["id"],
                "task": episode["task_description"],
                "summary": episode.get("summary_checkpoint", {}).get("summary", "No summary available") if episode.get("summary_checkpoint") else "No summary available",
                "lessons": episode.get("summary_checkpoint", {}).get("lessons", []) if episode.get("summary_checkpoint") else [],
                "outcome": episode.get("outcome", "unknown"),
                "timestamp": episode.get("timestamp", ""),
                "relevance_score": episode.get("relevance_score", 0.0),
            }
            
            # Include a few relevant actions if available
            if "relevant_actions" in episode:
                result["relevant_actions"] = episode["relevant_actions"][:3]
                
            results.append(result)
            
        return results
        
    except Exception as e:
        logger.error(f"Error recalling episodes: {e}")
        return []


@server.tool
async def new_episode(reason: str, agent_id: str) -> str:
    """Start a new episode when context shifts.

    This signals that the current episode should be finalized
    and a new one started. Used when Winston detects a topic
    change or completes a coherent task sequence.

    Parameters
    ----------
    reason : str
        Explanation of why a new episode is starting
    agent_id : str
        The agent requesting the new episode

    Returns
    -------
    str
        Confirmation message with new episode status
    """
    logger.info(f"new_episode called with: reason='{reason}', agent_id='{agent_id}'")
    try:
        # Get paths from environment - these must be set by the calling process
        episodes_path_str = os.environ.get("EPISODES_PATH")
        chroma_path_str = os.environ.get("CHROMA_PATH")
        
        if not episodes_path_str or not chroma_path_str:
            raise ValueError(
                "EPISODES_PATH and CHROMA_PATH environment variables are required. "
                "These must be absolute paths to the episodes and ChromaDB directories."
            )
        
        # Use the paths as-is - they're already absolute from Config
        episodes_path = Path(episodes_path_str)
        chroma_path = Path(chroma_path_str)
        
        # Verify they're absolute (they should be from Config)
        if not episodes_path.is_absolute() or not chroma_path.is_absolute():
            raise ValueError(
                f"Paths must be absolute. Got episodes={episodes_path}, chroma={chroma_path}. "
                "This indicates a bug in Config variable substitution."
            )
        
        # For compression operations, we need OpenAI client and templates
        aclient = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        template_env = Environment(loader=FileSystemLoader("./prompts"), enable_async=True)
        
        # Load agent from disk
        manager = ActionTraceManager.get_agent(
            agent_id=agent_id,
            episodes_path=episodes_path,
            aclient=aclient,
            template_env=template_env,
            chroma_path=chroma_path,
        )
        await manager.start_new_episode_with_reason(reason)
        logger.info(f"Started new episode for agent {agent_id}: {reason}")
        return f"Started new episode: {reason}"
    except Exception as e:
        logger.error(f"Error starting new episode: {e}")
        return f"Error starting new episode: {str(e)}"


def main():
    """Main entry point for the server."""
    logger.info(f"Starting Experiential Memory Server")
    
    # Note: ActionTraceManager instances are created by the kernel
    # This MCP server just provides tool wrappers around them
    
    # Run the server
    server.run()


if __name__ == "__main__":
    main()