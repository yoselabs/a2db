<p align="center">
  <h1 align="center">🗄️ a2db</h1>
  <p align="center">
    <em>Agent-to-Database</em>
  </p>
  <p align="center">
    <strong>Give AI agents safe, read-only access to your databases. One call, multiple queries, clean results.</strong>
  </p>
  <p align="center">
    5 databases &middot; batch queries &middot; pre-configured connections &middot; SQLGlot read-only
  </p>
  <p align="center">
    <a href="https://pypi.org/project/a2db/"><img src="https://img.shields.io/pypi/v/a2db" alt="PyPI"></a>
    <a href="https://pypi.org/project/a2db/"><img src="https://img.shields.io/pypi/dm/a2db" alt="Downloads"></a>
    <a href="https://www.apache.org/licenses/LICENSE-2.0"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License: Apache 2.0"></a>
    <a href="https://python.org"><img src="https://img.shields.io/badge/python-3.12%2B-blue.svg" alt="Python 3.12+"></a>
  </p>
  <p align="center">
    <a href="#quick-start">Quick Start</a> &middot;
    <a href="#mcp-tools">MCP Tools</a> &middot;
    <a href="#security">Security</a> &middot;
    <a href="#comparison">Comparison</a> &middot;
    <a href="#setup-by-environment">Setup</a>
  </p>
</p>

---

```
Agent: "Show me active users and their recent orders"
  ↓
a2db execute → 2 queries, 1 call, structured results
  ↓
Agent: "Got it — 847 active users, avg order $42.50"
```

## Why a2db?

Most database MCP servers make you run one query at a time, repeat connection details on every call, and return results double-encoded inside JSON strings. a2db fixes all of that:

