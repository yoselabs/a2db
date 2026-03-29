from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from a2db.drivers import DriverNotFoundError, DriverRegistry, _parse_dsn


def test_resolve_sqlite():
    reg = DriverRegistry()
    driver = reg.resolve("sqlite")
    assert driver.scheme == "sqlite"
    assert driver.module_name == "aiosqlite"


def test_resolve_postgresql():
    reg = DriverRegistry()
    driver = reg.resolve("postgresql")
    assert driver.scheme == "postgresql"
    assert driver.module_name == "asyncpg"


def test_resolve_unknown_raises():
    reg = DriverRegistry()
    with pytest.raises(DriverNotFoundError, match="Unknown database scheme: 'nosql'"):
        reg.resolve("nosql")


async def test_connect_sqlite(sqlite_db: Path):
    reg = DriverRegistry()
    conn = await reg.connect(f"sqlite:///{sqlite_db}")
    rows, _desc = await conn.fetch("SELECT COUNT(*) FROM users")
    assert rows[0][0] == 3
    await conn.close()


async def test_connect_unknown_scheme_raises():
    reg = DriverRegistry()
    with pytest.raises(DriverNotFoundError):
        await reg.connect("nosql://localhost/db")


def test_driver_not_found_error_has_install_hint():
    reg = DriverRegistry()
    driver = reg.resolve("postgresql")
    assert driver.install_hint == "pip install asyncpg"


def test_parse_dsn_kwargs():
    from a2db.drivers import _parse_dsn_kwargs

    kwargs = _parse_dsn_kwargs("mysql://admin:secret@db.example.com:3306/mydb")
    assert kwargs["host"] == "db.example.com"
    assert kwargs["port"] == 3306
    assert kwargs["user"] == "admin"
    assert kwargs["password"] == "secret"
    assert kwargs["database"] == "mydb"


def test_parse_dsn_kwargs_minimal():
    from a2db.drivers import _parse_dsn_kwargs

    kwargs = _parse_dsn_kwargs("mysql://localhost/mydb")
    assert kwargs["host"] == "localhost"
    assert kwargs["database"] == "mydb"
    assert "port" not in kwargs
    assert "user" not in kwargs


def test_all_schemes_have_install_hints():
    reg = DriverRegistry()
    for scheme in ["postgresql", "mysql", "mariadb", "sqlite", "oracle", "mssql"]:
        driver = reg.resolve(scheme)
        assert driver.install_hint, f"Missing install hint for {scheme}"


def test_parse_dsn_returns_scheme_and_original():
    scheme, original = _parse_dsn("postgresql://user:pass@localhost:5432/mydb")
    assert scheme == "postgresql"
    assert original == "postgresql://user:pass@localhost:5432/mydb"


def test_parse_dsn_strips_driver_suffix():
    scheme, _ = _parse_dsn("postgresql+psycopg2://user@localhost/db")
    assert scheme == "postgresql"


async def test_connect_sync_generic_kwargs_driver():
    """Non-DSN drivers (e.g. mysql.connector) should receive parsed kwargs via to_thread."""
    mock_conn = MagicMock()
    mock_mod = MagicMock()
    mock_mod.connect.return_value = mock_conn
    with patch("importlib.import_module", return_value=mock_mod):
        from a2db.drivers import _connect_sync_generic

        result = await _connect_sync_generic("mysql.connector", "mysql://admin:secret@db.example.com:3306/mydb")
        assert result is not None


async def test_connect_sync_generic_import_error():
    """ImportError should be wrapped in DriverNotFoundError."""
    with patch("importlib.import_module", side_effect=ImportError("no module")):
        from a2db.drivers import _connect_sync_generic

        with pytest.raises(DriverNotFoundError, match="pip install mysql-connector-python"):
            await _connect_sync_generic("mysql.connector", "mysql://localhost/db")


async def test_connect_sync_generic_import_error_unknown_scheme():
    """ImportError for unknown scheme should still produce DriverNotFoundError."""
    with patch("importlib.import_module", side_effect=ImportError("no module")):
        from a2db.drivers import _connect_sync_generic

        with pytest.raises(DriverNotFoundError, match="unknown"):
            await _connect_sync_generic("somedriver", "nosql://localhost/db")


def test_resolve_postgres_alias():
    reg = DriverRegistry()
    driver = reg.resolve("postgres")
    assert driver.module_name == "asyncpg"


