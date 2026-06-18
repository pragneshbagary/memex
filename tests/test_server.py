"""Tests for MCP tool functions in memex/server.py."""

import json
import pytest
import memex.server as srv


# ---------------------------------------------------------------------------
# mem_save
# ---------------------------------------------------------------------------

def test_mem_save_basic(mem_db):
    result = srv.mem_save(task="Did a thing")
    assert "Saved memory #1" in result


def test_mem_save_returns_incrementing_ids(mem_db):
    srv.mem_save(task="First")
    result = srv.mem_save(task="Second")
    assert "#2" in result


def test_mem_save_all_fields(mem_db):
    srv.mem_save(
        task="Replaced auth",
        files=["src/auth.py"],
        decisions=["Use sessions, not JWT"],
        warnings=["Redis required"],
        tags=["auth"],
        notes="Some extra context",
    )
    with srv.get_conn() as conn:
        row = conn.execute("SELECT * FROM entries WHERE id=1").fetchone()
    assert json.loads(row["files"]) == ["src/auth.py"]
    assert json.loads(row["decisions"]) == ["Use sessions, not JWT"]
    assert json.loads(row["warnings"]) == ["Redis required"]
    assert json.loads(row["tags"]) == ["auth"]
    assert row["raw"] == "Some extra context"


def test_mem_save_token_warning(mem_db):
    long_notes = "word " * 400
    result = srv.mem_save(task="Big entry", notes=long_notes)
    assert "long" in result.lower() or "token" in result.lower()


# ---------------------------------------------------------------------------
# mem_load
# ---------------------------------------------------------------------------

def test_mem_load_empty(mem_db):
    result = srv.mem_load()
    assert "No memories" in result


def test_mem_load_returns_recent(mem_db):
    srv.mem_save(task="First task")
    srv.mem_save(task="Second task")
    result = srv.mem_load()
    assert "First task" in result
    assert "Second task" in result


def test_mem_load_hint_finds_matching_entry(mem_db):
    srv.mem_save(task="Deployed to production xyzzy123")
    srv.mem_save(task="Wrote some docs")
    result = srv.mem_load(hint="xyzzy123")
    assert "xyzzy123" in result


def test_mem_load_files_finds_matching_entry(mem_db):
    srv.mem_save(task="Touched the auth module", files=["src/auth.py"])
    srv.mem_save(task="Unrelated work", files=["src/api.py"])
    # Load 0 recent, search by file
    import memex.server as s
    old = s.MAX_LOAD_RECENT
    s.MAX_LOAD_RECENT = 0
    try:
        result = srv.mem_load(files=["src/auth.py"])
    finally:
        s.MAX_LOAD_RECENT = old
    assert "auth" in result


def test_mem_load_no_duplicate_in_recent_and_matched(mem_db):
    srv.mem_save(task="Unique keyword zqzqzq deployed")
    result = srv.mem_load(hint="zqzqzq")
    # Should appear exactly once
    assert result.count("zqzqzq") == 1


# ---------------------------------------------------------------------------
# mem_search
# ---------------------------------------------------------------------------

def test_mem_search_finds_entry(mem_db):
    srv.mem_save(task="Set up redis caching layer")
    result = srv.mem_search("redis")
    assert "redis" in result.lower()


def test_mem_search_no_match(mem_db):
    srv.mem_save(task="Something unrelated")
    result = srv.mem_search("xyzzy_nonexistent")
    assert "No entries" in result


def test_mem_search_empty_db(mem_db):
    result = srv.mem_search("anything")
    assert "No entries" in result


def test_mem_search_empty_query(mem_db):
    srv.mem_save(task="Something")
    result = srv.mem_search("  ")
    assert "empty" in result.lower()


def test_mem_search_searches_tags(mem_db):
    srv.mem_save(task="Added login", tags=["auth", "login"])
    result = srv.mem_search("auth")
    assert "Added login" in result


def test_mem_search_searches_decisions(mem_db):
    srv.mem_save(task="Refactored API", decisions=["Use REST not GraphQL"])
    result = srv.mem_search("GraphQL")
    assert "Refactored API" in result


# ---------------------------------------------------------------------------
# mem_list
# ---------------------------------------------------------------------------

def test_mem_list_empty(mem_db):
    result = srv.mem_list()
    assert "No entries" in result


def test_mem_list_shows_all(mem_db):
    srv.mem_save(task="Alpha")
    srv.mem_save(task="Beta")
    result = srv.mem_list()
    assert "Alpha" in result
    assert "Beta" in result


def test_mem_list_filter_by_tag(mem_db):
    srv.mem_save(task="Auth work", tags=["auth"])
    srv.mem_save(task="Docs work", tags=["docs"])
    result = srv.mem_list(tag="auth")
    assert "Auth work" in result
    assert "Docs work" not in result


def test_mem_list_respects_limit(mem_db):
    for i in range(5):
        srv.mem_save(task=f"Task {i}")
    result = srv.mem_list(limit=2)
    # Each entry has one "Task      :" label line
    assert result.count("Task      :") == 2


# ---------------------------------------------------------------------------
# mem_delete
# ---------------------------------------------------------------------------

def test_mem_delete_removes_entry(mem_db):
    srv.mem_save(task="To be deleted")
    result = srv.mem_delete(1)
    assert "Deleted" in result
    assert "No entries" in srv.mem_list()


def test_mem_delete_unknown_id(mem_db):
    result = srv.mem_delete(999)
    assert "No entry" in result


def test_mem_delete_cleans_fts_index(mem_db):
    srv.mem_save(task="Unique phrase zqzqzq")
    srv.mem_delete(1)
    result = srv.mem_search("zqzqzq")
    assert "No entries" in result


# ---------------------------------------------------------------------------
# FTS trigger integrity
# ---------------------------------------------------------------------------

def test_fts_update_trigger(mem_db):
    srv.mem_save(task="Original content aaabbb")
    with srv.get_conn() as conn:
        conn.execute("UPDATE entries SET task='New content cccdd' WHERE id=1")
    result = srv.mem_search("cccdd")
    assert "New content" in result
    assert "No entries" not in result
