"""
Action trace management for Winston's episodic memory system.

This module implements the core memory architecture for Chapter 4, managing
action traces, progressive compression, and episode boundaries.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field

from loguru import logger
from openai import AsyncOpenAI
from jinja2 import Environment

from common.chroma_client import get_chroma_client


@dataclass
class ActionTraceEntry:
    """Single entry in an action trace - uniform across ALL actions.
    
    Fields:
    - timestamp: When the action occurred
    - reasoning: Why this action was chosen (from reasoning phase)
    - action: What action was taken (e.g., "task_complete", "EXECUTE_TOOL: fetch_url")
    - result: The complete outcome of the action as a string
    - task: The task this action was taken for
    
    The result field contains the COMPLETE outcome for any action:
    - task_complete: Both the reason AND the answer
    - task_blocked: The blocking reason
    - EXECUTE_TOOL: The tool's output
    - START_INTENT: The status message
    - etc.
    
    NO SPECIAL CASES - every action uses the same structure.
    """

    timestamp: datetime
    reasoning: str
    action: str
    result: str  # The complete outcome - no special fields!
    task: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "reasoning": self.reasoning,
            "action": self.action,
            "result": self.result,
            "task": self.task,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ActionTraceEntry:
        """Create from dictionary."""
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            reasoning=data["reasoning"],
            action=data["action"],
            result=data["result"],
            task=data.get("task"),
        )


@dataclass
class SummaryCheckpoint:
    """Progressive compression checkpoint."""

    summary: str
    summarized_up_to: int  # Index of last summarized action
    checkpoint_timestamp: datetime
    lessons: list[str] = field(default_factory=list)
    token_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "summary": self.summary,
            "summarized_up_to": self.summarized_up_to,
            "checkpoint_timestamp": self.checkpoint_timestamp.isoformat(),
            "lessons": self.lessons,
            "token_count": self.token_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SummaryCheckpoint:
        """Create from dictionary."""
        return cls(
            summary=data["summary"],
            summarized_up_to=data["summarized_up_to"],
            checkpoint_timestamp=datetime.fromisoformat(data["checkpoint_timestamp"]),
            lessons=data.get("lessons", []),
            token_count=data.get("token_count", 0),
        )


@dataclass
class Episode:
    """Complete episode with full trace and summary."""

    id: str
    task_description: str
    outcome: str  # "task_complete" or "task_blocked"
    result: str
    timestamp: datetime
    full_trace: list[ActionTraceEntry]
    summary_checkpoint: SummaryCheckpoint | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "task_description": self.task_description,
            "outcome": self.outcome,
            "result": self.result,
            "timestamp": self.timestamp.isoformat(),
            "full_trace": [entry.to_dict() for entry in self.full_trace],
            "summary_checkpoint": (
                self.summary_checkpoint.to_dict() if self.summary_checkpoint else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Episode:
        """Create from dictionary."""
        return cls(
            id=data["id"],
            task_description=data["task_description"],
            outcome=data["outcome"],
            result=data["result"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            full_trace=[
                ActionTraceEntry.from_dict(entry) for entry in data["full_trace"]
            ],
            summary_checkpoint=(
                SummaryCheckpoint.from_dict(data["summary_checkpoint"])
                if data.get("summary_checkpoint")
                else None
            ),
        )


class ActionTraceManager:
    """Manages episodes as the single source of truth.
    
    All operations are atomic disk operations - no in-memory state.
    The episode file contains both the full trace and compression checkpoints.
    The 'action trace' for prompts is dynamically generated from the episode.
    """

    def __init__(
        self,
        episodes_path: Path,
        agent_id: str = "WINSTON",
        compression_threshold: int = 2000,
        aclient: AsyncOpenAI | None = None,
        template_env: Environment | None = None,
        chroma_path: Path | None = None,
    ):
        """Initialize the action trace manager.

        Parameters
        ----------
        episodes_path : Path
            Directory to store episode files
        agent_id : str
            Unique identifier for the agent
        compression_threshold : int
            Token count threshold for triggering compression
        aclient : AsyncOpenAI | None
            OpenAI client for summarization (required for compression)
        template_env : Environment | None
            Jinja2 environment for templates (required for compression)
        chroma_path : Path | None
            Directory for ChromaDB persistence
        """
        self.agent_id = agent_id
        self.episodes_path = episodes_path / agent_id
        self.episodes_path.mkdir(parents=True, exist_ok=True)
        self.active_episode_path = self.episodes_path / "active_episode.json"
        self.compression_threshold = compression_threshold
        self.aclient = aclient
        self.template_env = template_env

        # Initialize ChromaDB for this agent (REQUIRED for Chapter 4)
        if not chroma_path:
            raise ValueError(
                "ChromaDB path is required for episodic memory. "
                "Episode indexing is a core feature of Chapter 4."
            )
        
        # Use the centralized client factory for consistency
        self.chroma_client = get_chroma_client(chroma_path)
        self.collection = self.chroma_client.get_or_create_collection(
            name=f"episodes_{agent_id}",
            metadata={"description": f"Episodic memories for {agent_id}"},
        )
        logger.info(
            f"ChromaDB collection 'episodes_{agent_id}' initialized at {chroma_path}"
        )
        # Index any existing episodes on startup
        self._index_existing_episodes()

        # NO IN-MEMORY STATE - everything is on disk
        logger.info(
            f"ActionTraceManager initialized for agent '{agent_id}' with episodes path: {self.episodes_path}"
        )

    @classmethod
    def create_agent(
        cls,
        agent_id: str,
        episodes_path: Path,
        compression_threshold: int = 2000,
        aclient: AsyncOpenAI | None = None,
        template_env: Environment | None = None,
        chroma_path: Path | None = None,
    ) -> "ActionTraceManager":
        """Create a new trace manager for an agent.

        This should only be called once per agent, typically by the kernel
        during initialization. If a manager already exists for this agent,
        it will be replaced.

        Parameters
        ----------
        agent_id : str
            Unique identifier for the agent
        episodes_path : Path
            Base directory for episodes (agent_id will be appended)
        compression_threshold : int
            Token count threshold for compression
        aclient : AsyncOpenAI | None
            OpenAI client for compression (required if compression is needed)
        template_env : Environment | None
            Jinja2 environment for templates (required for compression)
        chroma_path : Path | None
            Directory for ChromaDB persistence

        Returns
        -------
        ActionTraceManager
            The newly created trace manager instance for this agent
        """
        # Create the agent directory structure on disk
        agent_path = episodes_path / agent_id
        agent_path.mkdir(parents=True, exist_ok=True)
        
        # Create agent metadata file to mark this agent exists
        metadata_path = agent_path / "agent_metadata.json"
        metadata = {
            "agent_id": agent_id,
            "created_at": datetime.now().isoformat(),
            "compression_threshold": compression_threshold,
        }
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)
        
        # Create new instance
        instance = cls(
            episodes_path=episodes_path,
            agent_id=agent_id,
            compression_threshold=compression_threshold,
            aclient=aclient,
            template_env=template_env,
            chroma_path=chroma_path,
        )
        logger.info(f"Created new ActionTraceManager for agent '{agent_id}'")
        return instance

    @classmethod
    def get_agent(
        cls,
        agent_id: str,
        episodes_path: Path,
        aclient: AsyncOpenAI | None = None,
        template_env: Environment | None = None,
        chroma_path: Path | None = None,
    ) -> "ActionTraceManager":
        """Get the existing trace manager for an agent.

        This loads the agent from disk. If the agent doesn't exist on disk,
        it raises an error.

        Parameters
        ----------
        agent_id : str
            Unique identifier for the agent
        episodes_path : Path
            Base directory for episodes
        aclient : AsyncOpenAI | None
            OpenAI client (optional, needed for compression)
        template_env : Environment | None
            Jinja2 environment (optional, needed for compression)
        chroma_path : Path | None
            Directory for ChromaDB persistence

        Returns
        -------
        ActionTraceManager
            The trace manager instance for this agent

        Raises
        ------
        ValueError
            If no trace manager exists for this agent on disk
        """
        # Check if agent exists on disk
        agent_path = episodes_path / agent_id
        metadata_path = agent_path / "agent_metadata.json"
        
        if not metadata_path.exists():
            raise ValueError(
                f"No ActionTraceManager exists for agent '{agent_id}' on disk. "
                f"The kernel must create it first using create_agent()."
            )
        
        # Load metadata to get compression threshold
        with open(metadata_path, "r") as f:
            metadata = json.load(f)
        
        # Create instance that loads from disk
        instance = cls(
            episodes_path=episodes_path,
            agent_id=agent_id,
            compression_threshold=metadata.get("compression_threshold", 2000),
            aclient=aclient,
            template_env=template_env,
            chroma_path=chroma_path,
        )
        logger.info(f"Loaded ActionTraceManager for agent '{agent_id}' from disk")
        return instance

    def append_action(
        self,
        reasoning: str,
        action: str,
        result: str,
        task_description: str | None = None,
    ) -> None:
        """Append an action to the current episode.
        
        Atomic read-modify-write operation on active_episode.json.
        Preserves full trace while potentially updating compression checkpoint.

        Parameters
        ----------
        reasoning : str
            Why this action was chosen (from reasoning phase)
        action : str
            What action was taken
        result : str
            The complete outcome of the action
        task_description : str | None
            Task description (required for first action)
        """
        # Read current episode from disk
        if self.active_episode_path.exists():
            with open(self.active_episode_path, "r") as f:
                episode = json.load(f)
            current_task = episode.get("task", "")
            episode_start_time = (
                datetime.fromisoformat(episode["episode_start_time"])
                if episode.get("episode_start_time")
                else datetime.now()
            )
            episode_id = episode.get("id")
            checkpoint = episode.get("checkpoint")
            full_trace = episode.get("full_trace", [])
        else:
            # Initialize new episode if none exists
            current_task = ""
            episode_start_time = datetime.now()
            episode_id = str(uuid.uuid4())
            checkpoint = None
            full_trace = []
        
        # Update task if needed
        if not current_task and task_description:
            current_task = task_description
            episode_start_time = datetime.now()
            episode_id = str(uuid.uuid4())
            logger.debug(f"Starting new episode {episode_id} for task: {task_description}")

        # Create and append new entry
        entry = ActionTraceEntry(
            timestamp=datetime.now(),
            reasoning=reasoning,
            action=action,
            result=result,
            task=task_description or current_task,
        )
        full_trace.append(entry.to_dict())
        
        logger.trace(
            f"Action appended to episode: {action} (full_trace length: {len(full_trace)})"
        )

        # TODO: Check if compression needed for prompt optimization
        # if self._estimate_tokens(full_trace) > self.compression_threshold:
        #     checkpoint = self._compress_for_prompt(full_trace[:-10])

        # Write episode back to disk atomically
        episode_data = {
            "id": episode_id,
            "task": current_task,
            "episode_start_time": episode_start_time.isoformat(),
            "checkpoint": checkpoint,
            "full_trace": full_trace,  # Always preserve full trace
        }
        with open(self.active_episode_path, "w") as f:
            json.dump(episode_data, f, indent=2)

    async def compress_if_needed(self) -> None:
        """Check if compression is needed and perform it.
        
        TODO: Refactor to read from disk instead of using in-memory state.
        Currently disabled to maintain disk-only operations.
        """
        logger.trace("Compression temporarily disabled - needs disk-based refactor")
        return

    async def _compress_trace(self) -> None:
        """Perform progressive compression on the trace."""
        logger.info("Performing progressive compression on action trace")

        try:
            # Determine what to summarize
            if self.current_checkpoint:
                # Summarize from last checkpoint to current
                start_idx = self.current_checkpoint.summarized_up_to + 1
                previous_summary = self.current_checkpoint.summary
            else:
                # First compression - summarize from beginning
                start_idx = 0
                previous_summary = None

            # Leave last 5 actions uncompressed for recent context
            end_idx = max(start_idx, len(self.current_trace) - 5)

            if end_idx <= start_idx:
                logger.trace("Not enough new actions to compress")
                return

            actions_to_summarize = self.current_trace[start_idx:end_idx]

            # Use template to create summarization prompt
            template = self.template_env.get_template("common/summarize_episode.md")
            prompt = await template.render_async(
                task_description=self.current_task,
                actions=actions_to_summarize,
                previous_summary=previous_summary,
                is_checkpoint=True,  # This is a checkpoint, not final
            )

            # Call LLM for summarization
            response = await self.aclient.chat.completions.create(
                model="gpt-4o-mini",  # Use smaller model for summarization
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )

            summary_data = json.loads(response.choices[0].message.content)

            # Create new checkpoint
            self.current_checkpoint = SummaryCheckpoint(
                summary=summary_data["summary"],
                summarized_up_to=end_idx - 1,
                checkpoint_timestamp=datetime.now(),
                lessons=summary_data.get("lessons", []),
                token_count=len(summary_data["summary"]) // 4,  # Rough estimate
            )

            logger.success(
                f"Compression complete: summarized actions {start_idx}-{end_idx - 1}, "
                f"extracted {len(self.current_checkpoint.lessons)} lessons"
            )

        except Exception as e:
            logger.error(f"Compression failed: {e}")

    def _clear_active_state(self) -> None:
        """Clear all active episode state and remove the active episode file.
        
        This is the common clearing logic used by both clear_session and start_new_episode.
        """
        # Simply delete the active episode file - no in-memory state to clear
        if self.active_episode_path.exists():
            self.active_episode_path.unlink()

    def clear_session(self) -> None:
        """Clear any persisted active trace from a previous session.
        
        This should be called when starting a new kernel session to ensure
        we don't carry over traces from previous runs.
        """
        self._clear_active_state()
        logger.info(f"Cleared active trace from previous session for agent {self.agent_id}")

    def start_new_episode(self, task_description: str) -> None:
        """Start a new episode, finalizing the current one if it exists.

        Parameters
        ----------
        task_description : str
            Description of the new task/episode
        """
        # Finalize current episode if it exists
        if self.has_active_episode():
            self.finalize_episode("context_shift", f"Starting new episode: {task_description}")
        
        # Then write new empty episode to disk
        episode_data = {
            "id": str(uuid.uuid4()),
            "task": task_description,
            "episode_start_time": datetime.now().isoformat(),
            "checkpoint": None,
            "full_trace": [],
        }
        with open(self.active_episode_path, "w") as f:
            json.dump(episode_data, f, indent=2)

        logger.info(f"Started new episode for task: {task_description}")

    def finalize_episode(
        self,
        outcome: str = "task_complete",
        result: str = "Task completed successfully",
    ) -> Episode:
        """Finalize the current episode and save to disk.

        Parameters
        ----------
        outcome : str
            The outcome of the episode ("task_complete" or "task_blocked")
        result : str
            The final result or reason

        Returns
        -------
        Episode
            The finalized episode
        """
        # Read current episode from disk
        if not self.active_episode_path.exists():
            logger.warning("No active episode to finalize")
            return None
            
        with open(self.active_episode_path, "r") as f:
            episode_data = json.load(f)
        
        # Convert trace entries from dict to ActionTraceEntry objects
        full_trace = [
            ActionTraceEntry.from_dict(entry)
            for entry in episode_data.get("full_trace", [])
        ]
        
        # Create episode object with finalization metadata
        episode = Episode(
            id=episode_data.get("id", str(uuid.uuid4())),
            task_description=episode_data.get("task", ""),
            outcome=outcome,
            result=result,
            timestamp=datetime.fromisoformat(episode_data.get("episode_start_time", datetime.now().isoformat())),
            full_trace=full_trace,
            summary_checkpoint=(
                SummaryCheckpoint.from_dict(episode_data["checkpoint"])
                if episode_data.get("checkpoint")
                else None
            ),
        )

        # Save finalized episode to permanent location
        episode_file = self.episodes_path / f"{episode.id}.json"
        with open(episode_file, "w") as f:
            json.dump(episode.to_dict(), f, indent=2)

        # Index in ChromaDB (required)
        self._index_episode(episode)

        logger.info(
            f"Episode finalized: {episode.id} ({len(episode.full_trace)} actions) -> {episode_file}"
        )

        # Clear active episode file
        if self.active_episode_path.exists():
            self.active_episode_path.unlink()

        return episode

    def get_current_trace(self) -> list[ActionTraceEntry]:
        """Get the current action trace for prompt injection.

        Dynamically generates a view from the active episode:
        - If checkpoint exists: returns checkpoint summary + last N actions
        - If no checkpoint: returns last N actions
        
        This is generated, not stored separately.
        """
        if not self.active_episode_path.exists():
            return []
        
        try:
            with open(self.active_episode_path, "r") as f:
                episode = json.load(f)
            
            full_trace = episode.get("full_trace", [])
            checkpoint = episode.get("checkpoint")
            
            # Generate view for prompt injection
            if checkpoint and len(full_trace) > 10:
                # Return compressed view: checkpoint + recent actions
                # Note: In a full implementation, we'd convert checkpoint.summary
                # to a synthetic ActionTraceEntry for consistent interface
                recent_actions = full_trace[-10:]  # Last 10 actions
                return [
                    ActionTraceEntry.from_dict(entry)
                    for entry in recent_actions
                ]
            else:
                # No compression yet, return last 20 actions
                recent_actions = full_trace[-20:] if len(full_trace) > 20 else full_trace
                return [
                    ActionTraceEntry.from_dict(entry)
                    for entry in recent_actions
                ]
                
        except Exception as e:
            logger.error(f"Failed to generate trace view from episode: {e}")
            return []

    def has_active_episode(self) -> bool:
        """Check if there's an active episode."""
        if not self.active_episode_path.exists():
            return False
        
        try:
            with open(self.active_episode_path, "r") as f:
                episode = json.load(f)
            return bool(episode.get("task"))
        except Exception:
            return False

    def get_recent_context(self, num_actions: int = 10) -> str:
        """Get a formatted string of recent actions for context.

        Parameters
        ----------
        num_actions : int
            Number of recent actions to include

        Returns
        -------
        str
            Formatted context string
        """
        # Read from episode file
        if not self.active_episode_path.exists():
            return "No actions in current episode."
        
        try:
            with open(self.active_episode_path, "r") as f:
                episode = json.load(f)
            
            full_trace = episode.get("full_trace", [])
            if not full_trace:
                return "No actions in current episode."
            
            recent = full_trace[-num_actions:]
            context_parts = []
            
            checkpoint = episode.get("checkpoint")
            if checkpoint and len(full_trace) > num_actions:
                context_parts.append(f"Summary: {checkpoint.get('summary', '')}")
                context_parts.append("")
            
            for entry_dict in recent:
                entry = ActionTraceEntry.from_dict(entry_dict)
                context_parts.append(
                    f"[{entry.timestamp.strftime('%H:%M:%S')}] {entry.action}"
                )
                context_parts.append(f"  Result: {entry.result[:100]}...")
                context_parts.append("")
            
            return "\n".join(context_parts)
            
        except Exception as e:
            logger.error(f"Failed to get recent context: {e}")
            return "Error reading episode context."


    def _index_existing_episodes(self) -> None:
        """Index any episodes on disk that aren't in ChromaDB."""

        episode_files = list(self.episodes_path.glob("*.json"))

        if not episode_files:
            logger.trace("No existing episodes to index")
            return

        # Get IDs already in ChromaDB
        existing_ids = set()
        if self.collection.count() > 0:
            results = self.collection.get()
            existing_ids = set(results["ids"])

        # Index missing episodes
        indexed_count = 0
        for episode_file in episode_files:
            if episode_file.name == "active_trace.json":
                continue  # Skip the active trace file

            episode_id = episode_file.stem

            if episode_id in existing_ids:
                continue

            try:
                with open(episode_file, "r") as f:
                    episode_data = json.load(f)

                episode = Episode.from_dict(episode_data)
                self._index_episode(episode)
                indexed_count += 1

            except Exception as e:
                logger.error(f"Failed to index episode {episode_file}: {e}")

        if indexed_count > 0:
            logger.info(f"Indexed {indexed_count} existing episodes")

    def _index_episode(self, episode: Episode) -> None:
        """Index an episode in ChromaDB for semantic search.

        Parameters
        ----------
        episode : Episode
            Episode to index
        """

        # Build indexable text from episode
        index_parts = [
            episode.task_description,
            episode.result,
        ]

        # Add summary if available
        if episode.summary_checkpoint:
            index_parts.append(episode.summary_checkpoint.summary)
            index_parts.extend(episode.summary_checkpoint.lessons)

        # Add a sample of actions for additional context
        for entry in episode.full_trace[:5]:  # First 5 actions
            index_parts.append(entry.action)

        index_text = " ".join(filter(None, index_parts))

        # Prepare metadata
        metadata = {
            "task": episode.task_description,
            "outcome": episode.outcome,
            "timestamp": episode.timestamp.isoformat(),
            "has_lessons": bool(
                episode.summary_checkpoint and episode.summary_checkpoint.lessons
            ),
            "action_count": len(episode.full_trace),
        }

        # Store in ChromaDB
        self.collection.add(
            documents=[index_text], metadatas=[metadata], ids=[episode.id]
        )

        logger.info(
            f"Indexed episode {episode.id} in ChromaDB: '{episode.task_description[:50]}...' "
            f"({len(episode.full_trace)} actions, {len(index_text)} chars indexed)"
        )

    async def start_new_episode_with_reason(self, reason: str) -> None:
        """Start new episode, optionally finalizing current one.

        Parameters
        ----------
        reason : str
            Reason for starting new episode
        """
        if self.has_active_episode():
            self.finalize_episode("context_shift", reason)
        self.start_new_episode(reason)

    async def search_episodes(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search episodes using ChromaDB semantic search.

        Parameters
        ----------
        query : str
            Natural language query
        limit : int
            Maximum number of results

        Returns
        -------
        list[dict]
            Relevant episodes with metadata and relevance scores
        """
        if self.collection.count() == 0:
            logger.warning("No episodes indexed for search")
            return []

        try:
            # Perform semantic search
            results = self.collection.query(
                query_texts=[query], n_results=min(limit, self.collection.count())
            )

            if not results["ids"] or not results["ids"][0]:
                return []

            # Load full episode data for each result
            episodes = []
            for idx, episode_id in enumerate(results["ids"][0]):
                # Load from disk
                episode_file = self.episodes_path / f"{episode_id}.json"

                if not episode_file.exists():
                    logger.warning(f"Episode file not found: {episode_file}")
                    continue

                try:
                    with open(episode_file, "r") as f:
                        episode_data = json.load(f)

                    # Add relevance score
                    if results["distances"]:
                        # Convert distance to similarity score (0-1)
                        distance = results["distances"][0][idx]
                        episode_data["relevance_score"] = 1.0 / (1.0 + distance)

                    # Extract relevant actions based on query
                    if episode_data.get("full_trace"):
                        episode_data["relevant_actions"] = (
                            self._extract_relevant_actions(
                                episode_data["full_trace"], query
                            )
                        )

                    episodes.append(episode_data)

                except Exception as e:
                    logger.error(f"Failed to load episode {episode_id}: {e}")

            return episodes

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def _extract_relevant_actions(
        self, full_trace: list[dict], query: str
    ) -> list[dict]:
        """Extract actions most relevant to the query.

        Parameters
        ----------
        full_trace : list[dict]
            Complete action trace
        query : str
            Search query

        Returns
        -------
        list[dict]
            Most relevant actions
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored_actions = []
        for action in full_trace:
            # Score based on keyword overlap
            action_text = (
                f"{action['action']} {action['reasoning']} {action['result']}".lower()
            )
            action_words = set(action_text.split())

            overlap = len(query_words & action_words)
            if overlap > 0:
                scored_actions.append((overlap, action))

        # Sort by score and return top actions
        scored_actions.sort(key=lambda x: x[0], reverse=True)
        return [action for _, action in scored_actions[:5]]