- **Pre-configured connections** — define databases in `.mcp.json` with `--register`, agent queries immediately
- **Batch queries** — run multiple named queries in a single tool call
- **Default connection** — set connection once, use it across all queries in a batch
- **Clean output** — structured JSON envelope with compact TSV data and per-query timing (see [why TSV?](#why-tsv))
- **Read-only enforced** — SQLGlot AST parsing blocks all write operations
- **All drivers bundled** — `pip install a2db` and you're done
- **Secrets stay in env** — `${DB_PASSWORD}` in DSNs, expanded only at connection time

## Supported Databases

| Database | Driver | Async |
|----------|--------|-------|
| PostgreSQL | asyncpg | native |
| SQLite | aiosqlite | native |
| MySQL / MariaDB | mysql-connector-python | wrapped |
| Oracle | oracledb | wrapped |
| SQL Server | pymssql | wrapped |

## Quick Start

```bash
pip install a2db
```

### As an MCP Server (recommended)

**Claude Code** (with pre-configured connection):
```bash
claude mcp add -s user a2db -- a2db-mcp \
  --register myapp/prod/main 'postgresql://user:${DB_PASSWORD}@host/mydb'
```

**Claude Code** (minimal — agent calls `login` on demand):
```bash
claude mcp add -s user a2db -- a2db-mcp
```

**Claude Desktop / Cursor / any MCP client** (`.mcp.json`):
```json
{
  "mcpServers": {
    "a2db": {
      "command": "uvx",
      "args": [
        "a2db-mcp",
        "--register", "myapp/prod/main", "postgresql://user:${DB_PASSWORD}@host/mydb"
      ],
      "env": {
        "DB_PASSWORD": "your-password-here"
      }
    }
  }
}
```

**Multiple databases:**
```json
{
  "args": [
    "a2db-mcp",
    "--register", "myapp/prod/main", "postgresql://user:${DB_PASSWORD}@host/maindb",
    "--register", "myapp/prod/analytics", "postgresql://user:${DB_PASSWORD}@host/analytics"
  ]
}
```

`--register` pre-registers connections at server startup — the agent can query immediately. Passwords use `${ENV_VAR}` syntax and are expanded at connection time, never stored in plaintext.

### As a CLI

```bash
# Save a connection (validates immediately)
a2db login -p myapp -e prod -d main 'postgresql://user:${DB_PASSWORD}@localhost/mydb'

# Query
a2db query -p myapp -e prod -d main "SELECT * FROM users LIMIT 10"

# JSON output
a2db query -p myapp -e prod -d main -f json "SELECT * FROM users LIMIT 10"

# Explore schema
a2db schema -p myapp -e prod -d main tables
a2db schema -p myapp -e prod -d main columns -t users

# List / remove connections
a2db connections
a2db logout -p myapp -e prod -d main
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `login` | Save a connection — validates by connecting first |
| `logout` | Remove a saved connection |
| `list_connections` | List connections (no secrets exposed) |
| `execute` | Run named batch queries with pagination |
| `search_objects` | Explore schema — tables, columns, with detail levels |

### `execute` — the core tool

**Named dict with default connection (preferred):**
```json
{
  "connection": {"project": "myapp", "env": "prod", "db": "main"},
  "queries": {
    "active_users": {"sql": "SELECT id, name FROM users WHERE active = true"},
    "recent_orders": {"sql": "SELECT id, total FROM orders ORDER BY created_at DESC LIMIT 5"}
  }
}
```

**List format (auto-named q1, q2, ...):**
```json
{
  "connection": {"project": "myapp", "env": "prod", "db": "main"},
  "queries": [
    {"sql": "SELECT COUNT(*) AS cnt FROM users"},
    {"sql": "SELECT AVG(total) AS avg_order FROM orders"}
  ]
}
```

**Response (TSV format — default):**
```json
{
  "active_users": {
    "data": "id\tname\n1\tAlice\n2\tBob\n3\tCharlie",
    "rows": 3,
    "truncated": false,
    "time_ms": 12
  },
  "recent_orders": {
    "data": "id\ttotal\n501\t129.00\n500\t49.99",
    "rows": 2,
    "truncated": false,
    "time_ms": 8
  }
}
```

No `::text` casts needed — integers, floats, timestamps, arrays, NULLs all work natively.

### Error context

When a query fails with a column error, a2db enriches the message:

```
column "nme" does not exist
Did you mean: name?
Available columns: id (integer), name (text), email (text), active (integer)
```

### Why TSV?

LLM context windows are expensive. JSON row data is verbose — every row repeats every column name, adds braces, commas, and quotes. TSV is a flat grid: one header row, then just values separated by tabs.

For a 100-row, 5-column result set, TSV typically uses **40-60% fewer tokens** than JSON row format. The structured JSON envelope still gives you metadata (row count, truncation status) — only the row payload is TSV.

Set `format="json"` if you need full structured output with column names on every row.

## Security

### Read-Only Enforcement

Every query is parsed by [SQLGlot](https://github.com/tobymao/sqlglot) before execution:

- **Blocked:** INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER, CREATE, GRANT, REVOKE
- **Bypass-resistant:** multi-statement attacks and comment-wrapped writes are caught at the AST level, not just keyword matching
- **Allowed:** SELECT, UNION, EXPLAIN, SHOW, DESCRIBE, PRAGMA

This is defense-in-depth — you should also use a read-only database user, but a2db won't let writes through even if the user has write permissions.

**Write support** is implemented in the core but not yet exposed via MCP. Planned: per-connection write permissions, explicitly enabled by the human operator — not the agent. See [TODO.md](TODO.md).

### Credential Storage

Connections are saved in `~/.config/a2db/connections/` as TOML files.

- **`${DB_PASSWORD}` syntax** — environment variable references are stored literally and expanded only at connection time. Secrets stay in your environment, not on disk.
- **No secrets in list output** — `list_connections` shows project/env/db and database type, never DSNs or passwords
- Connection files are local to your machine and outside any repository

### Deployment Scope

a2db currently runs as a **local stdio MCP server**. It inherits environment variables from the process that launches it (your shell, Claude Code, Docker). This is the standard model for local MCP servers — the same approach used by DBHub, Google Toolbox, and others.

**Planned:** remote HTTP transport with OAuth 2.1 per the MCP spec. For now, if running in Docker, inject secrets via environment variables at container runtime.

## Comparison

| Feature | a2db | DBHub | Google Toolbox | PGMCP | Supabase MCP |
|---------|------|-------|----------------|-------|--------------|
| **Databases** | 5 (PG, SQLite, MySQL, Oracle, MSSQL) | 5 (PG, MySQL, MSSQL, MariaDB, SQLite) | 40+ (cloud + OSS) | PG only | PG (Supabase) |
| **Batch queries** | Named dict + list | Semicolon-separated | No | No | No |
| **Default connection** | Set once, use for all | Per-query | N/A | Single DB | Single project |
| **Read-only** | SQLGlot AST (enforced) | Keyword check (config) | Hint/annotation | Read-only tx + regex | Config flag |
| **Write support** | Planned (per-connection) | Config flag | Via tool definition | No | Config flag |
| **Output** | JSON + TSV data | Structured text | MCP protocol | Table / JSON / CSV | JSON |
| **Schema discovery** | 3 detail levels | Dedicated tool | Prebuilt tools | Via NL-to-SQL | Dedicated tools |
| **Pre-configured** | `--register` in MCP config | Config file | YAML config | Env var | Cloud-managed |
| **Credentials** | `${ENV_VAR}` in DSN | DSN strings | Env vars + GCP IAM | Env var | OAuth 2.1 |
| **Drivers bundled** | All included | All included | Varies | Built-in | Managed |
| **CLI** | Yes | No | Yes | Yes | No |
| **Error context** | Column suggestions + types | No | No | No | No |
| **License** | Apache 2.0 | MIT | Apache 2.0 | Apache 2.0 | Apache 2.0 |

**When to use what:**

- **a2db** — multi-DB batch queries with clean output, agent-first design, fast setup
- **DBHub** — custom tools via TOML config, web workbench UI
- **Google Toolbox** — GCP ecosystem, IAM integration, 40+ sources
- **PGMCP** — natural-language-to-SQL for PostgreSQL (requires OpenAI key)
- **Supabase MCP** — full Supabase platform management (edge functions, branching, storage)

## Setup by Environment

### Local (macOS / Linux)

```bash
pip install a2db

# CLI
a2db login -p myapp -e dev -d main 'postgresql://user:pass@localhost/mydb'

# Or add as MCP server (see Quick Start)
```

### Docker

```dockerfile
FROM python:3.12-slim
RUN pip install a2db
CMD ["a2db-mcp", "--register", "myapp/prod/main", "postgresql://user:${DB_PASSWORD}@host/mydb"]
```

```bash
docker run -e DB_PASSWORD=secret -i my-a2db-image
```

Secrets are injected as environment variables at runtime — never baked into the image.

### CI / Automation

```bash
pip install a2db

# Pre-configured — no login needed
a2db-mcp --register myapp/ci/main "postgresql://ci_user:${CI_DB_PASSWORD}@db-host/mydb"

# Or use CLI directly
a2db login -p myapp -e ci -d main "postgresql://ci_user:${CI_DB_PASSWORD}@db-host/mydb"
a2db query -p myapp -e ci -d main "SELECT COUNT(*) FROM migrations"
```

## Development

```bash
make bootstrap   # Install deps + hooks
make check       # Lint + test + security (full gate)
make test        # Tests with coverage (90% minimum)
make lint        # Lint only (never modifies files)
make fix         # Auto-fix + lint
```

## License

Apache 2.0

---

<p align="center">
  <sub>🗄️ Agent-first database access since 2025.</sub>
</p>
<p align="center">
  <sub>Built by <a href="https://github.com/iorlas">Denis Tomilin</a></sub>
</p>
