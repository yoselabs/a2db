from unittest import mock

import pytest

from a2db.sql import DSN_TO_DIALECT, ReadOnlyViolationError, SQLParseError, validate_read_only, wrap_with_pagination


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


def test_validate_read_only_rejects_comment_bypass():
    with pytest.raises(ReadOnlyViolationError):
        validate_read_only("/* harmless */ DELETE FROM users")


def test_validate_read_only_rejects_multi_statement():
    with pytest.raises(ReadOnlyViolationError):
        validate_read_only("SELECT 1; DROP TABLE users")


def test_validate_read_only_rejects_create():
    with pytest.raises(ReadOnlyViolationError):
        validate_read_only("CREATE TABLE evil (id INTEGER)")


def test_dsn_to_dialect_mapping():
    assert DSN_TO_DIALECT["postgresql"] == "postgres"
    assert DSN_TO_DIALECT["mysql"] == "mysql"
    assert DSN_TO_DIALECT["sqlite"] == "sqlite"
    assert DSN_TO_DIALECT["mssql"] == "tsql"
    assert DSN_TO_DIALECT["oracle"] == "oracle"


def test_wrap_raises_sql_parse_error_on_invalid_sql():
    with pytest.raises(SQLParseError, match="Failed to parse SQL"):
        wrap_with_pagination("SELECT )()()()(", dialect="sqlite")


def test_validate_read_only_empty_query_raises():
    with pytest.raises(ReadOnlyViolationError, match="Empty query"):
        validate_read_only("")


def test_validate_read_only_whitespace_only_raises():
    with pytest.raises(ReadOnlyViolationError, match="Empty query"):
        validate_read_only("   ;  ")


def test_validate_read_only_pragma():
    """PRAGMA parsed as Command is allowed; but SQLite PRAGMA may parse differently — just verify SHOW works."""
    # SHOW is the reliable Command path; PRAGMA behavior is dialect-specific
    validate_read_only("SHOW DATABASES")


def test_validate_read_only_show():
    """SHOW is a Command type that should be allowed."""
    validate_read_only("SHOW TABLES")


def test_validate_read_only_fallback_keyword_check():
    """When SQLGlot raises ParseError, fall back to keyword check — forbidden keyword raises."""
    import sqlglot.errors

    with mock.patch("sqlglot.parse", side_effect=sqlglot.errors.ParseError("bad")), pytest.raises(ReadOnlyViolationError, match="INSERT"):
        validate_read_only("INSERT INTO t VALUES (1)")


def test_validate_read_only_fallback_allows_select():
    """When SQLGlot raises ParseError, fall back to keyword check — SELECT is allowed."""
    import sqlglot.errors

    with mock.patch("sqlglot.parse", side_effect=sqlglot.errors.ParseError("bad")):
        validate_read_only("SELECT * FROM t")  # should not raise
