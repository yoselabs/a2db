"""SQL wrapping — pagination via SQLGlot and read-only validation."""

from __future__ import annotations

import sqlglot

MAX_ROWS = 10_000
DEFAULT_LIMIT = 100

# Maps DSN scheme to SQLGlot dialect name
DSN_TO_DIALECT: dict[str, str] = {
    "postgresql": "postgres",
    "postgres": "postgres",
    "mysql": "mysql",
    "mariadb": "mysql",
    "sqlite": "sqlite",
    "oracle": "oracle",
    "mssql": "tsql",
}

_FORBIDDEN_STATEMENTS = {"INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE", "ALTER", "CREATE", "GRANT", "REVOKE"}


class ReadOnlyViolationError(Exception):
    """Raised when a query contains a write operation."""


def validate_read_only(sql: str) -> None:
    """Reject DML/DDL statements. Only SELECT, WITH, EXPLAIN, SHOW allowed."""
    first_token = sql.strip().split()[0].upper().rstrip(";")
    if first_token in _FORBIDDEN_STATEMENTS:
        raise ReadOnlyViolationError(f"Write operation not allowed: {first_token}")


def wrap_with_pagination(
    sql: str,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    dialect: str = "sqlite",
) -> str:
    """Wrap a SQL query with LIMIT/OFFSET using SQLGlot dialect transpilation."""
    limit = min(limit, MAX_ROWS)
    sqlglot_dialect = DSN_TO_DIALECT.get(dialect, dialect)

    wrapped = f"SELECT * FROM ({sql}) AS _q LIMIT {limit} OFFSET {offset}"  # noqa: S608
    transpiled = sqlglot.transpile(wrapped, read=sqlglot_dialect, write=sqlglot_dialect)
    return transpiled[0]
