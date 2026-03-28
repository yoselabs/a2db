"""MCP server frontend — thin wrapper around a2db core."""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from a2db.connections import ConnectionStore
from a2db.executor import QueryExecutor
from a2db.formatter import format_results
from a2db.schema import SchemaExplorer

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "a2db" / "connections"

server = FastMCP(
    "a2db",
    instructions=(
        "Agent-to-Database — query and explore databases. "
        "Connections are identified by (project, env, db) triple. "
        "Use 'login' to save a connection, then 'execute' to run queries. "
        "Always include LIMIT in your queries or use the limit parameter. "
        "Default output is TSV for token efficiency."
    ),
)


def _store() -> ConnectionStore:
    return ConnectionStore(DEFAULT_CONFIG_DIR)


@server.tool()
def login(project: str, env: str, db: str, dsn: str) -> str:
    """Save a database connection. The (project, env, db) triple is the unique key."""
    store = _store()
    path = store.save(project, env, db, dsn)
    return f"Connection saved: {path}"


@server.tool()
def list_connections(project: str | None = None) -> str:
    """List saved connections. Returns project/env/db and database type (no secrets)."""
    store = _store()
    results = store.list_connections(project=project)
    if not results:
        return "No connections found."
    lines = [f"{r.project}/{r.env}/{r.db} ({r.scheme})" for r in results]
    return "\n".join(lines)


@server.tool()
def execute(
    queries: dict[str, dict],
    format: str = "tsv",  # noqa: A002
    limit: int = 100,
    offset: int = 0,
) -> str:
    """Execute named SQL queries. Each query specifies its connection and SQL.

    Example queries parameter:
    {
        "active_users": {
            "connection": {"project": "myapp", "env": "prod", "db": "users"},
            "sql": "SELECT id, name FROM users WHERE active = true"
        }
    }

    Returns results in TSV (default) or JSON format.
    """
    store = _store()
    executor = QueryExecutor(store)
    results = executor.execute(queries, limit=limit, offset=offset)
    return format_results(results, fmt=format)


@server.tool()
def search_objects(
    connection: dict[str, str],
    object_type: str,
    pattern: str = "%",
    schema: str | None = None,
    table: str | None = None,
    detail_level: str = "names",
    limit: int = 100,
) -> str:
    """Search database objects (tables, columns, indexes, etc.).

    object_type: schema, table, column, index, procedure, function
    detail_level: names (minimal), summary (with metadata), full (complete structure)
    """
    explorer = SchemaExplorer(_store())
    result = explorer.search_objects(
        connection=connection,
        object_type=object_type,
        pattern=pattern,
        schema=schema,
        table=table,
        detail_level=detail_level,
        limit=limit,
    )
    return json.dumps(result, indent=2)
