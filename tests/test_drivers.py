from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from a2db.drivers import DriverNotFoundError, DriverRegistry, _parse_dsn


def test_resolve_sqlite():
    reg = DriverRegistry()
    driver = reg.resolve("sqlite")
    assert driver.scheme == "sqlite"
    assert driver.module_name == "sqlite3"


def test_resolve_postgresql():
    reg = DriverRegistry()
    driver = reg.resolve("postgresql")
    assert driver.scheme == "postgresql"
    assert driver.module_name == "psycopg2"


def test_resolve_unknown_raises():
    reg = DriverRegistry()
    with pytest.raises(DriverNotFoundError, match="Unknown database scheme: 'nosql'"):
        reg.resolve("nosql")


def test_connect_sqlite(sqlite_db: Path):
    reg = DriverRegistry()
    conn = reg.connect(f"sqlite:///{sqlite_db}")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    assert cursor.fetchone()[0] == 3
    conn.close()


def test_connect_unknown_scheme_raises():
    reg = DriverRegistry()
    with pytest.raises(DriverNotFoundError):
        reg.connect("nosql://localhost/db")


def test_driver_not_found_error_has_install_hint():
    reg = DriverRegistry()
    driver = reg.resolve("postgresql")
    assert driver.install_hint == "pip install psycopg2-binary"


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


def test_connect_generic_dsn_accepting_driver():
    """psycopg2 is a DSN-accepting driver — connect() should be called with the full DSN string."""
    mock_mod = MagicMock()
    with patch("importlib.import_module", return_value=mock_mod) as mock_import:
        from a2db.drivers import _connect_generic

        _connect_generic("psycopg2", "postgresql://user:pass@localhost/db")
        mock_import.assert_called_once_with("psycopg2")
        mock_mod.connect.assert_called_once_with("postgresql://user:pass@localhost/db")


def test_connect_generic_kwargs_driver():
    """Non-DSN drivers (e.g. mysql.connector) should receive parsed kwargs."""
    mock_mod = MagicMock()
    with patch("importlib.import_module", return_value=mock_mod):
        from a2db.drivers import _connect_generic

        _connect_generic("mysql.connector", "mysql://admin:secret@db.example.com:3306/mydb")
        mock_mod.connect.assert_called_once_with(
            host="db.example.com",
            port=3306,
            user="admin",
            password="secret",
            database="mydb",
        )


def test_connect_generic_import_error_with_known_scheme():
    """ImportError should be wrapped in DriverNotFoundError with install hint."""
    with patch("importlib.import_module", side_effect=ImportError("no module")):
        from a2db.drivers import _connect_generic

        with pytest.raises(DriverNotFoundError, match="pip install mysql-connector-python"):
            _connect_generic("mysql.connector", "mysql://localhost/db")


def test_connect_generic_import_error_unknown_scheme():
    """ImportError for unknown scheme should still produce DriverNotFoundError."""
    with patch("importlib.import_module", side_effect=ImportError("no module")):
        from a2db.drivers import _connect_generic

        with pytest.raises(DriverNotFoundError, match="unknown"):
            _connect_generic("somedriver", "nosql://localhost/db")


def test_resolve_postgres_alias():
    reg = DriverRegistry()
    driver = reg.resolve("postgres")
    assert driver.module_name == "psycopg2"
