#!/usr/bin/env python3
"""
Winston Chapter 4: From Action Traces to Episodic Memory

This kernel evolves Chapter 3's design by using FastMCP idiomatically
for cleaner tool calling without the session abstraction.
"""

from __future__ import annotations

import json
import asyncio
import sys
from datetime import datetime
import time
from pathlib import Path
from typing import Any, cast

import click
from openai import AsyncOpenAI
from loguru import logger
from jinja2 import Environment, FileSystemLoader
from chromadb import Collection

# Import all Winston modules
from common.config import Config, setup_logging
from common.mcp_host import MCPHost
from common import (
    IntentGenerator,
    initialize_intent_database,
    query_intent_nodes,
    ActionTraceManager,
    print_action_trace,
    print_episode_summary,
    print_memory_status,
)
from common.tool_identity import ToolIdentity

# Minimal core functions - the only tools Winston needs built-in
REASONING_TOOLS = [
    {
        "type": "function",
        "name": "task_complete",
        "description": "Mark the current task as completed with a reason and optional result.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why the task is complete",
                },
                "result": {
                    "type": "string",
                    "description": "The final answer or result if the task was a question or required a specific output",
                },
            },
            "required": ["reason"],
            "additionalProperties": False,
        },
        "strict": False,
    },
    {
        "type": "function",
        "name": "task_blocked",
        "description": "Mark the current task as blocked with a reason.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Why the task is blocked",
                }
            },
            "required": ["reason"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "do",
        "description": "Execute an action with given intent and rationale.",
        "parameters": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "description": "The intent or goal of the action",
                },
                "rationale": {
                    "type": "string",
                    "description": "Why this action should be taken",
                },
            },
            "required": ["intent", "rationale"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "introspect",
        "description": "Discover what capabilities would be available for a hypothetical intent without executing them.",
        "parameters": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "description": "The hypothetical intent to explore",
                },
                "purpose": {
                    "type": "string",
                    "description": "Why you want to discover these capabilities",
                },
            },
            "required": ["intent", "purpose"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]

