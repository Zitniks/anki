# CLAUDE.md

Project-specific instructions for Claude Code.

## codebase-memory-mcp

This repo is indexed in the [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) knowledge graph
(project name `Users-rinatkurmakaev-learn-project-ankis`, 508 nodes / 1222 edges as of last index). It's an MCP
server exposing structural code-graph tools (`search_graph`, `trace_path`, `get_architecture`, `query_graph` with
Cypher, etc.) — precise call-graph/dependency queries in ~500 tokens instead of a multi-file grep.

Prefer it over grep for: "who calls X", "what does X call", dead code / high fan-out detection, and architecture
questions. See `~/.claude/skills/codebase-memory/SKILL.md` for the full tool reference and query cheatsheet.

Re-index after large refactors: `codebase-memory-mcp cli index_repository --repo-path . --mode fast`.
