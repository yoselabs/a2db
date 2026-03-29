"""Query executor — run named batch queries against database connections."""

from __future__ import annotations

import re
import time
from difflib import get_close_matches
from typing import TYPE_CHECKING

from a2db.drivers import DriverRegistry
from a2db.formatter import QueryResult
from a2db.sql import DSN_TO_DIALECT, validate_read_only, wrap_with_pagination

if TYPE_CHECKING:
    from a2db.connections import ConnectionStore

# Pattern to extract table and column names from common DB error messages
_COLUMN_NOT_FOUND_RE = re.compile(
    r'column "?([^"]+)"? (?:does not exist|not found|of relation "?([^"]+)"?)',
    re.IGNORECASE,
)
_UNDEFINED_COLUMN_RE = re.compile(
    r'(?:Unknown column|no such column)[:\s]+["\']?(\w+)',
    re.IGNORECASE,
)


class QueryError(Exception):
    """Query execution error with enriched context."""


async def _fetch_table_columns(conn, scheme: str, table_name: str) -> list[dict]:
    """Fetch column names and types for a table. Returns [] on failure."""
    try:
        if scheme == "sqlite":
            rows, _ = await conn.fetch(f"PRAGMA table_info('{table_name}')")
            return [{"name": row[1], "type": row[2]} for row in rows]
        rows, _ = await conn.fetch(
            f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table_name}' ORDER BY ordinal_position"  # noqa: S608
        )
        return [{"name": row[0], "type": row[1]} for row in rows]
    except Exception:  # noqa: BLE001
        return []


def _enrich_column_error(error_msg: str, table_columns: list[dict]) -> str:
    """Add column suggestions and type info to a column-not-found error."""
    if not table_columns:
        return error_msg

    col_names = [c["name"] for c in table_columns]

    # Try to extract the missing column name
    missing_col = None
    match = _COLUMN_NOT_FOUND_RE.search(error_msg)
    if match:
        missing_col = match.group(1)
    else:
        match = _UNDEFINED_COLUMN_RE.search(error_msg)
        if match:
            missing_col = match.group(1)

    parts = [error_msg]

    if missing_col:
        suggestions = get_close_matches(missing_col, col_names, n=3, cutoff=0.4)
        if suggestions:
            parts.append(f"Did you mean: {', '.join(suggestions)}?")

    col_summary = ", ".join(f"{c['name']} ({c['type']})" for c in table_columns[:20])
    parts.append(f"Available columns: {col_summary}")

    return "\n".join(parts)


def _extract_table_from_sql(sql: str) -> str | None:
    """Best-effort extraction of the main table name from a SQL query."""
    match = re.search(r"\bFROM\s+([\"']?[\w.]+[\"']?)", sql, re.IGNORECASE)
    if match:
        return match.group(1).strip("\"'")
    return None


class QueryExecutor:
    """Executes named batch queries using saved connections."""

    def __init__(self, store: ConnectionStore) -> None:
        self.store = store
        self.registry = DriverRegistry()

    async def execute(
        self,
        queries: dict[str, dict],
        limit: int = 100,
        offset: int = 0,
        *,
        read_only: bool = True,
    ) -> dict[str, QueryResult]:
        """Execute a batch of named queries. Returns results keyed by name."""
        results = {}
        for name, query_spec in queries.items():
            conn_spec = query_spec["connection"]
            sql = query_spec["sql"]

            if read_only:
                validate_read_only(sql)

            info = self.store.load(
                conn_spec["project"],
                conn_spec["env"],
                conn_spec["db"],
            )

            dialect = DSN_TO_DIALECT.get(info.scheme, info.scheme)

            # Pagination only applies to read queries
            if read_only:
                exec_sql = wrap_with_pagination(sql, limit=limit + 1, offset=offset, dialect=dialect)
            else:
                exec_sql = sql

            conn = await self.registry.connect(info.resolved_dsn)
            try:
                t0 = time.monotonic()
                rows, description = await conn.fetch(exec_sql)
                elapsed_ms = int((time.monotonic() - t0) * 1000)
                columns = [desc[0] for desc in description] if description else []
                if not read_only:
                    await conn.commit()
            except Exception as exc:
                error_msg = str(exc)
                enriched = await self._enrich_error(conn, info.scheme, sql, error_msg)
                raise QueryError(enriched) from exc
            finally:
                await conn.close()

            truncated = len(rows) > limit
            if truncated:
                rows = rows[:limit]

            results[name] = QueryResult(
                name=name,
                columns=columns,
                rows=[list(row) for row in rows],
                count=len(rows),
                truncated=truncated,
                time_ms=elapsed_ms,
            )
        return results

    async def _enrich_error(self, conn, scheme: str, sql: str, error_msg: str) -> str:
        """Try to add helpful context to a query error."""
        table_name = _extract_table_from_sql(sql)
        if not table_name:
            return error_msg

        columns = await _fetch_table_columns(conn, scheme, table_name)
        if not columns:
            return error_msg

        return _enrich_column_error(error_msg, columns)
