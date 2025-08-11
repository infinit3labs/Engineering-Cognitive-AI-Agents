# Chapter 4: From Action Traces to Episodic Memory

This chapter transforms Winston from an amnesiac agent into one with persistent, searchable episodic memory. The implementation demonstrates how to build intelligent memory systems that preserve complete experiences while keeping them usable through progressive compression and semantic search.

## Key Concepts

- **Episodic Memory**: Transforms ephemeral action traces into durable, searchable episodes
- **Unified State Management**: Single source of truth via disk-based coordination
- **Meta-cognitive Reasoning**: The `introspect()` function enables exploring capabilities without executing them
- **Progressive Compression**: Maintains full trace while creating efficient summaries for context windows
- **Semantic Search**: ChromaDB enables finding relevant memories by meaning, not keywords

## Prerequisites

1. Install `uv` package manager
2. Copy `.env.example` to `.env` and configure:
   - `OPENAI_API_KEY` (required)
   - Optional: `LOG_LEVEL`, `LOG_FILE`, `OPENAI_MODEL`
3. Run `uv sync` from the project root to install dependencies

## Running the Chapter

The chapter provides two modes of operation:

### Interactive REPL Mode

Start Winston in interactive mode to have a conversation:

```bash
uv run --package chapter04 python -m chapter04.kernel
```

Example session:
```
Welcome to Winston (Chapter 4) - Experiential Memory Edition
Type 'exit' or 'quit' to end the session.

You: What is the capital of Poland?
Winston: Warsaw

You: Was it always Warsaw?
Winston: No, Kraków was the capital before Warsaw...

You: Check Hacker News for AI stories
Winston: [Starts new episode for context shift]
```

### CLI Mode (Single Task)

Execute a single task directly:

```bash
uv run --package chapter04 python -m chapter04.kernel "Draft a one-paragraph brief on LLM inference on NPUs with three citations"
```

## Architecture Overview

The chapter introduces a sophisticated memory architecture while maintaining kernel simplicity:

```
Cognitive Layer:
├── kernel.py           # Pure reasoning loop (unchanged)
└── prompts/           # Meta-cognitive reasoning templates

Memory Management:
├── ActionTraceManager  # Handles traces, compression, episodes
└── episodes/          # Disk-based episodic storage

Protocol Layer:
├── experiential_memory_server.py  # MCP server for memory
├── Intent Database    # Semantic tool discovery
└── MCP Servers       # Fetch, filesystem capabilities
```

## Memory System Features

### Episode Structure

Episodes contain three interconnected representations:

1. **Metadata**: Quick filtering and relevance scoring
2. **Full Trace**: Complete history of every action (never deleted)
3. **Summary Checkpoint**: Compressed narrative for efficient access

### Progressive Compression

As action traces grow, the system automatically:
- Creates checkpoint summaries at token thresholds
- Preserves recent actions in full detail
- Maintains narrative continuity across checkpoints
- Extracts lessons and surprises for learning

### Semantic Search

Episodes are indexed in ChromaDB by:
- Task descriptions and summaries
- Extracted lessons and insights
- Temporal metadata
- Outcome patterns

## Exploring Winston's Memory

Use the chroma-repl tool to examine the episodic memory:

```bash
# Launch REPL for Chapter 4's memory
uv run --package chroma-repl python -m chroma_repl.main -ch chapter04

> query "debugging API errors"
> show episode_2024_01_15_api_debug
> list episodes --has-surprises
```

## Test Scenario

The canonical test validates three critical capabilities:

1. **Anaphora Resolution**: "Was it always Warsaw?" - Winston understands "it" from context
2. **Episode Continuity**: Related questions stay in the same episode
3. **Boundary Detection**: Context shifts trigger new episodes

Run the test sequence:
```bash
# In REPL mode:
"What is the capital of Poland?"
"Was it always Warsaw?"
"Check Hacker News for AI stories"  # Triggers new episode
```

## Key Files

- `kernel.py`: The cognitive loop with episodic memory integration
- `experiential_memory_server.py`: FastMCP server for memory operations
- `prompts/reasoning.md.jinja`: Meta-cognitive reasoning template
- `mcp_config.json`: Configuration for MCP servers
- `episodes/`: Directory storing episode files

## Exercises

1. **Add Web Search**: Configure Brave Search MCP server to transform Winston from passive reader to active researcher
2. **Daily AI Brief**: Build a workflow that creates markdown reports from multiple sources, improving over time
3. **Analyze Patterns**: Create analytics to reveal Winston's cognitive evolution through accumulated episodes
4. **Memory-First Experiment**: Modify prompts to require memory consultation and observe behavioral changes

## Troubleshooting

### Episodes Not Being Created
- Check that `EPISODES_PATH` is correctly set in environment
- Verify write permissions to the episodes directory
- Ensure MCP server is running (check logs)

### Memory Recall Not Working
- Verify ChromaDB is properly initialized
- Check that episodes are being indexed after creation
- Ensure semantic queries match episode content

### Context Window Issues
- Progressive compression activates at thresholds
- Adjust `COMPRESSION_THRESHOLD` if needed
- Monitor token counts in episode metadata

## Next Steps

Chapter 5 builds on this episodic foundation to create semantic understanding that spans across episodes, transforming isolated experiences into connected knowledge. The `introspect()` function introduced here becomes the seed for higher forms of cognition.

## References

See the full chapter text in `docs/book/ch04/chapter.md` for detailed explanations and the complete journey from action traces to episodic memory.