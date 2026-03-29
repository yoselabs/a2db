"""Driver registry — resolve DSN schemes to async database connections."""

from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlparse

if TYPE_CHECKING:
    from collections.abc import Sequence


class DriverNotFoundError(Exception):
    """Raised when a database driver cannot be resolved or imported."""


class AsyncConnection(Protocol):
    """Async database connection interface."""

    async def execute(self, sql: str) -> list[tuple]: ...
    async def fetch(self, sql: str) -> tuple[list[tuple], object]: ...
    async def close(self) -> None: ...


@dataclass(frozen=True)
class DriverInfo:
    """Metadata about a database driver."""

    scheme: str
    module_name: str
    install_hint: str


# Registry of supported database schemes
_DRIVERS: dict[str, DriverInfo] = {
    "postgresql": DriverInfo("postgresql", "asyncpg", "pip install asyncpg"),
    "postgres": DriverInfo("postgres", "asyncpg", "pip install asyncpg"),
    "mysql": DriverInfo("mysql", "mysql.connector", "pip install mysql-connector-python"),
    "mariadb": DriverInfo("mariadb", "mysql.connector", "pip install mysql-connector-python"),
    "sqlite": DriverInfo("sqlite", "aiosqlite", "pip install aiosqlite"),
    "oracle": DriverInfo("oracle", "oracledb", "pip install oracledb"),
    "mssql": DriverInfo("mssql", "pymssql", "pip install pymssql"),
}


def _parse_dsn(dsn: str) -> tuple[str, str]:
    """Extract scheme and path/params from a DSN. Returns (scheme, rest)."""
    parsed = urlparse(dsn)
    scheme = parsed.scheme.split("+")[0]
    return scheme, dsn


def _parse_dsn_kwargs(dsn: str) -> dict:
    """Parse a DSN URI into keyword arguments for DBAPI connect()."""
    parsed = urlparse(dsn)
    kwargs: dict = {}
    if parsed.hostname:
        kwargs["host"] = parsed.hostname
    if parsed.port:
        kwargs["port"] = parsed.port
    if parsed.username:
        kwargs["user"] = parsed.username
    if parsed.password:
        kwargs["password"] = parsed.password
    if parsed.path and parsed.path != "/":
        kwargs["database"] = parsed.path.lstrip("/")
    return kwargs


class _AsyncSqliteConnection:
    """Async wrapper around aiosqlite."""

    def __init__(self, conn) -> None:
        self._conn = conn

    async def fetch(self, sql: str) -> tuple[list[tuple], object]:
        cursor = await self._conn.execute(sql)
        rows = await cursor.fetchall()
        description = cursor.description
        return rows, description

    async def close(self) -> None:
        await self._conn.close()


class _AsyncSyncConnection:
    """Async wrapper for sync DBAPI 2.0 drivers via asyncio.to_thread."""

    def __init__(self, conn) -> None:
        self._conn = conn

    async def fetch(self, sql: str) -> tuple[list[tuple], Sequence]:
        def _run():
            cursor = self._conn.cursor()
            cursor.execute(sql)
            return cursor.fetchall(), cursor.description

        return await asyncio.to_thread(_run)

    async def close(self) -> None:
        await asyncio.to_thread(self._conn.close)


class _AsyncPgConnection:
    """Async wrapper around asyncpg connection."""

    def __init__(self, conn) -> None:
        self._conn = conn

    async def fetch(self, sql: str) -> tuple[list[tuple], list[tuple]]:
        rows = await self._conn.fetch(sql)
        if not rows:
            return [], []
        columns = [(key, None) for key in rows[0].keys()]  # noqa: SIM118 — asyncpg Record.__iter__ yields values, not keys
        return [tuple(row.values()) for row in rows], columns

    async def close(self) -> None:
        await self._conn.close()


async def _connect_sqlite(dsn: str) -> _AsyncSqliteConnection:
    """Connect to SQLite via aiosqlite."""
    import aiosqlite  # noqa: PLC0415

    parsed = urlparse(dsn)
    db_path = parsed.path
    if parsed.netloc:
        db_path = parsed.netloc + db_path
    conn = await aiosqlite.connect(db_path)
    return _AsyncSqliteConnection(conn)


async def _connect_asyncpg(dsn: str) -> _AsyncPgConnection:
    """Connect to PostgreSQL via asyncpg."""
    try:
        import asyncpg  # noqa: PLC0415
    except ImportError as exc:
        raise DriverNotFoundError("Driver 'asyncpg' not found. Install it: pip install asyncpg") from exc
    conn = await asyncpg.connect(dsn)
    return _AsyncPgConnection(conn)


async def _connect_sync_generic(module_name: str, dsn: str) -> _AsyncSyncConnection:
    """Connect using a sync DBAPI 2.0 driver, wrapped for async."""
    try:
        mod = importlib.import_module(module_name)
    except ImportError as exc:
        driver = _DRIVERS.get(urlparse(dsn).scheme.split("+")[0])
        hint = driver.install_hint if driver else "unknown"
        raise DriverNotFoundError(f"Driver '{module_name}' not found. Install it: {hint}") from exc

    kwargs = _parse_dsn_kwargs(dsn)
    conn = await asyncio.to_thread(mod.connect, **kwargs)
    return _AsyncSyncConnection(conn)


class DriverRegistry:
    """Resolves DSN schemes to database drivers and creates async connections."""

    def resolve(self, scheme: str) -> DriverInfo:
        """Look up driver info by DSN scheme."""
        scheme = scheme.split("+", maxsplit=1)[0]
        if scheme not in _DRIVERS:
            raise DriverNotFoundError(f"Unknown database scheme: '{scheme}'")
        return _DRIVERS[scheme]

    async def connect(self, dsn: str):
        """Create an async database connection from a DSN string."""
        scheme, _ = _parse_dsn(dsn)
        self.resolve(scheme)  # validate scheme

        if scheme == "sqlite":
            return await _connect_sqlite(dsn)

        if scheme in ("postgresql", "postgres"):
            return await _connect_asyncpg(dsn)

        driver = self.resolve(scheme)
        return await _connect_sync_generic(driver.module_name, dsn)
