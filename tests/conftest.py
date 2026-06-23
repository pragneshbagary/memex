"""Shared fixtures for memex tests."""

import pytest
import memex.server as server_module
import memex.cli as cli_module


@pytest.fixture
def mem_db(tmp_path, monkeypatch):
    """Point the server module at a fresh temp SQLite DB."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(server_module, "DB_PATH", db_file)
    server_module.init_db()
    return db_file


@pytest.fixture
def db_setup(tmp_path, monkeypatch):
    """Fresh DB accessible to both server functions and CLI functions."""
    db_file = tmp_path / "test.db"
    monkeypatch.setattr(server_module, "DB_PATH", db_file)
    server_module.init_db()
    monkeypatch.setattr(cli_module, "_db_path", lambda: db_file)
    return db_file


@pytest.fixture
def install_env(tmp_path, monkeypatch):
    """Redirect all install/remove config targets into tmp_path."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli_module, "GLOBAL_CONFIG", tmp_path / "claude.json")
    monkeypatch.setattr(cli_module, "GLOBAL_SETTINGS", tmp_path / ".claude" / "settings.json")
    monkeypatch.setattr(cli_module, "LOCAL_CONFIG", tmp_path / ".claude.json")
    monkeypatch.setattr(cli_module, "LOCAL_SETTINGS", tmp_path / ".claude" / "settings.json")
    git_exclude = tmp_path / ".git" / "info" / "exclude"
    git_exclude.parent.mkdir(parents=True)
    git_exclude.write_text("")
    return tmp_path
