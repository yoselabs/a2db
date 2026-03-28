# a2db v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working CLI + MCP server that connects to databases via DBAPI 2.0, runs named batch queries with SQLGlot pagination, explores schemas, and outputs TSV/JSON.

**Architecture:** Two thin frontends (Click CLI, FastMCP MCP server) wrap a shared core. The core uses SQLGlot for dialect-aware LIMIT/OFFSET wrapping and DBAPI 2.0 drivers (user-installed) for connections. Connection metadata lives in individual TOML files under `~/.config/a2db/connections/`.

**Tech Stack:** Python 3.12+, Click, FastMCP, SQLGlot, DBAPI 2.0 (sqlite3 for testing), tomllib (stdlib)

**Spec:** `docs/superpowers/specs/2026-03-28-v1-design.md`

---

## File Structure

```
src/a2db/
├── __init__.py              # version
├── connections.py           # ConnectionStore: save/load/list connection TOML files
├── drivers.py               # DriverRegistry: DSN scheme → DBAPI driver resolution + connect
├── sql.py                   # SQLGlot wrapping: pagination, read-only validation, dialect mapping
├── executor.py              # QueryExecutor: run named batch queries, format results
├── schema.py                # SchemaExplorer: search_objects implementation
├── formatter.py             # Output formatting: TSV and JSON renderers
├── cli.py                   # Click CLI (thin wrapper)
├── mcp_server.py            # FastMCP server (thin wrapper)
├── core.py                  # DELETE — replaced by the modules above
tests/
├── __init__.py
├── conftest.py              # Shared fixtures (tmp config dir, sqlite test DB)
├── test_connections.py      # ConnectionStore tests
├── test_drivers.py          # DriverRegistry tests
├── test_sql.py              # SQLGlot wrapping tests
├── test_executor.py         # QueryExecutor tests
├── test_schema.py           # SchemaExplorer tests
├── test_formatter.py        # Formatter tests
├── test_core.py             # DELETE — replaced by module-specific tests
```

---

## Task 0: Add sqlglot dependency and shared test fixtures

**Files:**
- Modify: `pyproject.toml`
- Create: `tests/conftest.py`
- Delete: `src/a2db/core.py`
- Delete: `tests/test_core.py`

- [ ] **Step 1: Add sqlglot to dependencies and remove httpx**

In `pyproject.toml`, replace the dependencies list:

```python
dependencies = [
    "click>=8,<9",
    "mcp[cli]>=1.9,<2",
    "sqlglot>=26,<27",
]
```

Remove `httpx` — it was a scaffold placeholder and is not needed.

- [ ] **Step 2: Create shared test fixtures**

Create `tests/conftest.py`:

```python
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    """Temporary config directory for connection files."""
    d = tmp_path / "a2db" / "connections"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def sqlite_db(tmp_path: Path) -> Path:
    """Create a temporary SQLite database with test data."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, email TEXT, active INTEGER)")
    conn.execute("INSERT INTO users VALUES (1, 'Alice', 'alice@example.com', 1)")
    conn.execute("INSERT INTO users VALUES (2, 'Bob', 'bob@example.com', 1)")
    conn.execute("INSERT INTO users VALUES (3, 'Charlie', 'charlie@example.com', 0)")
    conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, user_id INTEGER, total REAL)")
    conn.execute("INSERT INTO orders VALUES (101, 1, 49.99)")
    conn.execute("INSERT INTO orders VALUES (102, 2, 129.00)")
    conn.commit()
    conn.close()
    return db_path
```

- [ ] **Step 3: Delete scaffold stubs**

Delete `src/a2db/core.py` and `tests/test_core.py` — they are placeholder stubs that will be replaced by the real modules.

- [ ] **Step 4: Run uv sync and verify**

Run: `uv sync && uv run pytest tests/ -v`

Expected: 0 tests collected (old tests deleted, new ones not yet written). No import errors.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: add sqlglot dep, test fixtures, remove scaffold stubs"
```

---

## Task 1: Connection Store

**Files:**
- Create: `src/a2db/connections.py`
- Create: `tests/test_connections.py`

- [ ] **Step 1: Write failing tests for ConnectionStore**

Create `tests/test_connections.py`:

```python
from pathlib import Path

import pytest

from a2db.connections import ConnectionInfo, ConnectionStore


def test_save_creates_toml_file(config_dir: Path):
    store = ConnectionStore(config_dir)
    store.save("myapp", "prod", "users", "postgresql://admin:secret@localhost:5432/users")
    path = config_dir / "myapp-prod-users.toml"
    assert path.exists()
    content = path.read_text()
    assert 'project = "myapp"' in content
    assert 'env = "prod"' in content
    assert 'db = "users"' in content
    assert "postgresql://admin:secret@localhost:5432/users" in content


