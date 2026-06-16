# memex

![memex demo](docs/demo.gif)

Every Claude Code session starts without knowing what you built last time — which files you changed, what decisions you made, what broke. You re-explain. Claude re-reads. You start over.

**memex keeps a structured log of every session. Claude reads it at the start of the next one.**

No cloud. No LLM extraction. No cost per save. Just local SQLite and two commands to install.

## Install

```bash
pip install memex
memex install
```

Restart Claude Code. That's it.

## What gets saved

Each entry has structure — not a blob of text:

```python
mem_save(
    task="Replaced JWT auth with session cookies",
    files=["src/auth.py", "src/middleware.py"],
    decisions=["Session cookies over JWT — simpler, no token refresh needed"],
    warnings=["Redis required — app won't start without REDIS_URL set"],
    tags=["auth", "sessions"]
)
```

Claude calls `mem_save` when it finishes something meaningful. You can also just tell it: *"save what we just did."*

## What Claude sees at session start

```
=== memex: session context (db: my_project.db) ===

--- Recent (2) ---
[1] #4 — 2026-06-14T10:32
  Task      : Replaced JWT auth with session cookies
  Files     : src/auth.py, src/middleware.py
  Decision  : Session cookies over JWT — simpler, no token refresh needed
  Warning   : Redis required — app won't start without REDIS_URL set
  Tags      : auth, sessions

[2] #3 — 2026-06-13T15:10
  Task      : Added rate limiting to /api/login
  Files     : src/middleware.py
  Warning   : Rate limiter is in-memory per process — resets on restart
  Tags      : auth, rate-limiting
```

Claude calls `mem_load` automatically at the start of every session. It returns the most recent entries plus any entries that match what you're working on — by keyword and by file path.

## Browse from the terminal

You don't need to be inside Claude to look at your history:

```bash
memex list                  # recent entries for this project
memex list --tag auth       # filter by tag
memex search "rate limit"   # full-text search
```

## Five MCP tools

| Tool | What it does |
|------|--------------|
| `mem_load` | Called at session start — returns recent + relevant entries |
| `mem_save` | Saves a structured entry after meaningful work |
| `mem_search` | Full-text search across all entries |
| `mem_list` | Lists entries, optionally filtered by tag |
| `mem_delete` | Removes a stale entry by id |

## Why not just CLAUDE.md?

`CLAUDE.md` is for static project documentation — architecture, conventions, how to run tests. It doesn't change much and it isn't session-aware.

memex captures what's changing session to session: what you built yesterday, the decision you made this morning, the warning you discovered an hour ago. It's the difference between *"here's the project"* and *"here's what happened last time."*

## Memory is scoped per project

Each project gets its own SQLite database at `~/.memex/<project>.db` based on the working directory. Sessions from different projects never mix.

## Configuration

Set these in the MCP `env` block in `~/.claude.json` if you need to override defaults:

| Variable | Default | Description |
|----------|---------|-------------|
| `MEMEX_DIR` | `~/.memex` | Where DBs are stored |
| `MEMEX_GLOBAL` | `0` | Set to `1` to share one DB across all projects |
| `MEMEX_RECENT` | `5` | Max recent entries loaded per session |
| `MEMEX_MATCHED` | `5` | Max FTS-matched entries loaded per session |

## Uninstall

```bash
memex remove
pip uninstall memex
```

Memory DBs are kept at `~/.memex/` — delete that directory manually if you want to wipe everything.

## Requirements

- Python 3.10+
- `mcp` package (installed automatically)
- SQLite with FTS5 (standard since Python 3.8)
- Claude Code CLI

## License

MIT
