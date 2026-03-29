# a2db

[![PyPI](https://img.shields.io/pypi/v/a2db)](https://pypi.org/project/a2db/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Agent-to-Database — give AI agents safe, read-only access to your databases via CLI or MCP.

## Features

- **Multi-connection** — manage connections by project/environment/database triple
- **Named batch queries** — run multiple queries across different databases in one call
- **Schema explorer** — progressive discovery (tables, columns) at varying detail levels
- **Read-only by default** — blocks INSERT, UPDATE, DELETE, DROP, even via SQL comments
- **Async** — asyncpg for PostgreSQL, aiosqlite for SQLite, sync drivers wrapped for others
- **TSV output** — token-efficient default format for LLMs, with JSON option
- **Env var support** — `${DB_PASSWORD}` in DSNs, expanded at connection time

## Supported Databases

All drivers are bundled — no extra installs needed.

| Database | Driver |
|----------|--------|
| PostgreSQL | asyncpg |
| SQLite | aiosqlite |
| MySQL / MariaDB | mysql-connector-python |
| Oracle | oracledb |
| SQL Server | pymssql |

## Install

```bash
pip install a2db
```

## CLI

```bash
# Save a connection (validates by connecting)
a2db login -p myapp -e prod -d users "postgresql://user:pass@localhost/mydb"

# Use env vars in DSN (expanded at connection time)
a2db login -p myapp -e prod -d users 'postgresql://user:${DB_PASS}@localhost/mydb'

# List connections
a2db connections

# Query
a2db query -p myapp -e prod -d users "SELECT * FROM users LIMIT 10"

# JSON output
a2db query -p myapp -e prod -d users -f json "SELECT * FROM users LIMIT 10"

# Schema exploration
a2db schema -p myapp -e prod -d users tables
a2db schema -p myapp -e prod -d users columns -t users
a2db schema -p myapp -e prod -d users full

# Remove a connection
a2db logout -p myapp -e prod -d users
```

## MCP Server

a2db ships as an MCP server for AI agents. Add to your client config:

**Claude Code:**
```bash
claude mcp add -s user a2db -- a2db-mcp
```

**Manual config (Claude Desktop, Cursor, etc.):**
```json
{
  "mcpServers": {
    "a2db": {
      "command": "uvx",
      "args": ["a2db-mcp"]
    }
  }
}
```

### MCP Tools

| Tool | Description |
|------|-------------|
| `login` | Save a connection (validates by connecting first) |
| `logout` | Remove a saved connection |
| `list_connections` | List connections (no secrets exposed) |
| `execute` | Run named batch queries with pagination, returns TSV or JSON |
| `search_objects` | Explore schema — tables, columns, with detail levels |

### Example: `execute`

```json
{
  "queries": {
    "active_users": {
      "connection": {"project": "myapp", "env": "prod", "db": "users"},
      "sql": "SELECT id, name FROM users WHERE active = true LIMIT 10"
    },
    "recent_orders": {
      "connection": {"project": "myapp", "env": "prod", "db": "orders"},
      "sql": "SELECT id, total FROM orders ORDER BY created_at DESC LIMIT 5"
    }
  }
}
```

## Development

```bash
make bootstrap   # Install deps + hooks
make check       # Lint + test + security
make lint        # Lint only
make fix         # Auto-fix + lint
```

## License

MIT
