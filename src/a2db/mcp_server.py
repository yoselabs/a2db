"""MCP server frontend — thin wrapper around a2db core."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from a2db.config import DEFAULT_CONFIG_DIR
from a2db.connections import ConnectionInfo, ConnectionStore
from a2db.drivers import DriverRegistry
from a2db.executor import QueryExecutor
from a2db.formatter import format_results
from a2db.schema import SchemaExplorer

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
async def login(project: str, env: str, db: str, dsn: str) -> str:
    """Save a database connection. Validates by attempting a real connection."""
    info = ConnectionInfo(project=project, env=env, db=db, dsn=dsn)
    DriverRegistry().resolve(info.scheme)

    # Validate by connecting
    conn = await DriverRegistry().connect(info.resolved_dsn)
    await conn.close()

    store = _store()
    path = store.save(project, env, db, dsn)
    return f"Connection saved: {path}"


@server.tool()
def logout(project: str, env: str, db: str) -> str:
    """Remove a saved connection."""
    store = _store()
    store.delete(project, env, db)
    return f"Connection removed: {project}/{env}/{db}"


@server.tool()
def list_connections(project: str | None = None) -> str:
    """List saved connections. Returns project/env/db and database type (no secrets)."""
    store = _store()
    results = store.list_connections(project=project)
    if not results:
        return "No connections found."
    lines = [f"{r.project}/{r.env}/{r.db} ({r.scheme})" for r in results]
    return "\n".join(lines)


def _normalize_queries(queries: dict[str, dict] | list[dict]) -> dict[str, dict]:
    """Normalize queries to named dict format.

    Accepts both named dict ({"label": {connection, sql}}) and list
    ([{connection, sql}]) formats. Lists get auto-named q1, q2, etc.
    """
    if isinstance(queries, list):
        return {f"q{i + 1}": q for i, q in enumerate(queries)}
    return queries


@server.tool()
async def execute(
    queries: dict[str, dict] | list[dict[str, Any]],
    format: str = "tsv",  # noqa: A002
    limit: int = 100,
    offset: int = 0,
) -> str:
    """Execute named SQL queries. Each query specifies its connection and SQL.

    Example queries parameter (named dict — preferred):
    {
        "active_users": {
            "connection": {"project": "myapp", "env": "prod", "db": "users"},
            "sql": "SELECT id, name FROM users WHERE active = true"
        }
    }

    Also accepts a list of queries (auto-named q1, q2, ...):
    [
        {
            "connection": {"project": "myapp", "env": "prod", "db": "users"},
            "sql": "SELECT id, name FROM users WHERE active = true"
        }
    ]

    Returns results in TSV (default) or JSON format.
    """
    normalized = _normalize_queries(queries)
    store = _store()
    executor = QueryExecutor(store)
    results = await executor.execute(normalized, limit=limit, offset=offset)
    return format_results(results, fmt=format)


@server.tool()
async def search_objects(
    connection: dict[str, str],
    object_type: str,
    pattern: str = "%",
    schema: str | None = None,
    table: str | None = None,
    detail_level: str = "names",
    limit: int = 100,
) -> str:
    """Search database objects.

    object_type: table, column
    detail_level: names (minimal), summary (with metadata), full (complete structure)
    """
    explorer = SchemaExplorer(_store())
    result = await explorer.search_objects(
        connection=connection,
        object_type=object_type,
        pattern=pattern,
        schema=schema,
        table=table,
        detail_level=detail_level,
        limit=limit,
    )
    return json.dumps(result, indent=2)


def main() -> None:
    """Run the MCP server (stdio transport)."""
    server.run()


if __name__ == "__main__":
    main()
