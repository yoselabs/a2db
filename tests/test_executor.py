from pathlib import Path

import pytest

from a2db.connections import ConnectionStore
from a2db.executor import QueryExecutor
from a2db.sql import ReadOnlyViolationError


@pytest.fixture
def executor(config_dir: Path, sqlite_db: Path) -> QueryExecutor:
    store = ConnectionStore(config_dir)
    store.save("testapp", "dev", "main", f"sqlite:///{sqlite_db}")
    return QueryExecutor(store)


def test_execute_single_query(executor: QueryExecutor):
    queries = {
        "all_users": {
            "connection": {"project": "testapp", "env": "dev", "db": "main"},
            "sql": "SELECT id, name FROM users",
        }
    }
    results = executor.execute(queries)
    assert "all_users" in results
    assert results["all_users"].count == 3
    assert results["all_users"].columns == ["id", "name"]


def test_execute_multiple_queries(executor: QueryExecutor):
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
    results = executor.execute(queries)
    assert len(results) == 2
    assert results["users"].count == 2
    assert results["orders"].count == 2


def test_execute_with_limit(executor: QueryExecutor):
    queries = {
        "limited": {
            "connection": {"project": "testapp", "env": "dev", "db": "main"},
            "sql": "SELECT * FROM users",
        }
    }
    results = executor.execute(queries, limit=1)
    assert results["limited"].count == 1


def test_execute_with_offset(executor: QueryExecutor):
    queries = {
        "paged": {
            "connection": {"project": "testapp", "env": "dev", "db": "main"},
            "sql": "SELECT id FROM users ORDER BY id",
        }
    }
    results = executor.execute(queries, limit=1, offset=1)
    assert results["paged"].count == 1
    assert results["paged"].rows[0][0] == 2


def test_execute_rejects_write(executor: QueryExecutor):
    queries = {
        "bad": {
            "connection": {"project": "testapp", "env": "dev", "db": "main"},
            "sql": "DELETE FROM users",
        }
    }
    with pytest.raises(ReadOnlyViolationError):
        executor.execute(queries)


def test_execute_truncated_flag(executor: QueryExecutor):
    queries = {
        "check": {
            "connection": {"project": "testapp", "env": "dev", "db": "main"},
            "sql": "SELECT * FROM users",
        }
    }
    results = executor.execute(queries, limit=2)
    # We got 2 rows but there are 3 total — truncated should be true
    assert results["check"].truncated is True


def test_execute_not_truncated(executor: QueryExecutor):
    queries = {
        "check": {
            "connection": {"project": "testapp", "env": "dev", "db": "main"},
            "sql": "SELECT * FROM users",
        }
    }
    results = executor.execute(queries, limit=100)
    assert results["check"].truncated is False
