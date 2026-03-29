"""Schema explorer — progressive database schema discovery."""

from __future__ import annotations

from typing import TYPE_CHECKING

from a2db.drivers import DriverRegistry

if TYPE_CHECKING:
    from a2db.connections import ConnectionStore

_SUPPORTED_OBJECT_TYPES = {"table", "column"}


class SchemaExplorer:
    """Explores database schemas at varying detail levels."""

    def __init__(self, store: ConnectionStore) -> None:
        self.store = store
        self.registry = DriverRegistry()

    async def search_objects(
        self,
        connection: dict[str, str],
        object_type: str,
        pattern: str = "%",
        schema: str | None = None,  # noqa: ARG002
        table: str | None = None,
        detail_level: str = "names",
        limit: int = 100,
    ) -> dict:
        """Search database objects with progressive detail levels."""
        if object_type not in _SUPPORTED_OBJECT_TYPES:
            supported = ", ".join(sorted(_SUPPORTED_OBJECT_TYPES))
            raise ValueError(f"Unsupported object type: '{object_type}'. Supported: {supported}")

        info = self.store.load(connection["project"], connection["env"], connection["db"])
        conn = await self.registry.connect(info.resolved_dsn)

        try:
            if object_type == "table":
                results = await self._search_tables(conn, info.scheme, pattern, detail_level)
            else:
                results = await self._search_columns(conn, info.scheme, table, pattern, detail_level)
        finally:
            await conn.close()

        truncated = len(results) > limit
        if truncated:
            results = results[:limit]

        return {
            "object_type": object_type,
            "pattern": pattern,
            "detail_level": detail_level,
            "count": len(results),
            "truncated": truncated,
            "results": results,
        }

    async def _search_tables(self, conn, scheme: str, pattern: str, detail_level: str) -> list[dict]:
        """Search tables."""
        if scheme == "sqlite":
            rows, _ = await conn.fetch(
                f"SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '{pattern}' ORDER BY name"  # noqa: S608
            )
            tables = [row[0] for row in rows]
        else:
            sql = (
                f"SELECT table_name FROM information_schema.tables"  # noqa: S608
                f" WHERE table_schema = 'public' AND table_name LIKE '{pattern}' ORDER BY table_name"
            )
            rows, _ = await conn.fetch(sql)
            tables = [row[0] for row in rows]

        results = []
        for table_name in tables:
            entry: dict = {"name": table_name}

            if detail_level in ("summary", "full"):
                if scheme == "sqlite":
                    col_rows, _ = await conn.fetch(f"PRAGMA table_info('{table_name}')")
                else:
                    col_rows, _ = await conn.fetch(
                        f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table_name}'"  # noqa: S608
                    )
                entry["column_count"] = len(col_rows)

            if detail_level == "full":
                if scheme == "sqlite":
                    entry["columns"] = [{"name": col[1], "type": col[2], "nullable": not col[3], "pk": bool(col[5])} for col in col_rows]
                else:
                    entry["columns"] = [{"name": col[0], "type": col[1]} for col in col_rows]

            results.append(entry)

        return results

    async def _search_columns(self, conn, scheme: str, table: str | None, pattern: str, detail_level: str) -> list[dict]:
        """Search columns within a table."""
        if scheme == "sqlite":
            if not table:
                return []
            col_rows, _ = await conn.fetch(f"PRAGMA table_info('{table}')")
            results = []
            for col in col_rows:
                name = col[1]
                if pattern == "%" or pattern.replace("%", "") in name:
                    entry: dict = {"name": name}
                    if detail_level in ("summary", "full"):
                        entry["type"] = col[2]
                        entry["nullable"] = not col[3]
                        entry["pk"] = bool(col[5])
                    results.append(entry)
            return results

        col_rows, _ = await conn.fetch(
            f"SELECT column_name, data_type, is_nullable FROM information_schema.columns "  # noqa: S608
            f"WHERE table_name = '{table}' AND column_name LIKE '{pattern}' ORDER BY ordinal_position"
        )
        results = []
        for col in col_rows:
            entry = {"name": col[0]}
            if detail_level in ("summary", "full"):
                entry["type"] = col[1]
                entry["nullable"] = col[2] == "YES"
            results.append(entry)
        return results