def test_save_overwrites_existing(config_dir: Path):
    store = ConnectionStore(config_dir)
    store.save("myapp", "prod", "users", "postgresql://old@localhost/users")
    store.save("myapp", "prod", "users", "postgresql://new@localhost/users")
    info = store.load("myapp", "prod", "users")
    assert info.dsn == "postgresql://new@localhost/users"


def test_load_returns_connection_info(config_dir: Path):
    store = ConnectionStore(config_dir)
    store.save("myapp", "prod", "users", "postgresql://admin:secret@localhost:5432/users")
    info = store.load("myapp", "prod", "users")
    assert info.project == "myapp"
    assert info.env == "prod"
    assert info.db == "users"
    assert info.dsn == "postgresql://admin:secret@localhost:5432/users"


def test_load_missing_raises(config_dir: Path):
    store = ConnectionStore(config_dir)
    with pytest.raises(FileNotFoundError):
        store.load("noproject", "noenv", "nodb")


def test_list_all(config_dir: Path):
    store = ConnectionStore(config_dir)
    store.save("app1", "prod", "db1", "postgresql://localhost/db1")
    store.save("app2", "dev", "db2", "sqlite:///tmp/test.db")
    results = store.list_connections()
    assert len(results) == 2
    projects = {r.project for r in results}
    assert projects == {"app1", "app2"}


def test_list_filter_by_project(config_dir: Path):
    store = ConnectionStore(config_dir)
    store.save("app1", "prod", "db1", "postgresql://localhost/db1")
    store.save("app2", "dev", "db2", "sqlite:///tmp/test.db")
    results = store.list_connections(project="app1")
    assert len(results) == 1
    assert results[0].project == "app1"


def test_list_empty(config_dir: Path):
    store = ConnectionStore(config_dir)
    assert store.list_connections() == []


def test_connection_info_scheme(config_dir: Path):
    store = ConnectionStore(config_dir)
    store.save("app", "dev", "main", "postgresql://localhost/main")
    info = store.load("app", "dev", "main")
    assert info.scheme == "postgresql"


def test_connection_info_scheme_sqlite(config_dir: Path):
    store = ConnectionStore(config_dir)
    store.save("app", "dev", "local", "sqlite:///tmp/test.db")
    info = store.load("app", "dev", "local")
    assert info.scheme == "sqlite"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_connections.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'a2db.connections'`

- [ ] **Step 3: Implement ConnectionStore**

Create `src/a2db/connections.py`:

```python
"""Connection storage — save/load/list database connections as TOML files."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class ConnectionInfo:
    """A saved database connection."""

    project: str
    env: str
    db: str
    dsn: str

    @property
    def scheme(self) -> str:
        """Extract the DSN scheme (e.g., 'postgresql', 'sqlite')."""
        return urlparse(self.dsn).scheme.split("+")[0]


class ConnectionStore:
    """Manages connection TOML files in a config directory."""

    def __init__(self, config_dir: Path) -> None:
        self.config_dir = config_dir

    def _path(self, project: str, env: str, db: str) -> Path:
        return self.config_dir / f"{project}-{env}-{db}.toml"

    def save(self, project: str, env: str, db: str, dsn: str) -> Path:
        """Save a connection. Creates or overwrites the TOML file."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(project, env, db)
        content = (
            f'project = "{project}"\n'
            f'env = "{env}"\n'
            f'db = "{db}"\n'
            f'dsn = "{dsn}"\n'
        )
        path.write_text(content)
        return path

    def load(self, project: str, env: str, db: str) -> ConnectionInfo:
        """Load a connection by its triple. Raises FileNotFoundError if missing."""
        path = self._path(project, env, db)
        if not path.exists():
            raise FileNotFoundError(f"Connection not found: {project}/{env}/{db}")
        data = tomllib.loads(path.read_text())
        return ConnectionInfo(
            project=data["project"],
            env=data["env"],
            db=data["db"],
            dsn=data["dsn"],
        )

    def list_connections(self, project: str | None = None) -> list[ConnectionInfo]:
        """List all saved connections, optionally filtered by project."""
        if not self.config_dir.exists():
            return []
        results = []
        for path in sorted(self.config_dir.glob("*.toml")):
            data = tomllib.loads(path.read_text())
            info = ConnectionInfo(
                project=data["project"],
                env=data["env"],
                db=data["db"],
                dsn=data["dsn"],
            )
            if project is None or info.project == project:
                results.append(info)
        return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_connections.py -v`

Expected: all 9 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/a2db/connections.py tests/test_connections.py
git commit -m "feat: add ConnectionStore — save/load/list connection TOML files"
```

