# ChromaDB REPL Tool

An interactive REPL-like CLI tool for querying and inspecting ChromaDB databases used in the Winston cognitive AI agents project.

## Features

- Interactive command-line interface for ChromaDB inspection
- Support for semantic queries with distance thresholds
- Database information and statistics display
- Collection management and browsing
- Chapter context resolution (e.g., `chapter03` → database path)
- Rich-formatted output with tables and syntax highlighting
- Export functionality for query results
- **NEW: Episode mode for exploring Chapter 4's experiential memory**

## Installation

This tool is part of the Winston workspace and is installed automatically when you run:

```bash
uv sync
```

## Usage

### Basic Usage

```bash
# Launch REPL with default settings
chroma-repl

# Connect to specific database
chroma-repl --db-path ./path/to/chroma.db

# Use chapter context resolution
chroma-repl --chapter-context chapter03

# Explore Chapter 4's episodic memory
chroma-repl --chapter-context chapter04 --mode episodes

# Specify collection name
chroma-repl --collection-name intent_index

# Enable verbose logging
chroma-repl --verbose
```

### Interactive Commands

Once in the REPL, you can use these commands:

#### Intent Mode (default)
- `query <text> [n]` - Semantic search for intents
- `show <doc_id>` - Display full document details
- `count [type]` - Document count (optionally by type)
- `export <path> [type]` - Export data to JSON
- `info` - Database and collection information
- `collections` - List all collections
- `help` - Show command help
- `exit` - Exit the REPL

#### Episode Mode
- `list [--has-surprises]` - List all episodes
- `show <episode_id> [-t]` - Show episode details (use -t for full trace)
- `query <text> [n]` - Search episodes by semantic similarity
- `info` - Database and collection information
- `collections` - List all collections
- `help` - Show command help
- `exit` - Exit the REPL

### Examples

#### Intent Mode
```bash
# Query for intent-related documents
> query "create file" 5

# Show specific tool details
> show general-read_file

# Count tools in the database
> count tool

# Export all intents
> export ./intents.json intent
```

#### Episode Mode
```bash
# List episodes with lessons learned
> list --has-surprises

# Show episode with full action trace
> show 12345-abcd-6789 -t

# Search for testing-related episodes
> query "testing setup" 5
```

## Integration with Winston

This tool is specifically designed to work with Winston's database systems:

- Automatically resolves chapter-specific database paths
- Uses Winston's common configuration and utilities
- Supports both intent index (Chapter 3) and episodic memory (Chapter 4)
- Compatible with Winston's ChromaDB schema and metadata
- Enables exploration of Winston's learning and memory systems

## Architecture

The tool follows Winston's principles:

- **Minimal Interface**: Simple, focused REPL for database inspection
- **Protocol Integration**: Uses Winston's common ChromaDB utilities
- **Extensible Design**: Easy to add new commands and features
- **Error Resilience**: Comprehensive error handling and logging

## Development

For development and testing:

```bash
# Run with package specification
uv run --package chroma-repl chroma-repl --help

# Type checking
uv run mypy chroma-repl/src/

# Code formatting
uv run ruff format chroma-repl/src/
```

## License

Part of the Winston cognitive AI agents project.
