## memex: Session Memory

At the **start of every session**, call `mem_load` with a brief hint about
what you're working on. This gives you context from past sessions so you
don't rediscover things you already know.

```
mem_load(hint="<what you're about to work on>", files=["<relevant files>"])
```

During a session, call `mem_save` whenever you:
- Finish a meaningful task
- Make an architectural or design decision
- Discover something surprising or easy to get wrong

```
mem_save(
    task="One-sentence summary of what was done",
    files=["list", "of", "files", "touched"],
    decisions=["Any design decisions made"],
    warnings=["Anything surprising or easy to get wrong"],
    tags=["short", "labels"],
    notes="Any extra freeform context"
)
```

Other tools:
- `mem_search(query)` — find past work on a specific topic
- `mem_list()` — see all stored entries
- `mem_delete(id)` — remove stale entries

Memory is stored locally in ~/.memex/ as SQLite — no LLMs, no network.
