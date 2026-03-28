# a2db — Agent-to-Database

CLI and MCP server for AI agents to query databases. Two frontends (CLI + MCP), one core.

## Architecture

- `src/a2db/connections.py` — ConnectionStore: save/load/list connection TOML files
- `src/a2db/drivers.py` — DriverRegistry: DSN scheme → DBAPI 2.0 driver resolution
- `src/a2db/sql.py` — SQLGlot wrapping: pagination, read-only validation
- `src/a2db/executor.py` — QueryExecutor: named batch queries with pagination
- `src/a2db/schema.py` — SchemaExplorer: progressive schema discovery
- `src/a2db/formatter.py` — Output formatting: TSV and JSON renderers
- `src/a2db/cli.py` — Click CLI frontend (thin wrapper)
- `src/a2db/mcp_server.py` — MCP server frontend (thin wrapper)

## Dev Commands

- Full gate: `make check` (lint + test + security)
- Run tests: `make test` (includes coverage, fails under 90%)
- Lint: `make lint` or `agent-harness lint` (check only, never modifies files — safe to run anytime)
- Fix: `make fix` or `agent-harness fix` (auto-fix, then runs lint to verify)
- Coverage diff: `make coverage-diff` (changed lines must be 95%+ covered)
- Security: `agent-harness security-audit` (deps + secrets)
- Config check: `agent-harness init` (checks project hygiene)
- Build: `make build`
- Bootstrap: `make bootstrap` (installs deps, requires `agent-harness` CLI)

Pre-commit hooks run `fix` then `lint` automatically on every commit. Never truncate lint or test output — read the full error.

## Never

- Never commit `.env` files or database credentials
- Never execute destructive SQL (DROP, TRUNCATE, DELETE without WHERE) without explicit user confirmation

## Ask First

- Before changing CLI argument names or command structure (breaking change for users)
- Before adding new dependencies
- Before changing MCP tool signatures (breaking change for MCP clients)
