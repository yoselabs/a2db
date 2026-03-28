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
