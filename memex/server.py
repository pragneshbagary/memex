#!/usr/bin/env python3
"""
memex: Persistent session memory for Claude Code.
No LLMs, no embeddings — just SQLite + FTS5 + structured entries.

Tools exposed via MCP:
  mem_save   — save a session entry (task, decisions, warnings, files, tags)
  mem_load   — retrieve relevant entries for a new session
  mem_search — free-text search across all entries
  mem_list   — list recent entries (for inspection / housekeeping)
  mem_delete — remove an entry by id
"""

import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DB_DIR = Path(os.environ.get("MEMEX_DIR", Path.home() / ".memex"))
DB_DIR.mkdir(parents=True, exist_ok=True)

# By default, memory is scoped per-project using the CWD at server startup.
# Set MEMEX_GLOBAL=1 to share one DB across all projects.
_global = os.environ.get("MEMEX_GLOBAL", "0") == "1"
if _global:
    DB_PATH = DB_DIR / "global.db"
else:
    cwd = os.environ.get("MEMEX_PROJECT", os.getcwd())
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", cwd).strip("_")[:120]
    DB_PATH = DB_DIR / f"{safe}.db"

MAX_LOAD_RECENT = int(os.environ.get("MEMEX_RECENT", "5"))
MAX_LOAD_MATCHED = int(os.environ.get("MEMEX_MATCHED", "5"))

