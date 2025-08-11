# Experiential Memory MCP Server

This MCP server provides episodic memory capabilities for Winston, implementing the memory system described in Chapter 4 of "Engineering Cognitive AI Agents".

## Features

- **Episode Management**: Create and finalize episodes with context boundaries
- **Semantic Search**: Search past experiences using ChromaDB
- **Progressive Compression**: Automatic summarization of long action traces
- **Lesson Extraction**: Identify surprises and learnings from experiences

## Tools

### `recall_episodes`
Search for past experiences relevant to the current task.

**Parameters:**
- `query` (string): Natural language query to search for
- `limit` (int, optional): Maximum number of episodes to return (default: 5)

**Returns:**
List of relevant episodes with summaries and lessons.

### `new_episode`
Start a new episode when context shifts.

**Parameters:**
- `reason` (string): Explanation of why a new episode is starting

**Returns:**
Confirmation message with new episode ID.

## Configuration

The server expects the following environment variables:
- `EPISODES_PATH`: Directory to store episode JSON files
- `CHROMA_PATH`: Directory for ChromaDB persistence (optional)

## Architecture

Episodes are stored with triple representation:
1. **Metadata**: Quick identification and filtering
2. **Full Trace**: Complete action history
3. **Summary**: Compressed narrative with lessons

This design enables both detailed recall and efficient search.