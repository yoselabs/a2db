"""CLI frontend — thin wrapper around a2db core."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from a2db import __version__
from a2db.config import DEFAULT_CONFIG_DIR
from a2db.connections import ConnectionInfo, ConnectionStore
from a2db.drivers import DriverNotFoundError, DriverRegistry
from a2db.executor import QueryExecutor
from a2db.formatter import format_results
from a2db.schema import SchemaExplorer


def _store() -> ConnectionStore:
    return ConnectionStore(DEFAULT_CONFIG_DIR)


@click.group(invoke_without_command=True)
@click.version_option(__version__, package_name="a2db")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """a2db — Agent-to-Database. Query databases from CLI or MCP."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.option("-p", "--project", required=True, help="Project name")
@click.option("-e", "--env", required=True, help="Environment")
@click.option("-d", "--db", required=True, help="Database name")
@click.argument("dsn")
def login(project: str, env: str, db: str, dsn: str) -> None:
    """Save a database connection."""
    scheme = ConnectionInfo(project=project, env=env, db=db, dsn=dsn).scheme
    try:
        DriverRegistry().resolve(scheme)
    except DriverNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)

    store = _store()
    path = store.save(project, env, db, dsn)
    click.echo(f"Connection saved: {path}")


@cli.command()
@click.option("-p", "--project", required=True, help="Project name")
@click.option("-e", "--env", required=True, help="Environment")
@click.option("-d", "--db", required=True, help="Database name")
def logout(project: str, env: str, db: str) -> None:
    """Remove a saved connection."""
    store = _store()
    try:
        store.delete(project, env, db)
    except FileNotFoundError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    click.echo(f"Connection removed: {project}/{env}/{db}")


@cli.command()
@click.option("-p", "--project", default=None, help="Filter by project")
def connections(project: str | None) -> None:
    """List saved connections."""
    store = _store()
    results = store.list_connections(project=project)
    if not results:
        click.echo("No connections found.")
        return
    for info in results:
        click.echo(f"{info.project}/{info.env}/{info.db} ({info.scheme})")


@cli.command()
@click.option("-p", "--project", required=True, help="Project name")
@click.option("-e", "--env", required=True, help="Environment")
@click.option("-d", "--db", required=True, help="Database name")
@click.option("-f", "--format", "fmt", default="tsv", type=click.Choice(["tsv", "json"]), help="Output format")
@click.option("-l", "--limit", default=100, help="Max rows per query")
@click.option("-o", "--offset", default=0, help="Row offset")
@click.option("--batch", "batch_file", type=click.Path(exists=True), help="JSON file with named queries")
@click.argument("sql", required=False)
def query(project: str, env: str, db: str, fmt: str, limit: int, offset: int, batch_file: str | None, sql: str | None) -> None:
    """Execute SQL queries."""
    store = _store()
    executor = QueryExecutor(store)

    if batch_file:
        queries = json.loads(Path(batch_file).read_text())["queries"]
    elif sql:
        queries = {
            "result": {
                "connection": {"project": project, "env": env, "db": db},
                "sql": sql,
            }
        }
    else:
        click.echo("Error: provide SQL argument or --batch file", err=True)
        sys.exit(1)

    results = executor.execute(queries, limit=limit, offset=offset)
    click.echo(format_results(results, fmt=fmt))


@cli.command()
@click.option("-p", "--project", required=True, help="Project name")
@click.option("-e", "--env", required=True, help="Environment")
@click.option("-d", "--db", required=True, help="Database name")
@click.argument("object_type", type=click.Choice(["tables", "columns", "full"]))
@click.option("-t", "--table", default=None, help="Table name (for columns)")
@click.option("--pattern", default="%", help="SQL LIKE pattern")
@click.option("-f", "--format", "fmt", default="tsv", type=click.Choice(["tsv", "json"]), help="Output format")
def schema(project: str, env: str, db: str, object_type: str, table: str | None, pattern: str, fmt: str) -> None:
    """Explore database schema."""
    explorer = SchemaExplorer(_store())
    conn_spec = {"project": project, "env": env, "db": db}

    detail_level = "full" if object_type == "full" else "names"
    obj_type = "column" if object_type == "columns" else "table"

    result = explorer.search_objects(
        connection=conn_spec,
        object_type=obj_type,
        pattern=pattern,
        table=table,
        detail_level=detail_level,
    )

    if fmt == "json":
        click.echo(json.dumps(result, indent=2))
    else:
        for entry in result["results"]:
            if detail_level == "full" and "columns" in entry:
                click.echo(f"\n{entry['name']}:")
                for col in entry["columns"]:
                    parts = [f"  {col['name']} {col.get('type', '')}"]
                    if col.get("pk"):
                        parts.append("PK")
                    click.echo(" ".join(parts))
            else:
                click.echo(entry["name"])