# ---------------------------------------------------------------------------
# DB setup
# ---------------------------------------------------------------------------

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS entries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project     TEXT    NOT NULL DEFAULT '',
                timestamp   TEXT    NOT NULL,
                task        TEXT    NOT NULL,
                files       TEXT    NOT NULL DEFAULT '[]',
                decisions   TEXT    NOT NULL DEFAULT '[]',
                warnings    TEXT    NOT NULL DEFAULT '[]',
                tags        TEXT    NOT NULL DEFAULT '[]',
                raw         TEXT    NOT NULL DEFAULT ''
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
                task,
                files,
                decisions,
                warnings,
                tags,
                raw,
                content='entries',
                content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS entries_ai AFTER INSERT ON entries BEGIN
                INSERT INTO entries_fts(rowid, task, files, decisions, warnings, tags, raw)
                VALUES (new.id, new.task, new.files, new.decisions, new.warnings, new.tags, new.raw);
            END;

            CREATE TRIGGER IF NOT EXISTS entries_ad AFTER DELETE ON entries BEGIN
                INSERT INTO entries_fts(entries_fts, rowid, task, files, decisions, warnings, tags, raw)
                VALUES ('delete', old.id, old.task, old.files, old.decisions, old.warnings, old.tags, old.raw);
            END;

            CREATE TRIGGER IF NOT EXISTS entries_au AFTER UPDATE ON entries BEGIN
                INSERT INTO entries_fts(entries_fts, rowid, task, files, decisions, warnings, tags, raw)
                VALUES ('delete', old.id, old.task, old.files, old.decisions, old.warnings, old.tags, old.raw);
                INSERT INTO entries_fts(rowid, task, files, decisions, warnings, tags, raw)
                VALUES (new.id, new.task, new.files, new.decisions, new.warnings, new.tags, new.raw);
            END;
        """)
        # Migrate existing DBs with old column names
        cols = {row[1] for row in conn.execute("PRAGMA table_info(entries)")}
        if "gotchas" in cols:
            conn.execute("ALTER TABLE entries RENAME COLUMN gotchas TO warnings")


init_db()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    for field in ("files", "decisions", "warnings", "tags"):
        try:
            d[field] = json.loads(d[field])
        except (json.JSONDecodeError, TypeError):
            d[field] = []
    return d


def _format_entry(e: dict, idx: Optional[int] = None) -> str:
    prefix = f"[{idx}] " if idx is not None else ""
    lines = [
        f"{prefix}#{e['id']} — {e['timestamp'][:16]}",
        f"  Task      : {e['task']}",
    ]
    if e.get("files"):
        lines.append(f"  Files     : {', '.join(e['files'])}")
    if e.get("decisions"):
        for d in e["decisions"]:
            lines.append(f"  Decision  : {d}")
    if e.get("warnings"):
        for w in e["warnings"]:
            lines.append(f"  Warning   : {w}")
    if e.get("tags"):
        lines.append(f"  Tags      : {', '.join(e['tags'])}")
    if e.get("raw"):
        lines.append(f"  Notes     : {e['raw']}")
    return "\n".join(lines)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "memex",
    instructions=(
        "Persistent session memory for Claude Code. "
        "Call mem_load at the start of every session. "
        "Call mem_save whenever you finish a task or learn something worth keeping. "
        "Use mem_search to find specific past work. "
        "Use mem_list / mem_delete for housekeeping."
    ),
)


@mcp.tool()
def mem_save(
    task: str,
    files: Optional[list[str]] = None,
    decisions: Optional[list[str]] = None,
    warnings: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    notes: Optional[str] = None,
) -> str:
    """
    Save a memory entry about work just completed.

    Args:
        task:      One-sentence summary of what was done.
        files:     List of files touched / created / deleted.
        decisions: Architectural or design decisions made.
        warnings:  Anything surprising or easy to get wrong.
        tags:      Short labels for later filtering (e.g. ["auth", "api"]).
        notes:     Any freeform extra context.

    Call this:
      - At the end of a significant task or session.
      - Whenever you discover something worth warning a future session about.
      - After making an architectural decision.
    """
    entry = {
        "project": os.getcwd(),
        "timestamp": _now_iso(),
        "task": task.strip(),
        "files": json.dumps(files or []),
        "decisions": json.dumps(decisions or []),
        "warnings": json.dumps(warnings or []),
        "tags": json.dumps(tags or []),
        "raw": (notes or "").strip(),
    }
    with get_conn() as conn:
        cur = conn.execute(
            """INSERT INTO entries (project, timestamp, task, files, decisions, warnings, tags, raw)
               VALUES (:project, :timestamp, :task, :files, :decisions, :warnings, :tags, :raw)""",
            entry,
        )
        new_id = cur.lastrowid
    msg = f"✓ Saved memory #{new_id}: {task[:80]}"

    full_text = " ".join([
        task or "",
        json.dumps(files or []),
        json.dumps(decisions or []),
        json.dumps(warnings or []),
        json.dumps(tags or []),
        (notes or "")
    ])

    approx_tokens = len(full_text) // 4
    threshold = int(os.environ.get("MEMEX_WARN_TOKENS", "300"))

    if approx_tokens > threshold:
        msg += (
            f"\n⚠ This entry is long (~{approx_tokens} tokens). "
            "Consider keeping each field to one line."
        )
    return msg 

@mcp.tool()
def mem_load(
    hint: Optional[str] = None,
    files: Optional[list[str]] = None,
) -> str:
    """
    Load relevant memory entries for a new session.

    Returns the N most recent entries plus any entries that match the
    hint (keyword search) or overlap with the files list.

    Args:
        hint:  Optional keyword or phrase describing the current task.
        files: Optional list of files you're about to work on.

    Call this at the START of every new Claude Code session.
    """
    with get_conn() as conn:
        # 1. Recent entries
        recent_rows = conn.execute(
            "SELECT * FROM entries ORDER BY id DESC LIMIT ?",
            (MAX_LOAD_RECENT,),
        ).fetchall()
        recent = [_row_to_dict(r) for r in recent_rows]
        recent_ids = {e["id"] for e in recent}

        matched: list[dict] = []

        # 2. FTS keyword search on hint
        if hint and hint.strip():
            safe_hint = re.sub(r'[^a-zA-Z0-9 _\-]', ' ', hint).strip()
            if safe_hint:
                fts_rows = conn.execute(
                    """SELECT e.* FROM entries e
                       JOIN entries_fts f ON f.rowid = e.id
                       WHERE entries_fts MATCH ?
                       ORDER BY rank
                       LIMIT ?""",
                    (safe_hint, MAX_LOAD_MATCHED),
                ).fetchall()
                for r in fts_rows:
                    d = _row_to_dict(r)
                    if d["id"] not in recent_ids:
                        matched.append(d)
                        recent_ids.add(d["id"])

        # 3. File-path overlap
        if files:
            for fpath in files[:10]:
                like = f"%{fpath}%"
                file_rows = conn.execute(
                    "SELECT * FROM entries WHERE files LIKE ? ORDER BY id DESC LIMIT 3",
                    (like,),
                ).fetchall()
                for r in file_rows:
                    d = _row_to_dict(r)
                    if d["id"] not in recent_ids:
                        matched.append(d)
                        recent_ids.add(d["id"])

    if not recent and not matched:
        return "No memories saved for this project yet."

    parts = [f"=== memex: session context (db: {DB_PATH.name}) ===\n"]

    if recent:
        parts.append(f"--- Recent ({len(recent)}) ---")
        for i, e in enumerate(recent):
            parts.append(_format_entry(e, i + 1))

    if matched:
        parts.append(f"\n--- Matched your hint/files ({len(matched)}) ---")
        for i, e in enumerate(matched):
            parts.append(_format_entry(e, i + 1))

    return "\n".join(parts)


@mcp.tool()
def mem_search(query: str, limit: int = 10) -> str:
    """
    Full-text search across all memory entries.

    Args:
        query: Keywords to search for (e.g. "JWT auth middleware").
        limit: Max number of results (default 10).

    Use this when you want to find past work on a specific topic.
    """
    safe_query = re.sub(r'[^a-zA-Z0-9 _\-]', ' ', query).strip()
    if not safe_query:
        return "Query is empty after sanitisation."

    with get_conn() as conn:
        rows = conn.execute(
            """SELECT e.* FROM entries e
               JOIN entries_fts f ON f.rowid = e.id
               WHERE entries_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (safe_query, limit),
        ).fetchall()

    if not rows:
        return f"No entries matched '{query}'."

    parts = [f"=== Search results for '{query}' ({len(rows)}) ==="]
    for i, row in enumerate(rows):
        parts.append(_format_entry(_row_to_dict(row), i + 1))
    return "\n".join(parts)


