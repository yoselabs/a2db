"""Driver registry — resolve DSN schemes to DBAPI 2.0 drivers."""

from __future__ import annotations

import importlib
import sqlite3
from dataclasses import dataclass
from urllib.parse import urlparse


class DriverNotFoundError(Exception):
    """Raised when a database driver cannot be resolved or imported."""


@dataclass(frozen=True)
class DriverInfo:
    """Metadata about a DBAPI 2.0 driver."""

    scheme: str
    module_name: str
    install_hint: str
    connect_kwargs_fn: str = "default"


# Registry of supported database schemes
_DRIVERS: dict[str, DriverInfo] = {
    "postgresql": DriverInfo("postgresql", "psycopg2", "pip install psycopg2-binary"),
    "postgres": DriverInfo("postgres", "psycopg2", "pip install psycopg2-binary"),
    "mysql": DriverInfo("mysql", "mysql.connector", "pip install mysql-connector-python"),
    "mariadb": DriverInfo("mariadb", "mariadb", "pip install mariadb"),
    "sqlite": DriverInfo("sqlite", "sqlite3", "built-in"),
    "oracle": DriverInfo("oracle", "oracledb", "pip install oracledb"),
    "mssql": DriverInfo("mssql", "pymssql", "pip install pymssql"),
}


def _parse_dsn(dsn: str) -> tuple[str, str]:
    """Extract scheme and path/params from a DSN. Returns (scheme, rest)."""
    parsed = urlparse(dsn)
    scheme = parsed.scheme.split("+")[0]
    return scheme, dsn


def _connect_sqlite(dsn: str):
    """Connect to SQLite from a DSN like sqlite:///path/to/db."""
    parsed = urlparse(dsn)
    db_path = parsed.path
    if parsed.netloc:
        db_path = parsed.netloc + db_path
    return sqlite3.connect(db_path)


def _connect_generic(module_name: str, dsn: str):
    """Connect using a generic DBAPI 2.0 driver that accepts a DSN string."""
    try:
        mod = importlib.import_module(module_name)
    except ImportError as exc:
        driver = _DRIVERS.get(urlparse(dsn).scheme.split("+")[0])
        hint = driver.install_hint if driver else "unknown"
        raise DriverNotFoundError(f"Driver '{module_name}' not found. Install it: {hint}") from exc
    return mod.connect(dsn)


class DriverRegistry:
    """Resolves DSN schemes to DBAPI 2.0 drivers and creates connections."""

    def resolve(self, scheme: str) -> DriverInfo:
        """Look up driver info by DSN scheme."""
        scheme = scheme.split("+", maxsplit=1)[0]
        if scheme not in _DRIVERS:
            raise DriverNotFoundError(f"Unknown database scheme: '{scheme}'")
        return _DRIVERS[scheme]

    def connect(self, dsn: str):
        """Create a DBAPI 2.0 connection from a DSN string."""
        scheme, _ = _parse_dsn(dsn)
        driver = self.resolve(scheme)

        if scheme == "sqlite":
            return _connect_sqlite(dsn)

        return _connect_generic(driver.module_name, dsn)
