from pathlib import Path

import pytest

from a2db.connections import ConnectionStore
from a2db.executor import QueryError, QueryExecutor, _enrich_column_error, _extract_table_from_sql
from a2db.sql import ReadOnlyViolationError


@pytest.fixture
def executor(config_dir: Path, sqlite_db: Path) -> QueryExecutor:
    store = ConnectionStore(config_dir)
    store.save("testapp", "dev", "main", f"sqlite:///{sqlite_db}")
    return QueryExecutor(store)


async def test_execute_single_query(executor: QueryExecutor):
    queries = {
        "all_users": {
            "connection": {"project": "testapp", "env": "dev", "db": "main"},
            "sql": "SELECT id, name FROM users",
        }
    }
    results = await executor.execute(queries)
    assert "all_users" in results
    assert results["all_users"].count == 3
    assert results["all_users"].columns == ["id", "name"]


async def test_execute_multiple_queries(executor: QueryExecutor):
    queries = {
        "users": {
            "connection": {"project": "testapp", "env": "dev", "db": "main"},
            "sql": "SELECT * FROM users WHERE active = 1",
        },
        "orders": {
            "connection": {"project": "testapp", "env": "dev", "db": "main"},
            "sql": "SELECT * FROM orders",
        },
    }
    results = await executor.execute(queries)
    assert len(results) == 2
    assert results["users"].count == 2
    assert results["orders"].count == 2


async def test_execute_with_limit(executor: QueryExecutor):
    queries = {
        "limited": {
            "connection": {"project": "testapp", "env": "dev", "db": "main"},
            "sql": "SELECT * FROM users",
        }
    }
    results = await executor.execute(queries, limit=1)
    assert results["limited"].count == 1


async def test_execute_with_offset(executor: QueryExecutor):
    queries = {
        "paged": {
            "connection": {"project": "testapp", "env": "dev", "db": "main"},
            "sql": "SELECT id FROM users ORDER BY id",
        }
    }
    results = await executor.execute(queries, limit=1, offset=1)
    assert results["paged"].count == 1
    assert results["paged"].rows[0][0] == 2


async def test_execute_rejects_write(executor: QueryExecutor):
    queries = {
        "bad": {
            "connection": {"project": "testapp", "env": "dev", "db": "main"},
            "sql": "DELETE FROM users",
        }
    }
    with pytest.raises(ReadOnlyViolationError):
        await executor.execute(queries)


async def test_execute_truncated_flag(executor: QueryExecutor):
    queries = {
        "check": {
            "connection": {"project": "testapp", "env": "dev", "db": "main"},
            "sql": "SELECT * FROM users",
        }
    }
    results = await executor.execute(queries, limit=2)
    assert results["check"].truncated is True


async def test_execute_not_truncated(executor: QueryExecutor):
    queries = {
        "check": {
            "connection": {"project": "testapp", "env": "dev", "db": "main"},
            "sql": "SELECT * FROM users",
        }
    }
    results = await executor.execute(queries, limit=100)
    assert results["check"].truncated is False


async def test_execute_column_error_suggests_alternatives(executor: QueryExecutor):
    queries = {
        "bad_col": {
            "connection": {"project": "testapp", "env": "dev", "db": "main"},
            "sql": "SELECT nme FROM users",
        }
    }
    with pytest.raises(QueryError, match="Available columns"):
        await executor.execute(queries)


def test_extract_table_from_sql():
    assert _extract_table_from_sql("SELECT * FROM users WHERE id = 1") == "users"
    assert _extract_table_from_sql("SELECT count(*) from orders") == "orders"
    assert _extract_table_from_sql('SELECT * FROM "MyTable"') == "MyTable"
    assert _extract_table_from_sql("SELECT 1") is None  # no FROM clause


def test_enrich_column_error_with_suggestions():
    columns = [
        {"name": "name", "type": "text"},
        {"name": "email", "type": "text"},
        {"name": "active", "type": "integer"},
    ]
    msg = 'column "nme" does not exist'
    enriched = _enrich_column_error(msg, columns)
    assert "Did you mean: name?" in enriched
    assert "Available columns:" in enriched
    assert "name (text)" in enriched


def test_enrich_column_error_shows_types():
    columns = [
        {"name": "fetched_at", "type": "text"},
        {"name": "content", "type": "text"},
    ]
    msg = "some generic error"
    enriched = _enrich_column_error(msg, columns)
    assert "fetched_at (text)" in enriched


async def test_execute_numeric_types_in_results(executor: QueryExecutor):
    queries = {
        "counts": {
            "connection": {"project": "testapp", "env": "dev", "db": "main"},
            "sql": "SELECT COUNT(*) AS cnt, SUM(active) AS total_active FROM users",
        }
    }
    results = await executor.execute(queries)
    assert results["counts"].count == 1
    # Verify numeric values are present (not requiring ::text casts)
    assert results["counts"].rows[0][0] == 3  # COUNT(*)
    assert results["counts"].rows[0][1] == 2  # SUM(active)
