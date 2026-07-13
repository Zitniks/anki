# CLAUDE.md

Project-specific instructions for Claude Code.

## What this is

Future home of `adaptive-learning-repetitor` (planned migration target). Currently a mirrored copy of its `src/`,
`proto/`, `alembic/`, and packaging files, synced manually — not yet the canonical deployment. `.env`/`.env.local`
here are independent of repetitor's and were not overwritten by the sync.

## codebase-memory-mcp

This repo is indexed in the [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp) knowledge graph
(project name `Users-rinatkurmakaev-learn-project-llm_service`, 1058 nodes / 4396 edges as of last index). It's an
MCP server exposing structural code-graph tools (`search_graph`, `trace_path`, `get_architecture`, `query_graph`
with Cypher, etc.) — precise call-graph/dependency queries in ~500 tokens instead of a multi-file grep.

Prefer it over grep for: "who calls X", "what does X call", dead code / high fan-out detection, and architecture
questions. See `~/.claude/skills/codebase-memory/SKILL.md` for the full tool reference and query cheatsheet.

Re-index after large refactors (e.g. re-syncing from repetitor): `codebase-memory-mcp cli index_repository --repo-path . --mode fast`.
