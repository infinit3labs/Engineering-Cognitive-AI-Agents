#!/usr/bin/env python3
"""
Winston Minimal Cognitive Kernel - Proof that <200 lines can do cognitive agency
Chapter 2: What's the absolute minimum needed for cognition?

The entire cognitive loop: reason -> match intent -> execute -> repeat.
No orchestration bloat. No complex schemas. Pure cognitive simplicity.

Usage as a library:
    from chapter02.minimal_kernel import WinstonKernel
    from common.config import Config
    
    # Create configuration for your use case
    config = Config("my_chapter")
    
    # Initialize the kernel
    kernel = WinstonKernel(config)
    kernel.setup_demo_tools()  # Optional: add demo tools
    
    # Run a task
    result = kernel.run_cognitive_loop("Send an email to alice@example.com")
    print(f"Result: {result}")
    print(f"Actions taken: {len(kernel.action_trace)}")

Usage as CLI:
    python -m chapter02.minimal_kernel "Send an email about the meeting"
    python -m chapter02.minimal_kernel  # Interactive mode
"""

import json
import sys
from datetime import datetime
from typing import Any, cast

import click
from openai import OpenAI
from loguru import logger
from jinja2 import Environment, FileSystemLoader
from common.config import Config, setup_logging
from .tool_registry import execute_tool_function
from .mock_tools import TOOL_SCHEMAS

# Minimal core functions - the only tools Winston needs built-in
REASONING_TOOLS = [
    {
        "type": "function",
        "name": "task_complete",
        "description": "Mark the current task as completed with a reason.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why the task is complete"}
            },
            "required": ["reason"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "task_blocked",
        "description": "Mark the current task as blocked with a reason.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Why the task is blocked"}
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
]