@mcp.tool()
def mem_list(limit: int = 20, tag: Optional[str] = None) -> str:
    """
    List recent memory entries, optionally filtered by tag.

    Args:
        limit: How many entries to return (default 20).
        tag:   Optional tag to filter by (e.g. "auth").

    Use this to review or clean up stored memories.
    """
    with get_conn() as conn:
        if tag:
            rows = conn.execute(
                "SELECT * FROM entries WHERE tags LIKE ? ORDER BY id DESC LIMIT ?",
                (f'%"{tag}"%', limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM entries ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()

    if not rows:
        msg = f"No entries" + (f" with tag '{tag}'" if tag else "") + "."
        return msg

    parts = [f"=== memex: {len(rows)} entries ==="]
    for i, row in enumerate(rows):
        parts.append(_format_entry(_row_to_dict(row), i + 1))
    return "\n".join(parts)


@mcp.tool()
def mem_delete(entry_id: int) -> str:
    """
    Delete a memory entry by its id.

    Args:
        entry_id: The numeric id shown in mem_list or mem_load output.

    Use this to remove outdated or incorrect entries.
    """
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        if cur.rowcount == 0:
            return f"No entry with id {entry_id}."
    return f"✓ Deleted entry #{entry_id}."


@mcp.tool()
def mem_update(
    entry_id: int,
    task: Optional[str] = None,
    files: Optional[list[str]] = None,
    decisions: Optional[list[str]] = None,
    warnings: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    notes: Optional[str] = None,
) -> str:
    """
    Update an existing memory entry. Only the fields you supply are changed.

    Args:
        entry_id:  The numeric id shown in mem_list or mem_load output.
        task:      Replacement one-sentence summary.
        files:     Replacement list of files touched.
        decisions: Replacement list of decisions.
        warnings:  Replacement list of warnings.
        tags:      Replacement list of tags.
        notes:     Replacement freeform notes.

    Use this to correct a typo, add a warning you forgot, or update tags
    without losing the entry's original id and timestamp.
    """
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
        if row is None:
            return f"No entry with id {entry_id}."
        existing = _row_to_dict(row)

    updates: dict = {}
    if task is not None:
        updates["task"] = task.strip()
    if files is not None:
        updates["files"] = json.dumps(files)
    if decisions is not None:
        updates["decisions"] = json.dumps(decisions)
    if warnings is not None:
        updates["warnings"] = json.dumps(warnings)
    if tags is not None:
        updates["tags"] = json.dumps(tags)
    if notes is not None:
        updates["raw"] = notes.strip()

    if not updates:
        return f"Nothing to update for entry #{entry_id} — no fields supplied."

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values()) + [entry_id]
    with get_conn() as conn:
        conn.execute(f"UPDATE entries SET {set_clause} WHERE id = ?", values)

    changed = ", ".join(updates.keys())
    return f"✓ Updated entry #{entry_id} ({changed})."


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
