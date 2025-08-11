# Chapter 3: Scaling Agency with an Intent Index

This chapter solves the "tool-calling wall" that limits agent capability as toolsets grow. The implementation introduces two key innovations: the Model Context Protocol (MCP) for decoupling tools from the agent, and a two-level intent index that enables scalable tool discovery through semantic search.

## Key Concepts

- **Tool-Calling Wall**: LLM accuracy collapses with >20 tools, approaching random chance at 100+
- **Model Context Protocol (MCP)**: Standardized communication layer between agent and external tool servers
- **Two-Level Intent Index**: Semantic organization of capabilities into L1 (concrete actions) and L2 (abstract categories)
- **Intent-Based Discovery**: Agent expresses abstract intents; system finds relevant tools through vector search
- **Protocol-Driven Architecture**: Tools as external services, not hardcoded functions

## Prerequisites

1. Install `uv` package manager
2. Copy `.env.example` to `.env` and configure:
   - `OPENAI_API_KEY` (required)
   - Optional: `LOG_LEVEL`, `LOG_FILE`, `OPENAI_MODEL`
3. Run `uv sync` from the project root to install dependencies

## Running the Chapter

The chapter provides two modes of operation:

### Interactive REPL Mode

Start Winston in interactive mode for conversation:

```bash
uv run --package chapter03 python -m chapter03.kernel
```

Example session:
```
Welcome to Winston (Chapter 3) - Intent Index Edition
Type 'exit' or 'quit' to end the session.

You: Store a memory that Project Alpha is due Friday
Winston: [Creates entity and stores observation]

You: When is Project Alpha due?
Winston: Project Alpha is due on Friday
```

### CLI Mode (Single Task)

Execute a single task directly:

```bash
uv run --package chapter03 python -m chapter03.kernel "Store a memory that 'Project Alpha is due Friday' and another that 'Project Alpha is managed by Sarah'"
```

## Architecture Overview

The chapter introduces a scalable discovery architecture:

```
Cognitive Layer:
├── kernel.py           # Async cognitive loop with intent resolution
└── prompts/           # Reasoning and action selection templates

Discovery Layer:
├── IntentDatabase     # ChromaDB vector store for semantic search
├── IntentGenerator    # Generates L1/L2 intents from tool schemas
└── Two-Level Index:
    ├── L1 Intents     # Concrete actions ("send a message")
    └── L2 Intents     # Abstract categories ("manage communications")

Protocol Layer:
├── MCPHost           # Manages connections to MCP servers
└── MCP Servers:
    └── memory        # Graph-based knowledge store
```

## The Intent Index

### How It Works

1. **Tool Discovery**: MCPHost connects to servers and discovers available tools
2. **Intent Generation**: LLM translates tool schemas into user-centric intents
3. **Semantic Clustering**: Related L1 intents grouped into L2 categories
4. **Vector Storage**: ChromaDB indexes intents for semantic search
5. **Runtime Resolution**: Agent's abstract intent → semantic search → relevant tools

### Index Structure

```python
# L1 Intent (Concrete Action)
{
    "id": "l1_send_message",
    "text": "send a short message",
    "type": "L1",
    "tools": ["tool::slack::send_message", "tool::teams::send_message"]
}

# L2 Intent (Abstract Category)
{
    "id": "l2_communications",
    "text": "manage real-time communications",
    "type": "L2",
    "l1_texts": ["send a message", "create a channel", "add user to team"]
}
```

## Exploring the Intent Index

Use the chroma-repl tool to inspect the vector database:

```bash
# Launch REPL for Chapter 3's intent index
uv run --package chroma-repl python -m chroma_repl.main -ch chapter03

> info
Database: chapter03_intents
Collections: intents (15 documents)

> query "manage knowledge graph"
1. [0.92] L2: "manage and update the knowledge graph"
2. [0.85] L1: "create new entities in the graph"
3. [0.83] L1: "find relevant nodes in the knowledge graph"

> show l1_create_entities
Details of L1 intent with associated tools...
```

## Memory Server Demo

The chapter uses Anthropic's memory server as a demonstration of MCP capabilities:

### Storing Information

```bash
# Store related facts
uv run --package chapter03 python -m chapter03.kernel "Store that Project Alpha is due Friday and managed by Sarah"
```

Winston will:
1. Express intent: "retain important project information"
2. Discover relevant tools through semantic search
3. Create entities and add observations
4. Handle errors gracefully (e.g., creating entities before adding observations)

### Retrieving Information

```bash
# Query stored facts
uv run --package chapter03 python -m chapter03.kernel "When is Project Alpha due and who manages it?"
```

Winston will:
1. Express intent: "gather key project information"
2. Find and execute search tools
3. Return: "Project Alpha is due on Friday and is managed by Sarah"

## Key Files

- `kernel.py`: Async cognitive loop with intent-based action selection
- `mcp_config.json`: Configuration for MCP servers
- `prompts/reasoning.md.jinja`: Guides abstract intent expression
- `prompts/action.md.jinja`: Static action space for tool selection
- Memory data stored in: `tmp/chapter03/memory.json`

## Configuration

The `mcp_config.json` defines available MCP servers:

```json
{
  "mcpServers": {
    "memory": {
      "command": "npx",
      "args": ["-y", "@anthropic/server-memory"],
      "env": {}
    }
  }
}
```

Add new servers to extend Winston's capabilities without modifying the kernel.

## Exercises

1. **Semantic Equivalence**: Add a similar server (e.g., Discord if you have Slack) and observe how tools merge into existing L1 intents

2. **Semantic Boundaries**: Query ambiguous intents that span categories to see how the system handles fuzzy boundaries

3. **Emergent Categories**: Add servers with new capability domains and watch L2 categories reorganize

## Troubleshooting

### Intent Index Not Building
- Check that `mcp_config.json` exists and is valid JSON
- Verify MCP servers can be launched (test with `npx -y @anthropic/server-memory`)
- Check logs for connection errors

### Memory Operations Failing
- Ensure entities are created before adding observations
- Check `tmp/chapter03/memory.json` for stored data
- Verify the memory server is running (check process list)

### Chroma REPL Issues
- Ensure ChromaDB is properly initialized
- Check that intent generation completed successfully
- Verify database path matches chapter configuration

## Key Insights

This chapter demonstrates that scaling agent capabilities doesn't require overwhelming the LLM with choices. By:
- Decoupling tools through MCP
- Organizing capabilities semantically
- Trusting the agent to express abstract intents

We enable Winston to scale to thousands of tools while maintaining reliable performance. The agent no longer picks from a giant menu; it states what it wants to do, and the system finds the right tools.

## Next Steps

Chapter 4 builds on this foundation by adding episodic memory, transforming Winston from a stateless executor into an agent that learns from experience. The action traces become persistent episodes, searchable and compressed for efficient recall.

## References

See the full chapter text in `docs/book/ch03/chapter.md` for detailed explanations and the complete journey from tool-calling wall to scalable intent-based discovery.