FALLBACK_ACTION_TOOLS = [
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
    """Encapsulates Winston's minimal cognitive kernel.
    
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
        self.client = OpenAI(api_key=config["OPENAI_API_KEY"])
        self.model = config["OPENAI_MODEL"]
        self.action_trace: list[dict[str, str]] = []
        self.template_env = Environment(loader=FileSystemLoader("./prompts"))
        
        # Initialize intent database
        from common import initialize_intent_database
        from common.intent_database import index_tool, query_tools_by_intent
        
        persist_dir = str(config.get_chapter_path("chroma_db", create=True))
        collection_name = config["INTENT_COLLECTION_NAME"]
        self.collection = initialize_intent_database(persist_dir, collection_name)
        
        # Import functions we need
        self.index_tool = index_tool
        self.query_tools_by_intent = query_tools_by_intent
        
    def setup_demo_tools(self) -> None:
        """Initialize demo tools in the intent database."""
        # Index demo tools for intent-based discovery
        intent = "communicate with colleagues"
        for tool_name, tool_schema in TOOL_SCHEMAS.items():
            self.index_tool(self.collection, tool_schema, intent, "communication")
        logger.trace("Demo tools ready")
    
    def add_to_trace(self, intent: str, action: str, result: str) -> None:
        """Add an action to the trace for context maintenance."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "intent": intent,
            "action": action,
            "result": result,
        }
        self.action_trace.append(entry)
        logger.trace(f"Trace: {action} -> {result}")
    
    def task_complete(self, reason: str) -> str:
        """Mark task as completed."""
        self.add_to_trace("Task analysis", "task_complete", reason)
        print(f"[COMPLETE] Task Complete: {reason}")
        return "COMPLETE"
    
    def task_blocked(self, reason: str) -> str:
        """Mark task as blocked."""
        self.add_to_trace("Task analysis", "task_blocked", reason)
        print(f"[BLOCKED] Task Blocked: {reason}")
        return "BLOCKED"
    
    def reason_about_task(self, task_description: str) -> dict[str, Any] | None:
        """The reasoning phase - let the model think about the task."""
        try:
            template = self.template_env.get_template("chapter02/reasoning.md")
            prompt = template.render(
                task_description=task_description,
                action_trace=self.action_trace,
                timestamp=datetime.now().isoformat(),
            )

            response = self.client.responses.create(
                model=self.model,
                input=prompt,
                tools=cast(Any, REASONING_TOOLS),
                tool_choice="auto",
            )

            if response.status == "completed":
                for item in response.output:
                    if item.type == "function_call":
                        return {
                            "function": item.name,
                            "arguments": json.loads(item.arguments),
                        }
            return None
        except Exception as e:
            logger.error(f"Reasoning failed: {e}")
            return None
    
    def execute_intent(self, intent: str, rationale: str, task_description: str) -> None:
        """Match intent to tools and execute - the action phase with LLM tool selection."""
        logger.info(f"Processing intent: '{intent}' with rationale: '{rationale}'")

        # Query ChromaDB for tools matching the intent
        matching_tools = self.query_tools_by_intent(self.collection, intent)

        if not matching_tools:
            self.add_to_trace(rationale, intent, "No suitable tools found for intent")
            logger.trace(f"No tools found for intent '{intent}' - continuing reasoning")
            return

        logger.trace(f"Found {len(matching_tools)} tools for intent '{intent}'")

        # Build action prompt with available tools
        try:
            action_template = self.template_env.get_template("chapter02/action.md")
            action_prompt = action_template.render(
                task_description=task_description,
                current_intent=intent,
                intent_rationale=rationale,
                available_tools=matching_tools,
                action_trace=self.action_trace,
                timestamp=datetime.now().isoformat(),
            )

            # Create tool schemas for OpenAI function calling
            action_tools = []
            for tool in matching_tools:
                # Remove our custom 'intent' field
                tool_copy = tool.copy()
                tool_copy.pop("intent", None)
                tool_copy.pop("similarity", None)
                action_tools.append(tool_copy)

            # Add fallback tool options
            action_tools.extend(FALLBACK_ACTION_TOOLS)

            # Let LLM choose the appropriate tool
            response = self.client.responses.create(
                model=self.model,
                input=action_prompt,
                tools=cast(Any, action_tools),
                tool_choice="required",
            )

            if response.status == "completed":
                for item in response.output:
                    if item.type == "function_call":
                        function_name = item.name
                        arguments = json.loads(item.arguments)
                        
                        # Execute the chosen tool
                        if function_name == "insufficient_information":
                            missing = arguments.get("missing_parameters", "unknown")
                            self.add_to_trace(
                                intent, "insufficient_information", f"Missing: {missing}"
                            )
                            logger.trace(f"Insufficient information: {missing}")
                            print(f"[INFO] Missing Information: {missing}")
                        else:
                            # Execute the actual tool function
                            result = execute_tool_function(function_name, arguments)
                            self.add_to_trace(intent, function_name, result)
                            logger.trace(f"Executed {function_name}: {result}")
                            print(f"[ACTION] {function_name}")
                            print(f"  Result: {result}")

        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            self.add_to_trace(intent, "error", str(e))
    
    def run_cognitive_loop(self, task_description: str, max_iterations: int = 10) -> str:
        """The pure cognitive loop - reason, act, repeat."""
        logger.info(f"Starting: {task_description}")

        # Clear trace for new task
        self.action_trace = []

        # The cognitive loop
        for iteration in range(max_iterations):
            logger.trace(f"Iteration {iteration + 1}")

            # Stage 1: Reason about the task
            decision = self.reason_about_task(task_description)

            if not decision:
                continue

            function_name = decision["function"]
            arguments = decision["arguments"]

            # Stage 2: Handle reasoning decisions
            if function_name == "task_complete":
                return self.task_complete(arguments["reason"])
            elif function_name == "task_blocked":
                return self.task_blocked(arguments["reason"])
            elif function_name == "do":
                # Stage 3: Execute the intent
                self.execute_intent(
                    arguments["intent"], arguments["rationale"], task_description
                )

        # Iterations exhausted
        logger.warning(f"Exhausted {max_iterations} iterations without completion")
        return "EXHAUSTED"


# The standalone execute_intent function has been removed
# Use WinstonKernel.execute_intent instead

