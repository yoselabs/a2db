from pathlib import Path

import pytest

from a2db.connections import ConnectionStore
from a2db.schema import SchemaExplorer


@pytest.fixture
def explorer(config_dir: Path, sqlite_db: Path) -> SchemaExplorer:
    store = ConnectionStore(config_dir)
    store.save("testapp", "dev", "main", f"sqlite:///{sqlite_db}")
    return SchemaExplorer(store)


def _conn_spec():
    return {"project": "testapp", "env": "dev", "db": "main"}


def test_search_tables_names(explorer: SchemaExplorer):
    result = explorer.search_objects(
        connection=_conn_spec(),
        object_type="table",
        detail_level="names",
    )
    names = [r["name"] for r in result["results"]]
    assert "users" in names
    assert "orders" in names


def test_search_tables_with_pattern(explorer: SchemaExplorer):
    result = explorer.search_objects(
        connection=_conn_spec(),
        object_type="table",
        pattern="user%",
        detail_level="names",
    )
    names = [r["name"] for r in result["results"]]
    assert "users" in names
    assert "orders" not in names


def test_search_columns_names(explorer: SchemaExplorer):
    result = explorer.search_objects(
        connection=_conn_spec(),
        object_type="column",
        table="users",
        detail_level="names",
    )
    names = [r["name"] for r in result["results"]]
    assert "id" in names
    assert "name" in names
    assert "email" in names


def test_search_tables_summary(explorer: SchemaExplorer):
    result = explorer.search_objects(
        connection=_conn_spec(),
        object_type="table",
        detail_level="summary",
    )
    users_entry = next(r for r in result["results"] if r["name"] == "users")
    assert "column_count" in users_entry


def test_search_tables_full(explorer: SchemaExplorer):
    result = explorer.search_objects(
        connection=_conn_spec(),
        object_type="table",
        detail_level="full",
    )
    users_entry = next(r for r in result["results"] if r["name"] == "users")
    assert "columns" in users_entry
    col_names = [c["name"] for c in users_entry["columns"]]
    assert "id" in col_names


def test_search_with_limit(explorer: SchemaExplorer):
    result = explorer.search_objects(
        connection=_conn_spec(),
        object_type="table",
        detail_level="names",
        limit=1,
    )
    assert len(result["results"]) == 1
    assert result["truncated"] is True


def test_unsupported_object_type_raises(explorer: SchemaExplorer):
    with pytest.raises(ValueError, match="Unsupported object type: 'index'"):
        explorer.search_objects(
            connection=_conn_spec(),
            object_type="index",
        )


def test_result_metadata(explorer: SchemaExplorer):
    result = explorer.search_objects(
        connection=_conn_spec(),
        object_type="table",
        detail_level="names",
    )
    assert result["object_type"] == "table"
    assert result["detail_level"] == "names"
    assert "count" in result


def test_search_columns_summary(explorer: SchemaExplorer):
    result = explorer.search_objects(
        connection=_conn_spec(),
        object_type="column",
        table="users",
        detail_level="summary",
    )
    col = next(c for c in result["results"] if c["name"] == "id")
    assert "type" in col
    assert "nullable" in col
    assert "pk" in col


def test_search_columns_full(explorer: SchemaExplorer):
    result = explorer.search_objects(
        connection=_conn_spec(),
        object_type="column",
        table="users",
        detail_level="full",
    )
    col = next(c for c in result["results"] if c["name"] == "name")
    assert "type" in col
    assert "nullable" in col
    assert "pk" in col


def test_search_columns_no_table_returns_empty(explorer: SchemaExplorer):
    """When no table is given for column search with SQLite, returns empty list."""
    result = explorer.search_objects(
        connection=_conn_spec(),
        object_type="column",
        detail_level="names",
    )
    assert result["results"] == []
    assert result["count"] == 0


def test_search_columns_with_pattern(explorer: SchemaExplorer):
    result = explorer.search_objects(
        connection=_conn_spec(),
        object_type="column",
        table="users",
        pattern="%name%",
        detail_level="names",
    )
    names = [r["name"] for r in result["results"]]
    assert "name" in names
    assert "id" not in names
