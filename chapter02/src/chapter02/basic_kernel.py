#!/usr/bin/env python3
"""
Winston Basic Cognitive Kernel - The simplest possible cognitive agent
Chapter 2: What's the absolute minimum needed for cognition?

A demonstration that meaningful AI agency requires surprisingly little orchestration.
This basic implementation proves the three-function paradigm works without any external capabilities.
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

# Basic reasoning tools - the minimal set Winston needs
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


class WinstonKernel:
    """Encapsulates Winston's basic cognitive kernel.
    
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

    def add_to_trace(self, reasoning: str, action: str, result: str) -> None:
        """Add an entry to the action trace - Winston's only state."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "reasoning": reasoning,
            "action": action,
            "result": result,
        }
        self.action_trace.append(entry)
        logger.trace(f"Trace: {action} -> {result}")

    def task_complete(self, reason: str) -> str:
        """Mark task as completed."""
        self.add_to_trace("Task analysis", "task_complete", reason)
        return f"Task completed: {reason}"

    def task_blocked(self, reason: str) -> str:
        """Mark task as blocked."""
        self.add_to_trace("Task analysis", "task_blocked", reason)
        return f"Task blocked: {reason}"

    def do(self, intent: str, rationale: str) -> str:
        """Execute an action with given intent and rationale.

        Parameters
        ----------
        intent : str
            The intent or goal of the action.
        rationale : str
            Why this action should be taken.

        Returns
        -------
        str
            Action result message.

        Examples
        --------
        >>> result = kernel.do("analyze", "need to understand problem")
        >>> len(result) > 0
        True
        """
        self.add_to_trace(rationale, intent, "action logged")
        logger.info(f"Action: {intent} (Rationale: {rationale})")

        # In Chapter 2, Winston has no real capabilities
        # Actions are logged but don't execute external operations
        return f"Action '{intent}' logged with rationale: {rationale}"

    @logger.catch
    def build_prompt(self, task_description: str) -> str:
        """Construct complete prompt using Jinja2 template substitution.

        Parameters
        ----------
        task_description : str
            The user's task specification.

        Returns
        -------
        str
            Rendered prompt string ready for LLM processing.

        Examples
        --------
        >>> prompt = kernel.build_prompt("Test task")
        >>> len(prompt) > 0
        True
        """
        try:
            system_template = self.template_env.get_template("chapter02/system.md")

            prompt = system_template.render(
                task_description=task_description,
                action_trace=self.action_trace,
                timestamp=datetime.now().isoformat(),
            )

            logger.trace(f"Built prompt for task: {task_description[:50]}...")
            return prompt

        except Exception as e:
            logger.error(f"Failed to build prompt: {e}")
            raise

    @logger.catch
    def handle_function_call(self, function_call: Any) -> str | None:
        """Handle function calls from the LLM response.

        Parameters
        ----------
        function_call : Any
            OpenAI function call object.

        Returns
        -------
        str | None
            Function result or None if continuing cognitive loop.

        Examples
        --------
        >>> # Would be called with actual OpenAI function call object
        >>> # result = kernel.handle_function_call(mock_function_call)
        >>> # isinstance(result, str) or result is None
        True
        """
        try:
            function_name = function_call.name
            arguments = json.loads(function_call.arguments)

            logger.trace(f"Executing function: {function_name} with args: {arguments}")

            if function_name == "task_complete":
                return self.task_complete(arguments["reason"])
            elif function_name == "task_blocked":
                return self.task_blocked(arguments["reason"])
            elif function_name == "do":
                self.do(arguments["intent"], arguments["rationale"])
                return None  # Continue cognitive loop
            else:
                logger.error(f"Unknown function: {function_name}")
                return None

        except Exception as e:
            logger.error(f"Function call handling failed: {e}")
            return None

    @logger.catch
    def run_task(self, task_description: str, max_iterations: int = 10) -> str | None:
        """The entire cognitive loop - Winston's core reasoning process.

        Parameters
        ----------
        task_description : str
            Description of the task to accomplish.
        max_iterations : int, default=10
            Maximum cognitive loop iterations to prevent infinite loops.

        Returns
        -------
        str | None
            Final result of the task or None if task fails.

        Examples
        --------
        >>> result = kernel.run_task("Simple test task")
        >>> isinstance(result, str) or result is None
        True
        """
        logger.info(f"Starting task: {task_description}")

        # Clear action trace for new task
        self.action_trace = []

        iterations = 0

        while iterations < max_iterations:
            iterations += 1
            logger.trace(f"Cognitive loop iteration {iterations}")

            try:
                # Build prompt with current task and trace context
                prompt = self.build_prompt(task_description)

                # Get reasoning from LLM
                response = self.client.responses.create(
                    model=self.model,
                    input=prompt,
                    tools=cast(Any, REASONING_TOOLS),
                    tool_choice="auto",
                )

                # Check response status
                if response.status != "completed":
                    logger.warning(f"Response status: {response.status}")
                    continue

                # Handle function calls
                for output_item in response.output:
                    if output_item.type == "function_call":
                        result = self.handle_function_call(output_item)
                        if result:  # Task completed or blocked
                            logger.info(f"Task finished after {iterations} iterations")
                            return result

                # If no function call received, log and continue
                logger.trace("No function call received, continuing reasoning")

            except Exception as e:
                logger.error(f"Error in cognitive loop iteration {iterations}: {e}")
                continue

        # Max iterations reached
        logger.warning(f"Task incomplete after {max_iterations} iterations")
        return self.task_blocked(
            f"Maximum iterations ({max_iterations}) reached without completion"
        )


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
        print(f"   Reasoning: {entry['reasoning']}")
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
        print("  Winston is a minimal cognitive agent that reasons about tasks.")
        print("  Give Winston any task, and it will:")
        print("    1. Reason about the task")
        print("    2. Express intents for actions it would take")
        print("    3. Determine if the task is complete or blocked\n")
        print("  Note: In Chapter 2, Winston has no external capabilities -")
        print("  it can only reason and log its intended actions.\n")
        return True
    else:
        print(f"Unknown command: {command}")
        print("Type '/help' for available commands.")
        return True


def _setup_environment() -> Config:
    """Set up the environment for Winston.

    Configures logging and other environment settings.
    
    Returns
    -------
    Config
        The initialized configuration object
    """
    # Create configuration instance for this chapter
    config = Config("chapter02")
    config.validate()
    
    # Configure logging using centralized config
    log_file = config.get_chapter_path("logs", create=True) / "winston_basic.log"
    setup_logging(log_file=str(log_file))
    
    return config


def main(task: str | None = None) -> None:
    """Run the Chapter 2 kernel with optional task argument.

    Parameters
    ----------
    task : str, optional
        Task to execute immediately. If None, runs in interactive mode.
    """
    print("Winston Chapter 2: Minimal Cognitive Agent")
    print("==========================================")
    
    # Setup environment first (logging, etc.)
    config = _setup_environment()
    
    # Create the kernel instance with configuration
    kernel = WinstonKernel(config)

    # Log startup banner for easy identification in logs
    logger.info("🚀 WINSTON STARTUP 🚀")
    logger.info("=" * 60)
    logger.info("Winston Chapter 2: Minimal Cognitive Agent")
    logger.info(f"Startup Time: {datetime.now().isoformat()}")
    logger.info("Status: Initializing cognitive architecture...")
    logger.info("=" * 60)

    print("\nWinston is a minimal cognitive agent that reasons about tasks.")

    try:
        if task:
            # CLI mode: execute single task
            print(f"Executing task: {task}\n")
            result = kernel.run_task(task)
            print(f"\nResult: {result}")
            print(f"Actions: {len(kernel.action_trace)}")
        else:
            # Interactive mode: prompt for tasks
            print("\nInteractive Mode:")
            print("Winston has no external capabilities in Chapter 2.")
            print("It can only reason and log its intended actions.\n")
            print("Example tasks you can try:")
            print("  - Count to 5")
            print("  - Explain the concept of recursion")
            print("  - What's the weather like today?")
            print("  - Calculate the factorial of 6")
            print("  - Write a haiku about AI\n")
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
                    
                result = kernel.run_task(user_task)
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
    """Winston Chapter 2: Minimal Cognitive Agent.

    Execute a cognitive task or run in interactive mode.

    TASK is the task description to execute. If omitted, runs interactively.

    Examples:
        python -m chapter02.basic_kernel "Count to 5"
        python -m chapter02.basic_kernel --verbose "Explain recursion"
        python -m chapter02.basic_kernel  # Interactive mode
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
