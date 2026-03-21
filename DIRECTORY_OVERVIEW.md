# Repository Directory Overview

High-level map of the workspace and what you can learn by exploring each area.

## Workspace Root
- `pyproject.toml`: Defines the uv workspace and ties all packages (chapters, common utilities, MCP server, REPL) together so dependencies are shared during development.

## common/
- Shared Python package with Winston's core building blocks: configuration/loading helpers (`config.py`), ChromaDB client and intent index utilities (`chroma_client.py`, `intent_database.py`, `intent_generator.py`), MCP host utilities (`mcp_host.py`), tool identity helpers (`tool_identity.py`), CLI helpers, and action trace/episodic memory data structures (`action_trace.py`).
- Work here to learn how configuration, logging, vector search, and MCP integration are abstracted so chapter kernels stay minimal.

## chapter02/
- Implements the foundational cognitive kernels (`basic_kernel.py`, `minimal_kernel.py`) plus mock tools and a tool registry for semantic discovery.
- Explore to understand the minimal reasoning→intent→action loop, action traces as state, and how prompt templates in `prompts/chapter02/` drive the two-phase prompting approach.

## chapter03/
- Evolves the kernel with a hierarchical intent index and MCP-powered tool discovery (`kernel.py`), leaning on shared intent database utilities.
- Work here to see how L1/L2 intents are generated, indexed in ChromaDB, and resolved at runtime, and how MCP connections expand capabilities without changing the core loop.

## chapter04/
- Extends the agent with episodic memory (`kernel.py`) and meta-cognitive reasoning, persisting and compressing action traces into episodes.
- Dive in to learn how episodes are created, summarized, and searched via ChromaDB, and how memory-aware prompting in `prompts/chapter04/` shapes behavior.

## chroma-repl/
- CLI/REPL tool (`src/chroma_repl/main.py`, `README.md`) for inspecting ChromaDB stores used by the agents, including intent indexes and episodic memory.
- Useful for learning how to query, browse, and export intents or episodes from the vector stores while debugging or studying agent behavior.

## mcp_servers/experiential_memory/
- FastMCP server implementation (`server.py`) that exposes episodic memory tools like starting episodes and recalling past experiences; packaged with its own README.
- Explore to learn how MCP servers are built, configured, and wired to ChromaDB-backed memory for Chapter 4's experiential features.

## prompts/
- Prompt templates for each chapter (`chapter02/`, `chapter03/`, `chapter04/`) and shared prompts (`common/`) that drive reasoning, action selection, intent generation, and summarization.
- Study these to see how prompt design evolves across chapters and how Jinja templating is used to keep prompts structured and reusable.