def _removed_execute_intent(
    intent: str, rationale: str, task_description: str, collection
) -> None:
    """Match intent to tools and execute - the action phase with LLM tool selection."""
    logger.info(f"Processing intent: '{intent}' with rationale: '{rationale}'")

    # Query ChromaDB for tools matching the intent
    matching_tools = query_tools_by_intent(collection, intent)

    if not matching_tools:
        add_to_trace(rationale, intent, "No suitable tools found for intent")
        logger.trace(f"No tools found for intent '{intent}' - continuing reasoning")
        return

    logger.trace(f"Found {len(matching_tools)} tools for intent '{intent}'")

    # Build action prompt with available tools
    try:
        action_template = template_env.get_template("chapter02/action.md")
        action_prompt = action_template.render(
            task_description=task_description,
            current_intent=intent,
            intent_rationale=rationale,
            available_tools=matching_tools,
            action_trace=action_trace,
            timestamp=datetime.now().isoformat(),
        )

        # Create tool schemas for OpenAI function calling
        action_tools = []
        for tool in matching_tools:
            action_tools.append({
                "type": "function",
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
                "strict": tool.get("strict", True),
            })

        # Add fallback functions
        action_tools.extend(FALLBACK_ACTION_TOOLS)

        # Call OpenAI with action prompt and matched tools
        response = client.responses.create(
            model=MODEL,
            input=action_prompt,
            tools=cast(Any, action_tools),
            tool_choice="required",  # Force tool selection
        )

        if response.status != "completed":
            logger.warning(f"Action response status: {response.status}")
            add_to_trace(rationale, intent, "action phase failed")
            return

        # Process tool calls
        for output_item in response.output:
            if output_item.type == "function_call":
                function_name = output_item.name
                arguments = json.loads(output_item.arguments)

                logger.trace(f"Action phase selected tool: {function_name}")

                if function_name == "insufficient_information":
                    result = (
                        f"Insufficient information: {arguments['missing_parameters']}"
                    )
                    add_to_trace(rationale, intent, result)
                    return

                if function_name == "no_suitable_tool":
                    result = f"No suitable tool: {arguments['reason']}"
                    add_to_trace(rationale, intent, result)
                    return

                # Execute the selected tool
                tool_result = execute_tool_function(function_name, arguments)
                add_to_trace(rationale, f"{intent} -> {function_name}", tool_result)
                logger.success(f"Tool executed: {function_name} -> {tool_result}")
                return

        # No function call received
        add_to_trace(rationale, intent, "no tool selection made")

    except Exception as e:
        error_msg = f"Action phase error: {e}"
        logger.error(error_msg)
        add_to_trace(rationale, intent, error_msg)



# The standalone run_cognitive_loop function has been removed
# Use WinstonKernel.run_cognitive_loop instead

def _removed_run_cognitive_loop(
    task_description: str, collection, max_iterations: int = 10
) -> str:
    """The pure cognitive loop - reason, act, repeat."""
    logger.info(f"Starting: {task_description}")

    # Clear trace for new task
    global action_trace
    action_trace = []

    # The cognitive loop
    for iteration in range(max_iterations):
        logger.trace(f"Iteration {iteration + 1}")

        # Stage 1: Reason about the task
        decision = reason_about_task(task_description)

        if not decision:
            continue

        function_name = decision["function"]
        args = decision["arguments"]

        # Stage 2: Execute the decision
        if function_name == "task_complete":
            return task_complete(args["reason"])
        elif function_name == "task_blocked":
            return task_blocked(args["reason"])
        elif function_name == "do":
            execute_intent(
                args["intent"], args["rationale"], task_description, collection
            )
            # Continue loop with action results in trace

    return task_blocked(f"Max iterations ({max_iterations}) reached")


