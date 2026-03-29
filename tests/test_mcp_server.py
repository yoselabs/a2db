from a2db.mcp_server import _normalize_queries


def test_normalize_queries_dict_passthrough():
    queries = {
        "users": {"connection": {"project": "x", "env": "y", "db": "z"}, "sql": "SELECT 1"},
        "orders": {"connection": {"project": "x", "env": "y", "db": "z"}, "sql": "SELECT 2"},
    }
    assert _normalize_queries(queries) is queries


def test_normalize_queries_list_to_named_dict():
    queries = [
        {"connection": {"project": "x", "env": "y", "db": "z"}, "sql": "SELECT 1"},
        {"connection": {"project": "x", "env": "y", "db": "z"}, "sql": "SELECT 2"},
    ]
    result = _normalize_queries(queries)
    assert isinstance(result, dict)
    assert "q1" in result
    assert "q2" in result
    assert result["q1"]["sql"] == "SELECT 1"
    assert result["q2"]["sql"] == "SELECT 2"


def test_normalize_queries_single_list_item():
    queries = [{"connection": {"project": "x", "env": "y", "db": "z"}, "sql": "SELECT 1"}]
    result = _normalize_queries(queries)
    assert result == {"q1": queries[0]}
