"""Tests for CLI commands in memex/cli.py."""

import json
import sqlite3
import sys
from pathlib import Path

import pytest
import memex.cli as cli
import memex.server as srv


# ---------------------------------------------------------------------------
# install / remove
# ---------------------------------------------------------------------------

def test_install_writes_mcp_entry(install_env, capsys):
    cli.install()
    config = json.loads((install_env / "claude.json").read_text())
    assert "memex" in config["mcpServers"]
    entry = config["mcpServers"]["memex"]
    assert entry["type"] == "stdio"
    assert "-m" in entry["args"]
    assert "memex.server" in entry["args"]


def test_install_writes_stop_hook(install_env, capsys):
    cli.install()
    settings = json.loads((install_env / ".claude" / "settings.json").read_text())
    stop_hooks = settings["hooks"]["Stop"]
    commands = [h["command"] for entry in stop_hooks for h in entry.get("hooks", [])]
    assert any("hook-stop" in cmd for cmd in commands)


def test_install_no_hook_skips_stop_hook(install_env, capsys):
    cli.install(no_hook=True)
    settings_path = install_env / ".claude" / "settings.json"
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
        stop_hooks = settings.get("hooks", {}).get("Stop", [])
        assert stop_hooks == []
    # If settings file doesn't exist at all, that's also fine


def test_install_creates_claude_memex_md(install_env, capsys):
    cli.install()
    memex_md = install_env / ".claude" / "memex.md"
    assert memex_md.exists()
    assert "memex" in memex_md.read_text()


def test_install_does_not_touch_project_claude_md(install_env, capsys):
    # Project's own CLAUDE.md must be left untouched
    cli.install()
    assert not (install_env / "CLAUDE.md").exists()


def test_install_idempotent_memex_md(install_env, capsys):
    cli.install()
    first_content = (install_env / ".claude" / "memex.md").read_text()
    cli.install()
    second_content = (install_env / ".claude" / "memex.md").read_text()
    assert first_content == second_content


def test_install_does_not_create_gitignore(install_env, capsys):
    cli.install()
    assert not (install_env / ".gitignore").exists()


def test_remove_cleans_config(install_env, capsys):
    cli.install()
    cli.remove()
    config = json.loads((install_env / "claude.json").read_text())
    assert "memex" not in config.get("mcpServers", {})


def test_remove_cleans_stop_hook(install_env, capsys):
    cli.install()
    cli.remove()
    settings = json.loads((install_env / ".claude" / "settings.json").read_text())
    stop_hooks = settings.get("hooks", {}).get("Stop", [])
    commands = [h["command"] for entry in stop_hooks for h in entry.get("hooks", [])]
    assert not any("hook-stop" in cmd for cmd in commands)


def test_remove_deletes_memex_md(install_env, capsys):
    cli.install()
    memex_md = install_env / ".claude" / "memex.md"
    assert memex_md.exists()
    cli.remove()
    assert not memex_md.exists()


def test_remove_when_not_installed(install_env, capsys):
    cli.remove()  # Should not raise
    out = capsys.readouterr().out
    assert "not found" in out


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

