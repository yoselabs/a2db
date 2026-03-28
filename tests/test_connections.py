from pathlib import Path

import pytest

from a2db.config import DEFAULT_CONFIG_DIR
from a2db.connections import ConnectionStore


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


def test_save_and_load_dsn_with_special_chars(config_dir: Path):
    store = ConnectionStore(config_dir)
    dsn = 'postgresql://admin:p@ss"word@localhost:5432/db'
    store.save("app", "dev", "main", dsn)
    info = store.load("app", "dev", "main")
    assert info.dsn == dsn


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


def test_delete_removes_file(config_dir: Path):
    store = ConnectionStore(config_dir)
    store.save("app", "dev", "main", "sqlite:///tmp/test.db")
    store.delete("app", "dev", "main")
    assert not (config_dir / "app-dev-main.toml").exists()


def test_delete_missing_raises(config_dir: Path):
    store = ConnectionStore(config_dir)
    with pytest.raises(FileNotFoundError):
        store.delete("nope", "nope", "nope")


def test_default_config_dir_is_path():
    assert isinstance(DEFAULT_CONFIG_DIR, Path)
    assert "a2db" in str(DEFAULT_CONFIG_DIR)
    assert "connections" in str(DEFAULT_CONFIG_DIR)