def show_trace(kernel: WinstonKernel) -> None:
    """Display the current action trace in a readable format.

    Shows all entries in the action trace with timestamps,
    reasoning, actions, and results.
    
    Parameters
    ----------
    kernel : WinstonKernel
        The kernel instance containing the action trace
    """
    if not kernel.action_trace:
        print("Action trace is empty.")
        return

    print(f"\nAction Trace ({len(kernel.action_trace)} entries):")
    print("=" * 60)

    for i, entry in enumerate(kernel.action_trace, 1):
        print(f"\n{i}. {entry['timestamp']}")
        print(f"   Intent: {entry['intent']}")
        print(f"   Action:    {entry['action']}")
        print(f"   Result:    {entry['result']}")

    print("=" * 60)


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
    elif command in ["/help", "/?"]:
        print("\nAvailable commands:")
        print("  /showTrace  - Display the current action trace")
        print("  /help, /?   - Show this help message")
        print("  quit, exit  - Exit Winston\n")
        print("How to use Winston:")
        print("  Winston uses a simple intent database with demo tools.")
        print("  Give Winston any communication task, and it will:")
        print("    1. Reason about the task")
        print("    2. Match intents to available tools")
        print("    3. Execute the selected tool")
        print("    4. Determine if the task is complete or blocked\n")
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
    config = Config("chapter02")
    config.validate()

    # Configure logging using centralized config
    log_file = config.get_chapter_path("logs", create=True) / "winston.log"
    setup_logging(log_file=str(log_file))
    
    return config


def main(task: str | None = None) -> None:
    """Run the minimal kernel with optional task argument.

    Parameters
    ----------
    task : str, optional
        Task to execute immediately. If None, runs in interactive mode.
    """
    print("Winston Minimal Cognitive Kernel")
    print("================================")

    # Setup environment first (logging, etc.)
    config = _setup_environment()

    # Log startup banner for easy identification in logs
    logger.info("🚀 WINSTON STARTUP 🚀")
    logger.info("=" * 60)
    logger.info("Winston Minimal Cognitive Kernel - <200 lines of cognition")
    logger.info(f"Startup Time: {datetime.now().isoformat()}")
    logger.info("Status: Initializing cognitive architecture...")
    logger.info("=" * 60)

    print("\nInitializing Winston kernel...")

    # Create the kernel instance with configuration
    kernel = WinstonKernel(config)
    kernel.setup_demo_tools()

    print("\nWinston demonstrates cognitive agency in <200 lines of code.")

    try:
        if task:
            # CLI mode: execute single task
            print(f"Executing task: {task}\n")
            result = kernel.run_cognitive_loop(task)
            print(f"\nResult: {result}")
            print(f"Actions: {len(kernel.action_trace)}")
        else:
            # Interactive mode: prompt for tasks
            print("\nInteractive Mode:")
            print("Winston has demo communication tools (email, SMS, Slack).")
            print("It uses a simple intent database for tool discovery.\n")
            print("Example tasks you can try:")
            print("  - Send an email to alice@example.com about the meeting")
            print("  - Text Bob to confirm lunch plans")
            print("  - Post a message in #general about the team update")
            print("  - Notify the team about tomorrow's deadline\n")
            print("Type '/help' for available commands.")
            print("Enter a task or 'quit' to exit.\n")
            
            while True:
                user_task = input("Task: ").strip()
                if user_task.lower() in ["quit", "exit", ""]:
                    break
                    
                # Handle CLI commands
                if user_task.startswith("/"):
                    handle_command(user_task, kernel)
                    continue
                    
                result = kernel.run_cognitive_loop(user_task)
                print(f"\nResult: {result}")
                print(f"Actions: {len(kernel.action_trace)}\n")
    except (KeyboardInterrupt, EOFError):
        print("\nShutting down...")
    except Exception as e:
        logger.error(f"Kernel execution failed: {e}")
        raise click.ClickException(f"Kernel execution failed: {e}")


@click.command()
@click.argument("task", required=False)
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose logging")
def cli(task: str | None, verbose: bool) -> None:
    """Winston Minimal Cognitive Kernel - <200 lines of cognition.

    Execute a cognitive task or run in interactive mode.

    TASK is the task description to execute. If omitted, runs interactively.

    Examples:
        python -m chapter02.minimal_kernel "Send email to Alice"
        python -m chapter02.minimal_kernel --verbose "Text Bob about lunch"
        python -m chapter02.minimal_kernel  # Interactive mode
    """
    if verbose:
        logger.add(sys.stderr, level="DEBUG")

    try:
        main(task)
    except KeyboardInterrupt:
        click.echo("\nShutting down...")
    except Exception as e:
        logger.error(f"CLI execution failed: {e}")
        raise click.ClickException(f"CLI execution failed: {e}")


if __name__ == "__main__":
    cli()