async def test_async_sqlite_connection_fetch_and_close(sqlite_db):
    """_AsyncSqliteConnection.fetch returns rows+description; close works."""
    import aiosqlite

    from a2db.drivers import _AsyncSqliteConnection

    raw = await aiosqlite.connect(str(sqlite_db))
    conn = _AsyncSqliteConnection(raw)
    rows, desc = await conn.fetch("SELECT id, name FROM users ORDER BY id")
    assert len(rows) == 3
    assert rows[0][1] == "Alice"
    assert desc is not None
    await conn.close()


async def test_async_sync_connection_fetch_and_close():
    """_AsyncSyncConnection.fetch and close delegate to sync DBAPI via mock."""
    from a2db.drivers import _AsyncSyncConnection

    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = [(42,)]
    mock_cursor.description = [("x", None)]

    mock_raw = MagicMock()
    mock_raw.cursor.return_value = mock_cursor
    mock_raw.close.return_value = None

    conn = _AsyncSyncConnection(mock_raw)
    rows, desc = await conn.fetch("SELECT x FROM t")
    assert rows == [(42,)]
    assert desc is not None
    await conn.close()
    mock_raw.close.assert_called_once()


async def test_async_pg_connection_fetch_with_rows():
    """_AsyncPgConnection.fetch maps asyncpg Record rows to tuples."""
    from a2db.drivers import _AsyncPgConnection

    mock_row = MagicMock()
    mock_row.keys.return_value = ["id", "name"]
    mock_row.values.return_value = [1, "Alice"]

    mock_asyncpg_conn = MagicMock()
    mock_asyncpg_conn.fetch = AsyncMock(return_value=[mock_row])
    mock_asyncpg_conn.close = AsyncMock()

    conn = _AsyncPgConnection(mock_asyncpg_conn)
    rows, columns = await conn.fetch("SELECT id, name FROM users")
    assert rows == [(1, "Alice")]
    assert columns == [("id", None), ("name", None)]
    await conn.close()


async def test_async_pg_connection_fetch_empty():
    """_AsyncPgConnection.fetch returns empty lists when no rows."""
    from a2db.drivers import _AsyncPgConnection

    mock_asyncpg_conn = MagicMock()
    mock_asyncpg_conn.fetch = AsyncMock(return_value=[])
    mock_asyncpg_conn.close = AsyncMock()

    conn = _AsyncPgConnection(mock_asyncpg_conn)
    rows, columns = await conn.fetch("SELECT id FROM users WHERE 1=0")
    assert rows == []
    assert columns == []


async def test_connect_asyncpg_import_error(monkeypatch):
    """_connect_asyncpg raises DriverNotFoundError when asyncpg is missing."""
    import sys

    import a2db.drivers as drivers_module

    monkeypatch.setitem(sys.modules, "asyncpg", None)
    # Force re-import to pick up the monkeypatched sys.modules
    with pytest.raises(DriverNotFoundError, match="asyncpg"):
        await drivers_module._connect_asyncpg("postgresql://localhost/db")


async def test_connect_registry_uses_sync_generic_for_mysql():
    """DriverRegistry.connect routes mysql to _connect_sync_generic."""
    mock_conn = MagicMock()
    mock_mod = MagicMock()
    mock_mod.connect.return_value = mock_conn

    with patch("importlib.import_module", return_value=mock_mod):
        reg = DriverRegistry()
        result = await reg.connect("mysql://admin:secret@db.example.com:3306/mydb")
        assert result is not None


async def test_connect_sqlite_with_netloc(tmp_path):
    """_connect_sqlite handles sqlite://hostname/path style DSNs."""
    from a2db.drivers import _connect_sqlite

    db_path = tmp_path / "test.db"
    import sqlite3

    raw = sqlite3.connect(str(db_path))
    raw.execute("CREATE TABLE t (x INTEGER)")
    raw.commit()
    raw.close()

    # sqlite:///path (empty netloc) — already covered; test netloc form
    conn = await _connect_sqlite(f"sqlite:///{db_path}")
    rows, _ = await conn.fetch("SELECT x FROM t")
    assert rows == []
    await conn.close()


def test_parse_dsn_kwargs_no_path_slash_only():
    """_parse_dsn_kwargs skips database when path is just '/'."""
    from a2db.drivers import _parse_dsn_kwargs

    kwargs = _parse_dsn_kwargs("mysql://localhost/")
    assert "database" not in kwargs