# Action tools for resolving intents to concrete actions
# Note: execute_tool uses strict=False because the arguments object must
# accept dynamic properties that vary based on the specific tool being called
ACTION_TOOLS = [
    {
        "type": "function",
        "name": "execute_tool",
        "description": "Execute a specific tool with the provided arguments.",
        "parameters": {
            "type": "object",
            "properties": {
                "tool_uri": {
                    "type": "string",
                    "description": "The tool URI in format 'tool::server_name::tool_name'",
                },
                "arguments": {
                    "type": "object",
                    "description": "The arguments to pass to the tool",
                },
            },
            "required": ["tool_uri", "arguments"],
            "additionalProperties": False,
        },
        "strict": False,
    },
    {
        "type": "function",
        "name": "refine_intent",
        "description": "Refine the current intent using an L2 intent category.",
        "parameters": {
            "type": "object",
            "properties": {
                "intent_id": {
                    "type": "string",
                    "description": "The ID of the L2 intent to use for refinement",
                },
                "explanation": {
                    "type": "string",
                    "description": "Explanation of how this refinement helps",
                },
            },
            "required": ["intent_id", "explanation"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "insufficient_information",
        "description": "Tools are suitable but essential parameters are missing.",
        "parameters": {
            "type": "object",
            "properties": {
                "missing_parameters": {
                    "type": "string",
                    "description": "Description of what specific information is needed",
                }
            },
            "required": ["missing_parameters"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "no_suitable_tool",
        "description": "None of the available tools are suitable for the intent.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Explanation of why no tool is suitable",
                }
            },
            "required": ["reason"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


class WinstonKernel:
    """Encapsulates Winston's episodic memory cognitive kernel.

    This class maintains all state and configuration needed for the kernel,
    avoiding global variables and making it reusable as a library.
    """

    def __init__(self, config: Config):
        """Initialize the kernel with configuration.

        Parameters
        ----------
        config : Config
            Configuration object with all settings
        """
        self.config = config
        self.agent_id = config.get("AGENT_ID", "WINSTON")  # Agent identity
        self.aclient = AsyncOpenAI(api_key=config["OPENAI_API_KEY"])
        self.model = config["OPENAI_MODEL"]
        self.template_env = Environment(
            loader=FileSystemLoader("./prompts"), enable_async=True
        )
        # Add custom filter for JSON parsing in templates
        self.template_env.filters["from_json"] = json.loads

        # These will be initialized in setup methods
        self.collection: Collection | None = None
        self.mcp_host: MCPHost | None = None
        self.trace_manager: ActionTraceManager | None = None

    async def __aenter__(self):
        """Async context manager entry - initialize all components."""
        # 1. Setup Database
        persist_dir = str(self.config.get_chapter_path("chroma_db", create=True))
        collection_name = self.config["INTENT_COLLECTION_NAME"]
        self.collection = initialize_intent_database(persist_dir, collection_name)
        logger.trace(f"Collection initialized with: {self.collection.count()} items.")

        # 2. Setup MCP Host with variable substitution
        mcp_config_path = Path("chapter04") / "mcp_config.json"
        self.mcp_host = MCPHost(mcp_config_path, self.config)
        await self.mcp_host.startup()

        # 3. Generate and Index Intents (handles config change detection internally)
        intent_generator = IntentGenerator(
            self.aclient,
            self.mcp_host,
            self.template_env,
            persist_dir,
            collection_name,
            self.config["INTENT_INSERTION_THRESHOLD"],
        )
        regenerated = await intent_generator.generate_and_store_intents_if_needed(
            self.collection
        )

        # 4. Initialize Action Trace Manager for episodic memory
        episodes_path = self.config.get_chapter_path("episodes", create=True)
        chroma_path = self.config.get_chapter_path("chroma_db", create=True)
        # Create the singleton trace manager for this agent
        self.trace_manager = ActionTraceManager.create_agent(
            agent_id=self.agent_id,
            episodes_path=episodes_path,  # create_agent will create episodes_path/WINSTON/
            compression_threshold=self.config.get("COMPRESSION_THRESHOLD", 2000),
            aclient=self.aclient,
            template_env=self.template_env,
            chroma_path=chroma_path,
        )

        # Clear any persisted trace from previous session
        self.trace_manager.clear_session()

        logger.info(
            f"Action trace manager initialized with episodes at: {episodes_path}"
        )

        if regenerated:
            print(f"\nRegenerated intent index with {self.collection.count()} items.")
        else:
            print(f"\nIntent database ready with {self.collection.count()} items.")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - handle cleanup."""
        if self.mcp_host:
            logger.info("Shutting down MCP host...")
            await self.mcp_host.shutdown()
            logger.info("MCP host shutdown complete")

    def _get_timestamp_with_tz(self) -> str:
        """Get current timestamp with timezone information.

        Returns formatted string like:
        2025-08-10T14:43:45-08:00 (PST)
        """
        now = datetime.now().astimezone()
        # Get timezone name (e.g., PST, PDT, EST, etc.)
        tz_name = time.tzname[time.daylight]
        return f"{now.isoformat()} ({tz_name})"

    def _add_to_trace(self, reasoning: str, action: str, result: str) -> None:
        """Add an entry to the action trace - uniform for ALL actions."""
        # Only use trace manager - no duplicate traces!
        if self.trace_manager:
            self.trace_manager.append_action(
                reasoning=reasoning,
                action=action,
                result=result,
                task_description=getattr(self, "current_task", None),
            )
        else:
            logger.warning("Trace manager not initialized, action not recorded")

        logger.trace(f"Trace: {action} -> {result[:100]}...")

    def _task_complete(self, reason: str, result: str | None = None) -> str:
        """Mark task as completed.

        Parameters
        ----------
        reason : str
            Explanation of why the task is complete.
        result : str | None, optional
            The final answer or result if the task was a question
            or required a specific output.

        Returns
        -------
        str
            Formatted completion message.
        """
        # Pass the actual reasoning and result to the trace
        # If there's no separate result, the reason IS the result
        trace_result = result if result else reason
        self._add_to_trace(reason, "task_complete", trace_result)

        # DON'T finalize episode on task_complete - let Winston decide episode boundaries
        # Episodes should span multiple related tasks

        if result:
            print(f"\n[COMPLETE] Task Complete: {reason}")
            print(f"\nResult:\n{result}")
        else:
            print(f"\n[COMPLETE] Task Complete: {reason}")
        return "COMPLETE"

    def _task_blocked(self, reason: str) -> str:
        """Mark task as blocked."""
        # Pass the actual reasoning as both reasoning and result
        self._add_to_trace(reason, "task_blocked", reason)

        # DON'T finalize episode on task_blocked - let Winston decide episode boundaries
        # Episodes should span multiple related tasks

        print(f"\n[BLOCKED] Task Blocked: {reason}")
        return "BLOCKED"

    async def _reason_about_task(self, task_description: str) -> dict[str, Any] | None:
        """The reasoning phase - let the model think about the task."""
        try:
            # Build workspace context
            workspace_context = {
                "filesystem_root": {
                    "value": str(
                        self.config.get_chapter_path("workspace", create=True)
                    ),
                    "description": "Root directory for all filesystem operations",
                }
            }

            # Get current trace from trace manager - just pass the entries directly!
            action_trace = []
            if self.trace_manager and self.trace_manager.has_active_episode():
                action_trace = self.trace_manager.get_current_trace()

            template = self.template_env.get_template("chapter04/reasoning.md")
            prompt = await template.render_async(
                agent_id=self.agent_id,
                task_description=task_description,
                action_trace=action_trace,
                timestamp=self._get_timestamp_with_tz(),
                workspace=workspace_context,
            )

            # Log the rendered template for debugging
            logger.info("REASONING TEMPLATE RENDERED:")
            logger.info("=" * 80)
            logger.info(prompt)
            logger.info("=" * 80)

            response = await self.aclient.responses.create(
                model=self.model,
                input=prompt,
                tools=cast(Any, REASONING_TOOLS),
                tool_choice="auto",
            )

            if response.status == "completed":
                for item in response.output:
                    if item.type == "function_call":
                        decision = {
                            "function": item.name,
                            "arguments": json.loads(item.arguments),
                        }
                        logger.trace(
                            f"REASONING DECISION: {decision['function']} with args: {decision['arguments']}"
                        )
                        return decision
                logger.warning("REASONING RESULT: No function calls returned from LLM")
                return None
            else:
                logger.warning(f"REASONING RESULT: Response status {response.status}")
                return None
        except Exception as e:
            logger.error(f"Reasoning failed: {e}")
            return None

    # These functions are no longer needed with the unified action prompt
    # They have been replaced by the single LLM call in execute_intent

    async def _execute_intent(
        self,
        intent: str,
        rationale: str,
        task_description: str,
    ) -> None:
        """Match intent to a flat list of L1/L2 intents and execute the chosen action."""
        logger.info(f"Executing intent: '{intent}'")
        self._add_to_trace(
            rationale,
            f"START_INTENT: {intent}",
            f"Starting intent discovery for: {intent}",
        )

        # Query the vector database for a flat list of matching intents (both L1 and L2)
        logger.trace(f"Querying intent database for: '{intent}'")
        options = query_intent_nodes(self.collection, intent)

        if not options:
            logger.warning(
                f"INTENT DATABASE QUERY RESULT: No matching options found for '{intent}'"
            )
            self._add_to_trace(
                rationale, intent, "No matching options found in intent database."
            )
            return

        logger.trace(
            f"INTENT DATABASE QUERY RESULT: Found {len(options)} matching options"
        )
        for i, option in enumerate(options):
            logger.trace(
                f"Option {i + 1}: ID={option.get('id', 'N/A')}, Type={option.get('type', 'N/A')}, Document={option.get('document', '')[:100]}..."
            )
        logger.trace(f"Full options data for template: {options}")

        # Build action prompt with available options
        try:
            # Build workspace context
            workspace_context = {
                "filesystem_root": {
                    "value": str(
                        self.config.get_chapter_path("workspace", create=True)
                    ),
                    "description": "Root directory for all filesystem operations",
                }
            }

            # Get current trace from trace manager for action phase too
            action_trace = []
            if self.trace_manager and self.trace_manager.has_active_episode():
                action_trace = self.trace_manager.get_current_trace()

            action_template = self.template_env.get_template("chapter04/action.md")
            action_prompt = await action_template.render_async(
                agent_id=self.agent_id,  # Pass agent identity so Winston knows who they are
                task_description=task_description,
                current_intent=intent,
                intent_rationale=rationale,
                options=options,
                action_trace=action_trace,
                timestamp=self._get_timestamp_with_tz(),
                workspace=workspace_context,
            )

            # Log the rendered template for debugging
            logger.info("ACTION TEMPLATE RENDERED:")
            logger.info("=" * 80)
            logger.info(action_prompt)
            logger.info("=" * 80)

            # Call OpenAI with action prompt and global ACTION_TOOLS
            response = await self.aclient.responses.create(
                model=self.model,
                input=action_prompt,
                tools=cast(Any, ACTION_TOOLS),
                tool_choice="auto",
            )

            # Process the response
            if response.status != "completed":
                logger.warning(
                    f"ACTION SELECTION RESULT: Response status {response.status}"
                )
                self._add_to_trace(
                    rationale, intent, f"Response status: {response.status}"
                )
                return

            function_call_found = False
            for item in response.output:
                if item.type == "function_call":
                    function_call_found = True
                    function_name = item.name

                    # Defensive parsing of arguments
                    try:
                        arguments = json.loads(item.arguments)
                    except json.JSONDecodeError as e:
                        logger.error(
                            f"ACTION SELECTION ERROR: Failed to parse tool arguments: {e}"
                        )
                        self._add_to_trace(
                            rationale, intent, f"Failed to parse tool arguments: {e}"
                        )
                        return
                    break

            if not function_call_found:
                logger.warning(
                    "NO_FUNCTION_CALL: LLM failed to select an action - no function calls returned"
                )
                self._add_to_trace(
                    rationale,
                    intent,
                    "NO_FUNCTION_CALL: LLM failed to select an action.",
                )
                return

            logger.info(
                f"ACTION SELECTION RESULT: {function_name} with args: {json.dumps(arguments, indent=2)}"
            )

            # Handle the different action types
            if function_name == "execute_tool":
                # Defensive extraction of required arguments
                tool_uri = arguments.get("tool_uri")
                tool_args = arguments.get("arguments", {})

                if not tool_uri:
                    error_msg = "Missing required 'tool_uri' argument for execute_tool"
                    logger.error(f"EXECUTE_TOOL ERROR: {error_msg}")
                    self._add_to_trace(rationale, "EXECUTE_TOOL", error_msg)
                    return

                # Parse tool_uri to extract server_name and tool_name
                try:
                    server_name, tool_name = ToolIdentity.parse_tool_uri(tool_uri)
                except ValueError as e:
                    error_msg = str(e)
                    logger.error(f"EXECUTE_TOOL ERROR: {error_msg}")
                    self._add_to_trace(
                        rationale, f"EXECUTE_TOOL: {tool_uri}", error_msg
                    )
                    return

                logger.trace(
                    f"Parsed tool_uri '{tool_uri}' -> server: '{server_name}', tool: '{tool_name}'"
                )

                # Check if server exists
                if server_name not in self.mcp_host.server_names:
                    error_msg = f"No client for server '{server_name}'"
                    logger.error(f"EXECUTE_TOOL ERROR: {error_msg}")
                    logger.trace(f"Available servers: {self.mcp_host.server_names}")
                    self._add_to_trace(
                        rationale, f"EXECUTE_TOOL: {tool_name}", error_msg
                    )
                    return

                # Log the complete arguments for debugging
                logger.info(f"Tool URI: {tool_uri}")
                logger.info(f"Tool arguments: {json.dumps(tool_args, indent=2)}")
                logger.trace(f"Tool arguments type: {type(tool_args)}")

                logger.success(
                    f"Executing tool '{tool_name}' on server '{server_name}' with args: {tool_args}"
                )

                try:
                    # Log exactly what we're about to send to MCP
                    logger.info("CALLING MCP TOOL:")
                    logger.info(f"  Server: {server_name}")
                    logger.info(f"  Tool: {tool_name}")
                    logger.info(f"  Arguments: {json.dumps(tool_args, indent=4)}")

                    # Use FastMCP idiomatic call_tool method
                    tool_result = await self.mcp_host.call_tool(
                        server_name, tool_name, tool_args
                    )
                    result_str = json.dumps([
                        c.model_dump() for c in tool_result.content
                    ])
                    logger.trace(f"EXECUTE_TOOL RESULT: {result_str[:200]}...")
                    self._add_to_trace(
                        rationale, f"EXECUTE_TOOL: {tool_name}", result_str
                    )

                except Exception as e:
                    error_msg = f"Tool execution failed: {e}"
                    logger.error(
                        f"EXECUTE_TOOL ERROR: {error_msg} (args: {tool_args}, type: {type(tool_args)})"
                    )
                    self._add_to_trace(
                        rationale, f"EXECUTE_TOOL: {tool_uri}", error_msg
                    )

            elif function_name == "refine_intent":
                # Defensive extraction of required arguments
                intent_id = arguments.get("intent_id")
                explanation = arguments.get("explanation", "")

                if not intent_id:
                    error_msg = (
                        "Missing required 'intent_id' argument for refine_intent"
                    )
                    logger.error(f"REFINE_INTENT ERROR: {error_msg}")
                    self._add_to_trace(
                        rationale, f"REFINE_INTENT: {intent_id}", error_msg
                    )
                    return

                logger.trace(f"Refining intent with ID: {intent_id}")

                # Find the intent document from the options
                refined_intent = None
                for option in options:
                    if option.get("id") == intent_id:
                        refined_intent = option.get("document", "")
                        break

                if refined_intent:
                    logger.trace(
                        f"REFINE_INTENT SUCCESS: Found intent document for ID {intent_id}"
                    )
                    self._add_to_trace(
                        rationale,
                        f"REFINE_INTENT: {intent_id}",
                        f"Refined to: {refined_intent}. {explanation}",
                    )
                else:
                    logger.error(
                        f"REFINE_INTENT ERROR: Failed to find intent document for ID {intent_id}"
                    )
                    self._add_to_trace(
                        rationale,
                        f"REFINE_INTENT: {intent_id}",
                        f"Failed to find intent document. {explanation}",
                    )

            elif function_name == "insufficient_information":
                missing = arguments.get("missing_parameters", "Unknown parameters")
                logger.trace(f"INSUFFICIENT_INFORMATION: {missing}")
                self._add_to_trace(
                    rationale, intent, f"INSUFFICIENT_INFORMATION: {missing}"
                )

            elif function_name == "no_suitable_tool":
                reason = arguments.get("reason", "No reason provided")
                logger.trace(f"NO_SUITABLE_TOOL: {reason}")
                self._add_to_trace(rationale, intent, f"NO_SUITABLE_TOOL: {reason}")

            else:
                logger.warning(
                    f"UNKNOWN ACTION: Unexpected function name '{function_name}' with args: {arguments}"
                )
                self._add_to_trace(
                    rationale, intent, f"UNKNOWN_ACTION: {function_name}"
                )

        except Exception as e:
            error_msg = f"Action phase error: {e}"
            logger.error(error_msg)
            self._add_to_trace(rationale, intent, error_msg)

    async def _introspect_intent(
        self,
        intent: str,
        purpose: str,
        task_description: str,
    ) -> None:
        """Discover capabilities for a hypothetical intent without executing.

        This enables meta-cognitive exploration - Winston can discover what tools
        would be available for an intent without actually using them.
        """
        logger.info(f"Introspecting capabilities for: '{intent}'")

        # Query the vector database for matching intents
        logger.trace(f"Querying intent database for hypothetical: '{intent}'")
        options = query_intent_nodes(self.collection, intent)

        if not options:
            discovery = "No matching capabilities found for this intent"
            logger.trace(f"INTROSPECT RESULT: {discovery}")
            self._add_to_trace(purpose, f"INTROSPECT: {intent}", discovery)
            return

        # Build a summary of discovered capabilities
        discovered_tools = []
        seen_tools = set()  # Avoid duplicates

        for option in options:
            option_type = option.get("type", "")
            option_id = option.get("id", "unknown")

            # L1 and L2 intents that represent tool capabilities
            if option_type == "L1":
                # Parse L1 intent ID: intent::L1::server_name::tool_name
                parts = option_id.split("::")
                if len(parts) >= 4:
                    server = parts[2]
                    tool = parts[3]
                    tool_key = f"{server}::{tool}"

                    if tool_key not in seen_tools:
                        seen_tools.add(tool_key)
                        tool_info = {
                            "name": tool,
                            "server": server,
                            "description": option.get("document", "")[:200],
                        }
                        discovered_tools.append(tool_info)
            # Skip L2 intents - they're categories not specific tools
            elif option_type == "tool":
                # Direct tool reference (shouldn't happen with current indexing)
                tool_info = {
                    "name": option.get("id", "unknown"),
                    "description": option.get("document", "")[:200],
                    "server": option.get("metadata", {}).get("server_name", "unknown"),
                }
                discovered_tools.append(tool_info)

        if discovered_tools:
            discovery = f"Discovered {len(discovered_tools)} capabilities:\n"
            for tool in discovered_tools[:5]:  # Limit to first 5 for brevity
                discovery += f"- {tool['name']} ({tool['server']}): {tool['description'][:100]}...\n"
        else:
            discovery = f"Found {len(options)} intent categories but no specific tools"

        logger.success(f"INTROSPECT COMPLETE: Found {len(discovered_tools)} tools")
        self._add_to_trace(purpose, f"INTROSPECT: {intent}", discovery)

    async def run_cognitive_loop(
        self,
        task_description: str,
        max_iterations: int = 10,
    ) -> str:
        """The pure cognitive loop - reason, act, repeat."""
        logger.info(f"Starting: {task_description}")

        # Store current task for trace manager
        self.current_task = task_description

        for iteration in range(max_iterations):
            logger.trace(f"Iteration {iteration + 1}")

            decision = await self._reason_about_task(task_description)
            if not decision:
                logger.warning("Agent failed to make a decision. Blocking task.")
                return self._task_blocked(
                    "Agent failed to make a decision in the reasoning step."
                )

            function_name = decision["function"]
            args = decision["arguments"]

            if function_name == "task_complete":
                return self._task_complete(args["reason"], args.get("result"))
            elif function_name == "task_blocked":
                return self._task_blocked(args["reason"])
            elif function_name == "do":
                await self._execute_intent(
                    args["intent"],
                    args["rationale"],
                    task_description,
                )
            elif function_name == "introspect":
                await self._introspect_intent(
                    args["intent"],
                    args["purpose"],
                    task_description,
                )

                # Check if we need to compress the trace
                if self.trace_manager:
                    await self.trace_manager.compress_if_needed()

        self._task_blocked(f"Max iterations ({max_iterations}) reached.")
        return "BLOCKED"


def show_trace(kernel: WinstonKernel) -> None:
    """Display the current action trace in a readable format.

    Shows all entries in the action trace with timestamps,
    reasoning, actions, and results.

    Parameters
    ----------
    kernel : WinstonKernel
        The kernel instance containing the action trace
    """
    # Use new pretty printer if available
    if kernel.trace_manager:
        trace = kernel.trace_manager.get_current_trace()
        if trace:
            print_action_trace(trace)
        else:
            # No current trace - try to show the last episode
            print("\nNo active trace. Showing last episode:\n")
            episodes_path = kernel.trace_manager.episodes_path
            if episodes_path.exists():
                # Get the most recent episode file
                episode_files = sorted(
                    episodes_path.glob("*.json"),
                    key=lambda f: f.stat().st_mtime,
                    reverse=True,
                )
                if episode_files:
                    with open(episode_files[0], "r") as f:
                        episode_data = json.load(f)
                    print_episode_summary(episode_data)
                    # Show the trace if requested
                    if episode_data.get("full_trace"):
                        print("\nAction Trace:")
                        print("=" * 60)
                        for i, entry in enumerate(episode_data["full_trace"], 1):
                            print(f"\n{i}. {entry['timestamp']}")
                            print(f"   Reasoning: {entry['reasoning']}")
                            print(f"   Action:    {entry['action']}")
                            result = entry["result"]
                            if len(result) > 200:
                                result = result[:200] + "..."
                            print(f"   Result:    {result}")
                        print("=" * 60)
                else:
                    print("No episodes found.")
            else:
                print("No episodes directory found.")
    else:
        print("Trace manager not initialized.")


def show_memory_status(kernel: WinstonKernel) -> None:
    """Display memory system status.

    Parameters
    ----------
    kernel : WinstonKernel
        The kernel instance
    """
    if not kernel.trace_manager:
        print("Memory system not initialized.")
        return

    # Count episodes in the episodes directory
    episodes_path = kernel.trace_manager.episodes_path
    episode_files = list(episodes_path.glob("*.json"))
    episode_count = len(episode_files)

    # Count total actions
    total_actions = 0
    compressed_count = 0
    for ep_file in episode_files:
        try:
            with open(ep_file, "r") as f:
                ep_data = json.load(f)
                total_actions += len(ep_data.get("full_trace", []))
                if ep_data.get("summary_checkpoint"):
                    compressed_count += 1
        except:
            pass

    # Add current trace if active
    if kernel.trace_manager.has_active_episode():
        total_actions += len(kernel.trace_manager.get_current_trace())

    print_memory_status(episode_count, total_actions, compressed_count)


def handle_command(command: str, kernel: WinstonKernel) -> bool:
    """Handle CLI commands that start with '/'.

    Parameters
    ----------
    command : str
        The command string starting with '/'
    kernel : WinstonKernel
        The kernel instance for accessing state

    Returns
    -------
    bool
        True if command was handled, False otherwise
    """
    command = command.lower().strip()

    if command == "/showtrace":
        show_trace(kernel)
        return True
    elif command == "/memorystatus":
        show_memory_status(kernel)
        return True
    elif command in ["/help", "/?"]:
        print("\nAvailable commands:")
        print("  /showTrace     - Display the current action trace")
        print("  /memoryStatus  - Show episodic memory statistics")
        print("  /help, /?      - Show this help message")
        print("  quit, exit     - Exit Winston\n")
        print("How to use Winston:")
        print("  Winston has episodic memory to learn from experiences.")
        print("  Give Winston memory-related tasks, and it will:")
        print("    1. Reason about the task using past experiences")
        print("    2. Express intents and discover relevant tools")
        print("    3. Execute memory operations")
        print("    4. Automatically save experiences for future learning")
        print("    5. Compress long traces to manage context\n")
        return True
    else:
        print(f"Unknown command: {command}")
        print("Type '/help' for available commands.")
        return True


def _setup_environment() -> Config:
    """Set up the environment including logging configuration.

    This must be called before any other Winston operations that use logging.

    Returns
    -------
    Config
        The initialized configuration object
    """
    # Create configuration instance for this chapter
    config = Config("chapter04")
    config.validate()

    # Configure logging using centralized config
    log_file = config.get_chapter_path("logs", create=True) / "winston.log"
    setup_logging(log_file=str(log_file))

    return config


async def main(task: str | None = None) -> None:
    """Run the Chapter 4 kernel with optional task argument.

    Parameters
    ----------
    task : str, optional
        Task to execute immediately. If None, runs in interactive mode.
    """
    print("Winston Chapter 4: From Action Traces to Episodic Memory")
    print("=========================================================")

    # Setup environment first (logging, etc.)
    config = _setup_environment()

    # Log startup banner for easy identification in logs
    logger.info("🚀 WINSTON STARTUP 🚀")
    logger.info("=" * 60)
    logger.info("Winston Chapter 4: From Action Traces to Episodic Memory")
    logger.info(f"Startup Time: {datetime.now().isoformat()}")
    logger.info("Status: Initializing cognitive architecture...")
    logger.info("=" * 60)

    print("\nInitializing Winston kernel...")

    # Create the kernel instance with configuration
    kernel = WinstonKernel(config)

    # Use kernel as a context manager for automatic initialization and cleanup
    async with kernel:
        try:
            if task:
                # CLI mode: execute single task
                print(f"Executing task: {task}\n")
                await kernel.run_cognitive_loop(task)
                action_count = (
                    len(kernel.trace_manager.get_current_trace())
                    if kernel.trace_manager
                    else 0
                )
                print(f"Actions: {action_count}")
            else:
                # Interactive mode: prompt for tasks
                print("\nInteractive Mode:")
                print("Winston now has episodic memory - it learns from experiences.")
                print(
                    "Try tasks that build on previous actions to see memory in action.\n"
                )
                print("Example tasks you can try:")
                print(
                    "  - Check Hacker News for interesting AI stories and create my daily AI brief"
                )
                print(
                    "  - Draft a one-paragraph brief on LLM inference on NPUs with three citations"
                )
                print("  - What memory tools do you have?")
                print("  - Add trending topics to the brief (continues the episode)")
                print(
                    "  - What's the weather in Seattle? (notice how this triggers a new episode)"
                )
                print(
                    "  - Add a risks section and label this v2 (for research tasks)\n"
                )
                print("Type '/help' for available commands.")
                print("Enter a task or 'quit' to exit.\n")
                while True:
                    user_task = input("Task: ").strip()
                    if user_task.lower() in ["quit", "exit", ""]:
                        # Finalize any active episode before exiting
                        if (
                            kernel.trace_manager
                            and kernel.trace_manager.has_active_episode()
                        ):
                            episode = kernel.trace_manager.finalize_episode(
                                outcome="session_end", result="REPL session ended"
                            )
                            logger.info(f"Finalized episode {episode.id} on REPL exit")
                        break

                    # Handle CLI commands
                    if user_task.startswith("/"):
                        handle_command(user_task, kernel)
                        continue

                    await kernel.run_cognitive_loop(user_task)
                    action_count = (
                        len(kernel.trace_manager.get_current_trace())
                        if kernel.trace_manager
                        else 0
                    )
                    print(f"Actions: {action_count}\n")
        except (KeyboardInterrupt, EOFError):
            print("\nShutting down...")
        except Exception as e:
            logger.error(f"Kernel execution failed: {e}")
            raise click.ClickException(f"Kernel execution failed: {e}")


@click.command()
@click.argument("task", required=False)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def cli(task: str | None, verbose: bool) -> None:
    """Winston Chapter 4: From Action Traces to Episodic Memory.

    Execute a cognitive task or run in interactive mode.

    TASK is the task description to execute. If omitted, runs interactively.

    Examples:
        python -m chapter04.kernel "What tools are available for memory operations?"
        python -m chapter04.kernel --verbose "Create a memory of today's events"
        python -m chapter04.kernel  # Interactive mode
    """
    if verbose:
        logger.add(sys.stderr, level="TRACE")

    try:
        asyncio.run(main(task))
    except KeyboardInterrupt:
        click.echo("\nShutting down...")
    except Exception as e:
        logger.error(f"CLI execution failed: {e}")
        if not task:  # In REPL mode, show the error
            raise click.ClickException(f"CLI execution failed: {e}")


if __name__ == "__main__":
    cli()