def test_status_no_db(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_db_path", lambda: tmp_path / "nonexistent.db")
    cli.status()
    out = capsys.readouterr().out
    assert "memex" in out
    assert "No memories" in out


def test_status_shows_entry_count(db_setup, capsys):
    srv.mem_save(task="Task A", tags=["alpha"])
    srv.mem_save(task="Task B", tags=["alpha", "beta"])
    cli.status()
    out = capsys.readouterr().out
    assert "Entries: 2" in out
    assert "alpha" in out


def test_status_shows_db_path(db_setup, capsys):
    cli.status()
    out = capsys.readouterr().out
    assert "DB:" in out
    assert "test.db" in out


# ---------------------------------------------------------------------------
# list_entries
# ---------------------------------------------------------------------------

def test_list_empty(db_setup, capsys):
    cli.list_entries()
    out = capsys.readouterr().out
    assert "No entries" in out


def test_list_shows_entries(db_setup, capsys):
    srv.mem_save(task="Deployed to prod", tags=["deploy"])
    srv.mem_save(task="Fixed auth bug", tags=["auth"])
    cli.list_entries()
    out = capsys.readouterr().out
    assert "Deployed to prod" in out
    assert "Fixed auth bug" in out


def test_list_filter_by_tag(db_setup, capsys):
    srv.mem_save(task="Auth work", tags=["auth"])
    srv.mem_save(task="Docs work", tags=["docs"])
    cli.list_entries(tag="auth")
    out = capsys.readouterr().out
    assert "Auth work" in out
    assert "Docs work" not in out


def test_list_respects_limit(db_setup, capsys):
    for i in range(5):
        srv.mem_save(task=f"Task {i}")
    cli.list_entries(limit=2)
    out = capsys.readouterr().out
    assert out.count("Task") == 2


# ---------------------------------------------------------------------------
# list_entries --since / --until
# ---------------------------------------------------------------------------

def _insert_entry_with_timestamp(db_path, task: str, timestamp: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO entries (task, files, decisions, warnings, tags, raw, timestamp) "
        "VALUES (?, '[]', '[]', '[]', '[]', '', ?)",
        (task, timestamp),
    )
    conn.commit()
    conn.close()


def test_list_since_filters_old_entries(db_setup, capsys):
    _insert_entry_with_timestamp(db_setup, "Old task", "2026-01-01T00:00:00+00:00")
    _insert_entry_with_timestamp(db_setup, "Recent task", "2026-06-10T00:00:00+00:00")
    cli.list_entries(since="2026-06-01")
    out = capsys.readouterr().out
    assert "Recent task" in out
    assert "Old task" not in out


def test_list_until_filters_future_entries(db_setup, capsys):
    _insert_entry_with_timestamp(db_setup, "Early task", "2026-01-15T00:00:00+00:00")
    _insert_entry_with_timestamp(db_setup, "Late task", "2026-12-01T00:00:00+00:00")
    cli.list_entries(until="2026-06-01")
    out = capsys.readouterr().out
    assert "Early task" in out
    assert "Late task" not in out


def test_list_since_and_until_combined(db_setup, capsys):
    _insert_entry_with_timestamp(db_setup, "Before range", "2026-01-01T00:00:00+00:00")
    _insert_entry_with_timestamp(db_setup, "In range", "2026-06-05T00:00:00+00:00")
    _insert_entry_with_timestamp(db_setup, "After range", "2026-12-01T00:00:00+00:00")
    cli.list_entries(since="2026-06-01", until="2026-06-30")
    out = capsys.readouterr().out
    assert "In range" in out
    assert "Before range" not in out
    assert "After range" not in out


def test_list_since_relative_days(db_setup, capsys):
    from datetime import datetime, timedelta, timezone
    old_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat(timespec="seconds")
    new_ts = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    _insert_entry_with_timestamp(db_setup, "Month-old task", old_ts)
    _insert_entry_with_timestamp(db_setup, "Yesterday task", new_ts)
    cli.list_entries(since="7d")
    out = capsys.readouterr().out
    assert "Yesterday task" in out
    assert "Month-old task" not in out


def test_list_since_and_tag_combined(db_setup, capsys):
    _insert_entry_with_timestamp(db_setup, "Old auth work", "2026-01-01T00:00:00+00:00")
    srv.mem_save(task="Recent auth work", tags=["auth"])
    cli.list_entries(tag="auth", since="2026-06-01")
    out = capsys.readouterr().out
    assert "Recent auth work" in out
    assert "Old auth work" not in out


def test_parse_date_invalid_raises(db_setup):
    with pytest.raises(ValueError, match="Cannot parse date"):
        cli._parse_date("not-a-date")


def test_list_invalid_date_propagates_valueerror(db_setup):
    """list_entries is a library function: it raises; the caller handles (issue #25 review)."""
    with pytest.raises(ValueError, match="Cannot parse date"):
        cli.list_entries(since="not-a-date")
    with pytest.raises(ValueError, match="Cannot parse date"):
        cli.list_entries(until="garbage")


def test_cli_invalid_date_exits_cleanly(db_setup, monkeypatch, capsys):
    """End-to-end: `memex list` with a bad date exits cleanly via main(), no traceback (issue #25)."""
    monkeypatch.setattr(sys, "argv", ["memex", "list", "--since", "not-a-date"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    captured = capsys.readouterr()
    assert "Cannot parse date" in captured.err
    assert "Traceback" not in captured.err


# ---------------------------------------------------------------------------
# search_entries
# ---------------------------------------------------------------------------

def test_search_empty_db(db_setup, capsys):
    cli.search_entries("anything")
    out = capsys.readouterr().out
    assert "No entries" in out


def test_search_finds_match(db_setup, capsys):
    srv.mem_save(task="Set up redis for caching")
    cli.search_entries("redis")
    out = capsys.readouterr().out
    assert "redis" in out.lower()


def test_search_no_match(db_setup, capsys):
    srv.mem_save(task="Something unrelated")
    cli.search_entries("xyzzy_zqzqzq_notfound")
    out = capsys.readouterr().out
    assert "No entries" in out


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def test_export_creates_markdown_files(db_setup, tmp_path, capsys):
    srv.mem_save(task="Add rate limiting", tags=["api"], files=["src/middleware.py"])
    srv.mem_save(task="Add auth middleware", tags=["auth"], files=["src/middleware.py"])
    out_dir = tmp_path / "export"
    cli.export_entries(str(out_dir))
    md_files = list(out_dir.glob("*.md"))
    assert len(md_files) == 2


def test_export_markdown_has_frontmatter(db_setup, tmp_path, capsys):
    srv.mem_save(task="Bootstrap project", tags=["setup"])
    out_dir = tmp_path / "export"
    cli.export_entries(str(out_dir))
    content = next(out_dir.glob("*.md")).read_text()
    assert "---" in content
    assert "date:" in content


def test_export_related_entries_are_wikilinked(db_setup, tmp_path, capsys):
    # Both entries share the same file — should cross-link
    srv.mem_save(task="Add auth", tags=["auth"], files=["src/auth.py"])
    srv.mem_save(task="Fix auth bug", tags=["auth"], files=["src/auth.py"])
    out_dir = tmp_path / "export"
    cli.export_entries(str(out_dir))
    contents = [f.read_text() for f in out_dir.glob("*.md")]
    assert any("[[" in c for c in contents)


def test_export_empty_db(db_setup, tmp_path, capsys):
    cli.export_entries(str(tmp_path / "export"))
    out = capsys.readouterr().out
    assert "No entries" in out


# ---------------------------------------------------------------------------
# hook_stop
# ---------------------------------------------------------------------------

def test_hook_stop_no_transcript_exits_0(tmp_path, monkeypatch, capsys):
    payload = json.dumps({"transcript_path": ""})
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
    with pytest.raises(SystemExit) as exc:
        cli.hook_stop()
    assert exc.value.code == 0


def test_hook_stop_with_mem_save_exits_0(tmp_path, monkeypatch, capsys):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"type": "tool_use", "name": "mem_save", "id": "x"}) + "\n"
    )
    payload = json.dumps({"transcript_path": str(transcript)})
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
    with pytest.raises(SystemExit) as exc:
        cli.hook_stop()
    assert exc.value.code == 0


def test_hook_stop_without_mem_save_exits_0_and_prints_reminder(tmp_path, monkeypatch, capsys):
    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        json.dumps({"type": "tool_use", "name": "mem_load", "id": "x"}) + "\n"
    )
    payload = json.dumps({"transcript_path": str(transcript)})
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
    with pytest.raises(SystemExit) as exc:
        cli.hook_stop()
    assert exc.value.code == 0
    err = capsys.readouterr().err
    assert "mem_save" in err


def test_hook_stop_nested_mem_save_in_assistant_message(tmp_path, monkeypatch, capsys):
    transcript = tmp_path / "transcript.jsonl"
    line = json.dumps({
        "type": "message",
        "content": [{"type": "tool_use", "name": "mem_save", "id": "y"}],
    })
    transcript.write_text(line + "\n")
    payload = json.dumps({"transcript_path": str(transcript)})
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(payload))
    with pytest.raises(SystemExit) as exc:
        cli.hook_stop()
    assert exc.value.code == 0
