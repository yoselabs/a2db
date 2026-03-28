"""Query executor — run named batch queries against database connections."""

from __future__ import annotations

from typing import TYPE_CHECKING

from a2db.drivers import DriverRegistry
from a2db.formatter import QueryResult
from a2db.sql import DSN_TO_DIALECT, validate_read_only, wrap_with_pagination

if TYPE_CHECKING:
    from a2db.connections import ConnectionStore


class QueryExecutor:
    """Executes named batch queries using saved connections."""

    def __init__(self, store: ConnectionStore) -> None:
        self.store = store
        self.registry = DriverRegistry()

    def execute(
        self,
        queries: dict[str, dict],
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, QueryResult]:
        """Execute a batch of named queries. Returns results keyed by name."""
        results = {}
        for name, query_spec in queries.items():
            conn_spec = query_spec["connection"]
            sql = query_spec["sql"]

            validate_read_only(sql)

            info = self.store.load(
                conn_spec["project"],
                conn_spec["env"],
                conn_spec["db"],
            )

            dialect = DSN_TO_DIALECT.get(info.scheme, info.scheme)

            # Request limit+1 rows to detect truncation
            wrapped_sql = wrap_with_pagination(sql, limit=limit + 1, offset=offset, dialect=dialect)

            conn = self.registry.connect(info.dsn)
            try:
                cursor = conn.cursor()
                cursor.execute(wrapped_sql)
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
            finally:
                conn.close()

            truncated = len(rows) > limit
            if truncated:
                rows = rows[:limit]

            results[name] = QueryResult(
                name=name,
                columns=columns,
                rows=[list(row) for row in rows],
                count=len(rows),
                truncated=truncated,
            )
        return results