---

## Task 2: Driver Registry

**Files:**
- Create: `src/a2db/drivers.py`
- Create: `tests/test_drivers.py`

- [ ] **Step 1: Write failing tests for DriverRegistry**

Create `tests/test_drivers.py`:

```python
from pathlib import Path

import pytest

from a2db.drivers import DriverRegistry, DriverNotFoundError


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


def test_all_schemes_have_install_hints():
    reg = DriverRegistry()
    for scheme in ["postgresql", "mysql", "mariadb", "sqlite", "oracle", "mssql"]:
        driver = reg.resolve(scheme)
        assert driver.install_hint, f"Missing install hint for {scheme}"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_drivers.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'a2db.drivers'`

- [ ] **Step 3: Implement DriverRegistry**

Create `src/a2db/drivers.py`:

```python
"""Driver registry — resolve DSN schemes to DBAPI 2.0 drivers."""

from __future__ import annotations

import importlib
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
    import sqlite3

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
        raise DriverNotFoundError(
            f"Driver '{module_name}' not found. Install it: {hint}"
        ) from exc
    return mod.connect(dsn)


class DriverRegistry:
    """Resolves DSN schemes to DBAPI 2.0 drivers and creates connections."""

    def resolve(self, scheme: str) -> DriverInfo:
        """Look up driver info by DSN scheme."""
        scheme = scheme.split("+")[0]
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_drivers.py -v`

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/a2db/drivers.py tests/test_drivers.py
git commit -m "feat: add DriverRegistry — DSN scheme to DBAPI 2.0 driver resolution"
```

---

## Task 3: SQL Wrapping (SQLGlot pagination + read-only validation)

**Files:**
- Create: `src/a2db/sql.py`
- Create: `tests/test_sql.py`

- [ ] **Step 1: Write failing tests for SQL wrapping**

Create `tests/test_sql.py`:

```python
import pytest

from a2db.sql import wrap_with_pagination, validate_read_only, ReadOnlyViolationError, DSN_TO_DIALECT


def test_wrap_simple_select():
    result = wrap_with_pagination("SELECT * FROM users", limit=10, offset=0, dialect="sqlite")
    assert "LIMIT 10" in result.upper()
    assert "OFFSET 0" in result.upper()


def test_wrap_with_offset():
    result = wrap_with_pagination("SELECT * FROM users", limit=50, offset=100, dialect="sqlite")
    assert "LIMIT 50" in result.upper()
    assert "OFFSET 100" in result.upper()


def test_wrap_preserves_original_query():
    result = wrap_with_pagination("SELECT name FROM users WHERE active = 1", limit=10, offset=0, dialect="sqlite")
    assert "users" in result.lower()
    assert "active" in result.lower()


def test_wrap_caps_at_max_rows():
    result = wrap_with_pagination("SELECT * FROM users", limit=50000, offset=0, dialect="sqlite")
    assert "LIMIT 10000" in result.upper()


def test_wrap_default_limit():
    result = wrap_with_pagination("SELECT * FROM users", dialect="sqlite")
    assert "LIMIT 100" in result.upper()


def test_validate_read_only_select():
    validate_read_only("SELECT * FROM users")


def test_validate_read_only_with_cte():
    validate_read_only("WITH active AS (SELECT * FROM users WHERE active = 1) SELECT * FROM active")


def test_validate_read_only_explain():
    validate_read_only("EXPLAIN SELECT * FROM users")


def test_validate_read_only_rejects_insert():
    with pytest.raises(ReadOnlyViolationError, match="INSERT"):
        validate_read_only("INSERT INTO users VALUES (1, 'test', 'test@test.com', 1)")


def test_validate_read_only_rejects_update():
    with pytest.raises(ReadOnlyViolationError, match="UPDATE"):
        validate_read_only("UPDATE users SET name = 'test'")


def test_validate_read_only_rejects_delete():
    with pytest.raises(ReadOnlyViolationError, match="DELETE"):
        validate_read_only("DELETE FROM users")


def test_validate_read_only_rejects_drop():
    with pytest.raises(ReadOnlyViolationError, match="DROP"):
        validate_read_only("DROP TABLE users")


def test_validate_read_only_rejects_truncate():
    with pytest.raises(ReadOnlyViolationError, match="TRUNCATE"):
        validate_read_only("TRUNCATE TABLE users")


def test_validate_read_only_rejects_alter():
    with pytest.raises(ReadOnlyViolationError, match="ALTER"):
        validate_read_only("ALTER TABLE users ADD COLUMN age INTEGER")


