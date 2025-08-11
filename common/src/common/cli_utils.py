"""
CLI utilities for pretty printing and visualization.

This module provides utilities for displaying action traces,
episodes, and other Winston data in a readable format.
"""

from datetime import datetime
from typing import Any

from common.action_trace import ActionTraceEntry, Episode, SummaryCheckpoint


def format_timestamp(timestamp: datetime | str) -> str:
    """Format a timestamp for display.

    Parameters
    ----------
    timestamp : datetime | str
        Timestamp to format

    Returns
    -------
    str
        Formatted timestamp string
    """
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp)
    return timestamp.strftime("%H:%M:%S")


def print_action_trace(
    trace: list[ActionTraceEntry] | list[dict[str, Any]], 
    show_full: bool = False
) -> None:
    """Pretty print an action trace.

    Parameters
    ----------
    trace : list[ActionTraceEntry] | list[dict]
        Action trace to display
    show_full : bool
        Whether to show full results (default: truncate)
    """
    if not trace:
        print("No actions in trace.")
        return

    print(f"\n📜 Action Trace ({len(trace)} actions)")
    print("=" * 80)

    for i, entry in enumerate(trace, 1):
        # Handle both ActionTraceEntry objects and dicts
        if isinstance(entry, dict):
            timestamp = entry.get("timestamp", "")
            reasoning = entry.get("reasoning", "")
            action = entry.get("action", "")
            result = entry.get("result", "")
        else:
            timestamp = entry.timestamp
            reasoning = entry.reasoning
            action = entry.action
            result = entry.result

        # Format timestamp
        time_str = format_timestamp(timestamp) if timestamp else "??:??:??"

        # Print entry header
        print(f"\n{i}. [{time_str}] {action}")
        print(f"   💭 {reasoning}")

        # Handle result display
        if show_full or len(result) <= 200:
            print(f"   ✓ {result}")
        else:
            print(f"   ✓ {result[:200]}...")

    print("\n" + "=" * 80)


def print_episode_summary(episode: Episode | dict[str, Any]) -> None:
    """Print a summary of an episode.

    Parameters
    ----------
    episode : Episode | dict
        Episode to summarize
    """
    # Handle both Episode objects and dicts
    if isinstance(episode, dict):
        task = episode.get("task_description", "Unknown task")
        outcome = episode.get("outcome", "unknown")
        timestamp = episode.get("timestamp", "")
        action_count = len(episode.get("full_trace", []))
        
        checkpoint = episode.get("summary_checkpoint")
        if checkpoint:
            summary = checkpoint.get("summary", "No summary")
            lessons = checkpoint.get("lessons", [])
        else:
            summary = "No summary available"
            lessons = []
    else:
        task = episode.task_description
        outcome = episode.outcome
        timestamp = episode.timestamp
        action_count = len(episode.full_trace)
        
        if episode.summary_checkpoint:
            summary = episode.summary_checkpoint.summary
            lessons = episode.summary_checkpoint.lessons
        else:
            summary = "No summary available"
            lessons = []

    # Format display
    print("\n📚 Episode Summary")
    print("=" * 80)
    print(f"Task: {task}")
    print(f"Outcome: {outcome}")
    print(f"Started: {format_timestamp(timestamp) if timestamp else 'Unknown'}")
    print(f"Actions: {action_count}")
    print(f"\nSummary: {summary}")

    if lessons:
        print(f"\n🎓 Lessons Learned:")
        for lesson in lessons:
            print(f"  • {lesson}")

    print("=" * 80)


def print_episode_timeline(episodes: list[Episode] | list[dict[str, Any]]) -> None:
    """Print a timeline view of episodes.

    Parameters
    ----------
    episodes : list[Episode] | list[dict]
        Episodes to display
    """
    if not episodes:
        print("No episodes to display.")
        return

    print("\n📅 Episode Timeline")
    print("=" * 80)

    for episode in episodes:
        # Handle both Episode objects and dicts
        if isinstance(episode, dict):
            task = episode.get("task_description", "Unknown task")
            timestamp = episode.get("timestamp", "")
            outcome = episode.get("outcome", "unknown")
            action_count = len(episode.get("full_trace", []))
        else:
            task = episode.task_description
            timestamp = episode.timestamp
            outcome = episode.outcome
            action_count = len(episode.full_trace)

        time_str = format_timestamp(timestamp) if timestamp else "??:??:??"
        status_icon = "✅" if outcome == "task_complete" else "❌"

        print(f"{time_str} {status_icon} {task} ({action_count} actions)")

    print("=" * 80)


def print_memory_status(
    episode_count: int,
    total_actions: int,
    compressed_count: int = 0
) -> None:
    """Print memory system status.

    Parameters
    ----------
    episode_count : int
        Number of episodes stored
    total_actions : int
        Total number of actions across all episodes
    compressed_count : int
        Number of compressed episodes
    """
    print("\n🧠 Memory Status")
    print("=" * 40)
    print(f"Episodes: {episode_count}")
    print(f"Total Actions: {total_actions}")
    if compressed_count > 0:
        print(f"Compressed: {compressed_count}")
    print("=" * 40)