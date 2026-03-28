# a2db

Agent-to-Database — query databases from CLI or as an MCP server.

## Install

```bash
pip install a2db
```

Install the database driver you need:

```bash
pip install psycopg2-binary        # PostgreSQL
pip install mysql-connector-python  # MySQL
# SQLite is built-in
```

## CLI Usage

```bash
# Save a connection
a2db login -p myapp -e prod -d users "postgresql://user:pass@localhost/mydb"

# List connections
a2db connections

# Run a query
a2db query -p myapp -e prod -d users "SELECT * FROM users LIMIT 10"

# JSON output
a2db query -p myapp -e prod -d users -f json "SELECT * FROM users LIMIT 10"

# Explore schema
a2db schema -p myapp -e prod -d users tables
a2db schema -p myapp -e prod -d users columns -t users
a2db schema -p myapp -e prod -d users full
```

## MCP Usage

Add to your MCP client configuration:

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

## Development

```bash
make bootstrap   # Install deps
make check       # Lint + test
```

## License

MIT