def test_dsn_to_dialect_mapping():
    assert DSN_TO_DIALECT["postgresql"] == "postgres"
    assert DSN_TO_DIALECT["mysql"] == "mysql"
    assert DSN_TO_DIALECT["sqlite"] == "sqlite"
    assert DSN_TO_DIALECT["mssql"] == "tsql"
    assert DSN_TO_DIALECT["oracle"] == "oracle"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_sql.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'a2db.sql'`

- [ ] **Step 3: Implement SQL wrapping**

Create `src/a2db/sql.py`:

```python
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

    wrapped = f"SELECT * FROM ({sql}) AS _q LIMIT {limit} OFFSET {offset}"
    transpiled = sqlglot.transpile(wrapped, read=sqlglot_dialect, write=sqlglot_dialect)
    return transpiled[0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_sql.py -v`

Expected: all 16 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/a2db/sql.py tests/test_sql.py
git commit -m "feat: add SQL wrapping — SQLGlot pagination + read-only validation"
```

---

## Task 4: Output Formatter (TSV + JSON)

**Files:**
- Create: `src/a2db/formatter.py`
- Create: `tests/test_formatter.py`

- [ ] **Step 1: Write failing tests for formatters**

Create `tests/test_formatter.py`:

```python
import json

from a2db.formatter import QueryResult, format_results


def _make_result(name: str, columns: list[str], rows: list[list], truncated: bool = False) -> QueryResult:
    return QueryResult(name=name, columns=columns, rows=rows, count=len(rows), truncated=truncated)


def test_format_tsv_single_query():
    result = _make_result("users", ["id", "name"], [[1, "Alice"], [2, "Bob"]])
    output = format_results({"users": result}, fmt="tsv")
    lines = output.strip().split("\n")
    assert lines[0] == "query: users"
    assert lines[1] == "id\tname"
    assert lines[2] == "1\tAlice"
    assert lines[3] == "2\tBob"
    assert lines[4] == "rows: 2, truncated: false"


def test_format_tsv_multiple_queries():
    r1 = _make_result("users", ["id", "name"], [[1, "Alice"]])
    r2 = _make_result("orders", ["id", "total"], [[101, 49.99]])
    output = format_results({"users": r1, "orders": r2}, fmt="tsv")
    assert "query: users" in output
    assert "query: orders" in output


def test_format_tsv_truncated():
    result = _make_result("users", ["id"], [[1]], truncated=True)
    output = format_results({"users": result}, fmt="tsv")
    assert "truncated: true" in output


def test_format_json_single_query():
    result = _make_result("users", ["id", "name"], [[1, "Alice"], [2, "Bob"]])
    output = format_results({"users": result}, fmt="json")
    data = json.loads(output)
    assert "users" in data
    assert data["users"]["columns"] == ["id", "name"]
    assert data["users"]["rows"] == [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    assert data["users"]["count"] == 2
    assert data["users"]["truncated"] is False


def test_format_json_multiple_queries():
    r1 = _make_result("users", ["id"], [[1]])
    r2 = _make_result("orders", ["id"], [[101]])
    output = format_results({"users": r1, "orders": r2}, fmt="json")
    data = json.loads(output)
    assert "users" in data
    assert "orders" in data


def test_format_tsv_none_value():
    result = _make_result("users", ["id", "name"], [[1, None]])
    output = format_results({"users": result}, fmt="tsv")
    assert "1\tNULL" in output


def test_format_tsv_long_field_truncated():
    long_text = "x" * 3000
    result = _make_result("data", ["content"], [[long_text]])
    output = format_results({"data": result}, fmt="tsv")
    assert "... [truncated]" in output
    assert len(output) < 3000


def test_format_json_long_field_truncated():
    long_text = "x" * 3000
    result = _make_result("data", ["content"], [[long_text]])
    output = format_results({"data": result}, fmt="json")
    data = json.loads(output)
    assert "... [truncated]" in data["data"]["rows"][0]["content"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_formatter.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'a2db.formatter'`

- [ ] **Step 3: Implement formatters**

Create `src/a2db/formatter.py`:

```python
"""Output formatting — TSV and JSON renderers for query results."""

from __future__ import annotations

import json
from dataclasses import dataclass

FIELD_MAX_LENGTH = 2000


@dataclass
class QueryResult:
    """Result of a single named query."""

    name: str
    columns: list[str]
    rows: list[list]
    count: int
    truncated: bool


def _truncate_field(value: object) -> str:
    """Truncate a field value to FIELD_MAX_LENGTH chars."""
    if value is None:
        return "NULL"
    text = str(value)
    if len(text) <= FIELD_MAX_LENGTH:
        return text
    return text[:FIELD_MAX_LENGTH] + "... [truncated]"


def _format_tsv(results: dict[str, QueryResult]) -> str:
    """Format results as TSV with query headers."""
    parts = []
    for name, result in results.items():
        lines = [f"query: {name}"]
        lines.append("\t".join(result.columns))
        for row in result.rows:
            lines.append("\t".join(_truncate_field(v) for v in row))
        truncated_str = "true" if result.truncated else "false"
        lines.append(f"rows: {result.count}, truncated: {truncated_str}")
        parts.append("\n".join(lines))
    return "\n\n".join(parts) + "\n"


def _format_json(results: dict[str, QueryResult]) -> str:
    """Format results as JSON."""
    output = {}
    for name, result in results.items():
        rows_as_dicts = []
        for row in result.rows:
            row_dict = {}
            for col, val in zip(result.columns, row):
                if isinstance(val, str) and len(val) > FIELD_MAX_LENGTH:
                    val = val[:FIELD_MAX_LENGTH] + "... [truncated]"
                row_dict[col] = val
            rows_as_dicts.append(row_dict)
        output[name] = {
            "columns": result.columns,
            "rows": rows_as_dicts,
            "count": result.count,
            "truncated": result.truncated,
        }
    return json.dumps(output, indent=2, default=str)


def format_results(results: dict[str, QueryResult], fmt: str = "tsv") -> str:
    """Format query results in the specified format."""
    if fmt == "json":
        return _format_json(results)
    return _format_tsv(results)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_formatter.py -v`

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/a2db/formatter.py tests/test_formatter.py
git commit -m "feat: add formatter — TSV and JSON output for query results"
```

---

## Task 5: Query Executor

**Files:**
- Create: `src/a2db/executor.py`
- Create: `tests/test_executor.py`

- [ ] **Step 1: Write failing tests for QueryExecutor**

Create `tests/test_executor.py`:

```python
from pathlib import Path

import pytest

from a2db.connections import ConnectionStore
from a2db.executor import QueryExecutor
from a2db.formatter import QueryResult
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_executor.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'a2db.executor'`

- [ ] **Step 3: Implement QueryExecutor**

Create `src/a2db/executor.py`:

```python
"""Query executor — run named batch queries against database connections."""

from __future__ import annotations

from a2db.connections import ConnectionStore
from a2db.drivers import DriverRegistry
from a2db.formatter import QueryResult
from a2db.sql import DSN_TO_DIALECT, validate_read_only, wrap_with_pagination


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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_executor.py -v`

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/a2db/executor.py tests/test_executor.py
git commit -m "feat: add QueryExecutor — named batch queries with pagination"
```

---

## Task 6: Schema Explorer

**Files:**
- Create: `src/a2db/schema.py`
- Create: `tests/test_schema.py`

- [ ] **Step 1: Write failing tests for SchemaExplorer**

Create `tests/test_schema.py`:

```python
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


def test_result_metadata(explorer: SchemaExplorer):
    result = explorer.search_objects(
        connection=_conn_spec(),
        object_type="table",
        detail_level="names",
    )
    assert result["object_type"] == "table"
    assert result["detail_level"] == "names"
    assert "count" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_schema.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'a2db.schema'`

- [ ] **Step 3: Implement SchemaExplorer**

Create `src/a2db/schema.py`:

```python
"""Schema explorer — progressive database schema discovery."""

from __future__ import annotations

from a2db.connections import ConnectionStore
from a2db.drivers import DriverRegistry


class SchemaExplorer:
    """Explores database schemas at varying detail levels."""

    def __init__(self, store: ConnectionStore) -> None:
        self.store = store
        self.registry = DriverRegistry()

    def search_objects(
        self,
        connection: dict[str, str],
        object_type: str,
        pattern: str = "%",
        schema: str | None = None,
        table: str | None = None,
        detail_level: str = "names",
        limit: int = 100,
    ) -> dict:
        """Search database objects with progressive detail levels."""
        info = self.store.load(connection["project"], connection["env"], connection["db"])
        conn = self.registry.connect(info.dsn)

        try:
            if object_type == "table":
                results = self._search_tables(conn, info.scheme, pattern, detail_level)
            elif object_type == "column":
                results = self._search_columns(conn, info.scheme, table, pattern, detail_level)
            else:
                results = []
        finally:
            conn.close()

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

    def _search_tables(self, conn, scheme: str, pattern: str, detail_level: str) -> list[dict]:
        """Search tables using SQLite-compatible queries."""
        cursor = conn.cursor()

        if scheme == "sqlite":
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ? ORDER BY name",
                (pattern,),
            )
        else:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name LIKE %s ORDER BY table_name",
                (pattern,),
            )

        tables = [row[0] for row in cursor.fetchall()]
        results = []

        for table_name in tables:
            entry: dict = {"name": table_name}

            if detail_level in ("summary", "full"):
                cursor.execute(f"PRAGMA table_info('{table_name}')" if scheme == "sqlite" else f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table_name}'")  # noqa: S608
                columns_info = cursor.fetchall()
                entry["column_count"] = len(columns_info)

            if detail_level == "full":
                if scheme == "sqlite":
                    entry["columns"] = [
                        {"name": col[1], "type": col[2], "nullable": not col[3], "pk": bool(col[5])}
                        for col in columns_info
                    ]
                else:
                    entry["columns"] = [
                        {"name": col[0], "type": col[1]}
                        for col in columns_info
                    ]

            results.append(entry)

        return results

    def _search_columns(self, conn, scheme: str, table: str | None, pattern: str, detail_level: str) -> list[dict]:
        """Search columns within a table."""
        cursor = conn.cursor()

        if scheme == "sqlite":
            if table:
                cursor.execute(f"PRAGMA table_info('{table}')")  # noqa: S608
            else:
                return []
            columns = cursor.fetchall()
            results = []
            for col in columns:
                name = col[1]
                if pattern == "%" or pattern.replace("%", "") in name:
                    entry: dict = {"name": name}
                    if detail_level in ("summary", "full"):
                        entry["type"] = col[2]
                        entry["nullable"] = not col[3]
                        entry["pk"] = bool(col[5])
                    results.append(entry)
            return results

        cursor.execute(
            "SELECT column_name, data_type, is_nullable "
            "FROM information_schema.columns "
            "WHERE table_name = %s AND column_name LIKE %s "
            "ORDER BY ordinal_position",
            (table, pattern),
        )
        results = []
        for col in cursor.fetchall():
            entry = {"name": col[0]}
            if detail_level in ("summary", "full"):
                entry["type"] = col[1]
                entry["nullable"] = col[2] == "YES"
            results.append(entry)
        return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_schema.py -v`

Expected: all 7 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/a2db/schema.py tests/test_schema.py
git commit -m "feat: add SchemaExplorer — progressive schema discovery"
```

---

## Task 7: CLI Frontend

**Files:**
- Modify: `src/a2db/cli.py`

- [ ] **Step 1: Rewrite CLI with all commands**

Replace `src/a2db/cli.py` with:

```python
"""CLI frontend — thin wrapper around a2db core."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from a2db import __version__
from a2db.connections import ConnectionStore
from a2db.executor import QueryExecutor
from a2db.formatter import format_results
from a2db.schema import SchemaExplorer

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "a2db" / "connections"


def _store() -> ConnectionStore:
    return ConnectionStore(DEFAULT_CONFIG_DIR)


@click.group(invoke_without_command=True)
@click.version_option(__version__, package_name="a2db")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """a2db — Agent-to-Database. Query databases from CLI or MCP."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.option("-p", "--project", required=True, help="Project name")
@click.option("-e", "--env", required=True, help="Environment")
@click.option("-d", "--db", required=True, help="Database name")
@click.argument("dsn")
def login(project: str, env: str, db: str, dsn: str) -> None:
    """Save a database connection."""
    store = _store()
    path = store.save(project, env, db, dsn)
    click.echo(f"Connection saved: {path}")


@cli.command()
@click.option("-p", "--project", default=None, help="Filter by project")
def connections(project: str | None) -> None:
    """List saved connections."""
    store = _store()
    results = store.list_connections(project=project)
    if not results:
        click.echo("No connections found.")
        return
    for info in results:
        click.echo(f"{info.project}/{info.env}/{info.db} ({info.scheme})")


@cli.command()
@click.option("-p", "--project", required=True, help="Project name")
@click.option("-e", "--env", required=True, help="Environment")
@click.option("-d", "--db", required=True, help="Database name")
@click.option("-f", "--format", "fmt", default="tsv", type=click.Choice(["tsv", "json"]), help="Output format")
@click.option("-l", "--limit", default=100, help="Max rows per query")
@click.option("-o", "--offset", default=0, help="Row offset")
@click.option("--batch", "batch_file", type=click.Path(exists=True), help="JSON file with named queries")
@click.argument("sql", required=False)
def query(project: str, env: str, db: str, fmt: str, limit: int, offset: int, batch_file: str | None, sql: str | None) -> None:
    """Execute SQL queries."""
    store = _store()
    executor = QueryExecutor(store)

    if batch_file:
        queries = json.loads(Path(batch_file).read_text())["queries"]
    elif sql:
        queries = {
            "result": {
                "connection": {"project": project, "env": env, "db": db},
                "sql": sql,
            }
        }
    else:
        click.echo("Error: provide SQL argument or --batch file", err=True)
        sys.exit(1)

    results = executor.execute(queries, limit=limit, offset=offset)
    click.echo(format_results(results, fmt=fmt))


@cli.command()
@click.option("-p", "--project", required=True, help="Project name")
@click.option("-e", "--env", required=True, help="Environment")
@click.option("-d", "--db", required=True, help="Database name")
@click.argument("object_type", type=click.Choice(["tables", "columns", "full"]))
@click.option("-t", "--table", default=None, help="Table name (for columns)")
@click.option("--pattern", default="%", help="SQL LIKE pattern")
@click.option("-f", "--format", "fmt", default="tsv", type=click.Choice(["tsv", "json"]), help="Output format")
def schema(project: str, env: str, db: str, object_type: str, table: str | None, pattern: str, fmt: str) -> None:
    """Explore database schema."""
    explorer = SchemaExplorer(_store())
    conn_spec = {"project": project, "env": env, "db": db}

    detail_level = "full" if object_type == "full" else "names"
    obj_type = "column" if object_type == "columns" else "table"

    result = explorer.search_objects(
        connection=conn_spec,
        object_type=obj_type,
        pattern=pattern,
        table=table,
        detail_level=detail_level,
    )

    if fmt == "json":
        click.echo(json.dumps(result, indent=2))
    else:
        for entry in result["results"]:
            if detail_level == "full" and "columns" in entry:
                click.echo(f"\n{entry['name']}:")
                for col in entry["columns"]:
                    parts = [f"  {col['name']} {col.get('type', '')}"]
                    if col.get("pk"):
                        parts.append("PK")
                    click.echo(" ".join(parts))
            else:
                click.echo(entry["name"])
```

- [ ] **Step 2: Verify lint passes**

Run: `make lint`

Expected: all checks PASS.

- [ ] **Step 3: Commit**

```bash
git add src/a2db/cli.py
git commit -m "feat: rewrite CLI — login, connections, query, schema commands"
```

---

## Task 8: MCP Server Frontend

**Files:**
- Modify: `src/a2db/mcp_server.py`

- [ ] **Step 1: Rewrite MCP server with all tools**

Replace `src/a2db/mcp_server.py` with:

```python
"""MCP server frontend — thin wrapper around a2db core."""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from a2db.connections import ConnectionStore
from a2db.executor import QueryExecutor
from a2db.formatter import format_results
from a2db.schema import SchemaExplorer

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "a2db" / "connections"

server = FastMCP(
    "a2db",
    instructions=(
        "Agent-to-Database — query and explore databases. "
        "Connections are identified by (project, env, db) triple. "
        "Use 'login' to save a connection, then 'execute' to run queries. "
        "Always include LIMIT in your queries or use the limit parameter. "
        "Default output is TSV for token efficiency."
    ),
)


def _store() -> ConnectionStore:
    return ConnectionStore(DEFAULT_CONFIG_DIR)


@server.tool()
def login(project: str, env: str, db: str, dsn: str) -> str:
    """Save a database connection. The (project, env, db) triple is the unique key."""
    store = _store()
    path = store.save(project, env, db, dsn)
    return f"Connection saved: {path}"


@server.tool()
def list_connections(project: str | None = None) -> str:
    """List saved connections. Returns project/env/db and database type (no secrets)."""
    store = _store()
    results = store.list_connections(project=project)
    if not results:
        return "No connections found."
    lines = [f"{r.project}/{r.env}/{r.db} ({r.scheme})" for r in results]
    return "\n".join(lines)


@server.tool()
def execute(
    queries: dict[str, dict],
    format: str = "tsv",
    limit: int = 100,
    offset: int = 0,
) -> str:
    """Execute named SQL queries. Each query specifies its connection and SQL.

    Example queries parameter:
    {
        "active_users": {
            "connection": {"project": "myapp", "env": "prod", "db": "users"},
            "sql": "SELECT id, name FROM users WHERE active = true"
        }
    }

    Returns results in TSV (default) or JSON format.
    """
    store = _store()
    executor = QueryExecutor(store)
    results = executor.execute(queries, limit=limit, offset=offset)
    return format_results(results, fmt=format)


@server.tool()
def search_objects(
    connection: dict[str, str],
    object_type: str,
    pattern: str = "%",
    schema: str | None = None,
    table: str | None = None,
    detail_level: str = "names",
    limit: int = 100,
) -> str:
    """Search database objects (tables, columns, indexes, etc.).

    object_type: schema, table, column, index, procedure, function
    detail_level: names (minimal), summary (with metadata), full (complete structure)
    """
    explorer = SchemaExplorer(_store())
    result = explorer.search_objects(
        connection=connection,
        object_type=object_type,
        pattern=pattern,
        schema=schema,
        table=table,
        detail_level=detail_level,
        limit=limit,
    )
    return json.dumps(result, indent=2)
```

- [ ] **Step 2: Verify lint passes**

Run: `make lint`

Expected: all checks PASS.

- [ ] **Step 3: Commit**

```bash
git add src/a2db/mcp_server.py
git commit -m "feat: rewrite MCP server — login, list_connections, execute, search_objects"
```

---

## Task 9: Update pyproject.toml and coverage config

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Update coverage omit list**

In `pyproject.toml`, the coverage omit already has `cli.py` and `mcp_server.py`. Verify the config dir env var for tests:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --strict-markers --cov --cov-report=term:skip-covered --cov-report=xml --cov-fail-under=80"
env = [
    "A2DB_TEST=1",
    "A2DB_CONFIG_DIR={tmp_path}/a2db-test",
]
```

Remove `A2DB_CONFIG_DIR` from env (tests use `config_dir` fixture with `tmp_path`, no global env needed). Keep `A2DB_TEST=1`.

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest tests/ -v`

Expected: all tests pass across all test files. Coverage >= 80%.

- [ ] **Step 3: Run full lint**

Run: `make lint`

Expected: all checks PASS.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore: update coverage config for new module structure"
```

---

## Task 10: Update README and CLAUDE.md

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update README**

Rewrite `README.md` with accurate usage examples reflecting the real CLI and MCP interfaces:

```markdown
# a2db

Agent-to-Database — query databases from CLI or as an MCP server.

## Install

```bash
pip install a2db
```

Install the database driver you need:

```bash
pip install psycopg2-binary   # PostgreSQL
pip install mysql-connector-python  # MySQL
# SQLite is built-in
```

## CLI Usage

```bash
# Save a connection
a2db login -p myapp -e prod -d users "postgresql://user:pass@localhost/mydb"

# List connections
a2db connections

# Run a query
a2db query -p myapp -e prod -d users "SELECT * FROM users LIMIT 10"

# JSON output
a2db query -p myapp -e prod -d users -f json "SELECT * FROM users LIMIT 10"

# Explore schema
a2db schema -p myapp -e prod -d users tables
a2db schema -p myapp -e prod -d users columns -t users
a2db schema -p myapp -e prod -d users full
```

## MCP Usage

Add to your MCP client configuration:

```json
{
  "mcpServers": {
    "a2db": {
      "command": "uvx",
      "args": ["a2db-mcp"]
    }
  }
}
```

## Development

```bash
make bootstrap   # Install deps
make check       # Lint + test
```

## License

MIT
```

- [ ] **Step 2: Update CLAUDE.md architecture section**

Update the Architecture section in `CLAUDE.md` to reflect the real file structure:

```markdown
## Architecture

- `src/a2db/connections.py` — ConnectionStore: save/load/list connection TOML files
- `src/a2db/drivers.py` — DriverRegistry: DSN scheme → DBAPI 2.0 driver resolution
- `src/a2db/sql.py` — SQLGlot wrapping: pagination, read-only validation
- `src/a2db/executor.py` — QueryExecutor: named batch queries with pagination
- `src/a2db/schema.py` — SchemaExplorer: progressive schema discovery
- `src/a2db/formatter.py` — Output formatting: TSV and JSON renderers
- `src/a2db/cli.py` — Click CLI frontend (thin wrapper)
- `src/a2db/mcp_server.py` — MCP server frontend (thin wrapper)
```

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: update README and CLAUDE.md for v1 architecture"
```

---

## Task 11: Integration smoke test and push

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`

Expected: all tests PASS, coverage >= 80%.

- [ ] **Step 2: Run full lint**

Run: `make lint`

Expected: all 10 checks PASS.

- [ ] **Step 3: Manual smoke test with SQLite**

```bash
# Login
a2db login -p test -e dev -d local "sqlite:///tmp/a2db-smoke.db"

# Create test data
python3 -c "
import sqlite3
conn = sqlite3.connect('/tmp/a2db-smoke.db')
conn.execute('CREATE TABLE IF NOT EXISTS items (id INTEGER, name TEXT)')
conn.execute('INSERT INTO items VALUES (1, \"hello\")')
conn.commit()
conn.close()
"

# Query
a2db query -p test -e dev -d local "SELECT * FROM items"

# Schema
a2db schema -p test -e dev -d local tables

# List connections
a2db connections
```

Expected: each command produces output without errors.

- [ ] **Step 4: Push all commits**

```bash
git push
```
