import pytest
from pathlib import Path
from run.cao_memory import store_memory, query_memory, list_memories, get_connection


def test_sqlite_fts5_schema_and_store(tmp_path):
    db_file = tmp_path / "test_memory.sqlite"
    rowid = store_memory(
        category="bug_fix",
        summary="Fixed pyproject pythonpath",
        details="Added pythonpath=['.'] to tool.pytest.ini_options",
        file_paths="pyproject.toml",
        session_id="s1",
        db_path=db_file,
    )
    assert rowid == 1

    rowid2 = store_memory(
        category="architecture",
        summary="Hermes 50 percent context compaction",
        details="Compacts logs when turn count or token limits exceed 50 percent",
        file_paths="run/cao_compactor.py",
        session_id="s2",
        db_path=db_file,
    )
    assert rowid2 == 2


def test_query_memory_fts5(tmp_path):
    db_file = tmp_path / "test_memory.sqlite"
    store_memory(
        category="bug_fix",
        summary="Fixed PostgreSQL connection timeout in production",
        details="Adjusted pool size and idle ping settings in database.py",
        file_paths="src/database.py",
        db_path=db_file,
    )
    store_memory(
        category="architecture",
        summary="Added Redis cache layer for user auth tokens",
        details="JWT validation cached with 300s TTL",
        file_paths="src/auth.py",
        db_path=db_file,
    )

    # Search for postgres
    res = query_memory("postgres", db_path=db_file)
    assert len(res) == 1
    assert res[0]["category"] == "bug_fix"
    assert "timeout" in res[0]["summary"]

    # Search for redis
    res_redis = query_memory("redis cache", db_path=db_file)
    assert len(res_redis) == 1
    assert res_redis[0]["category"] == "architecture"

    # Search with category filter
    res_filtered = query_memory("user", category="bug_fix", db_path=db_file)
    assert len(res_filtered) == 0

    res_auth = query_memory("user", category="architecture", db_path=db_file)
    assert len(res_auth) == 1


def test_list_memories(tmp_path):
    db_file = tmp_path / "test_memory.sqlite"
    for i in range(5):
        store_memory(category="general", summary=f"Memory {i}", db_path=db_file)

    items = list_memories(limit=3, db_path=db_file)
    assert len(items) == 3
