# Contributing to memex

Thanks for wanting to help. Here's everything you need to get started.

## Setup

Requires Python 3.10+.

```bash
git clone https://github.com/pragneshbagary/memex.git
cd memex
python3.10 -m pip install -e ".[dev]"
```

The only runtime dependency is `mcp`. No build tools, no database to spin up.

## Running tests

```bash
python3.10 -m pytest tests/ -v
```

All 70 tests should pass. Add tests for any new behaviour you introduce.

## Where to start

Check the [`good first issue`](https://github.com/pragneshbagary/memex/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) label, these are self-contained and well-scoped.

The two main files:

| File | What it contains |
|------|-----------------|
| `memex/server.py` | The MCP server and all six tools (`mem_save`, `mem_load`, `mem_search`, `mem_list`, `mem_update`, `mem_delete`) |
| `memex/cli.py` | The `memex` CLI (`install`, `remove`, `list`, `search`, `export`, `status`) |

## Submitting a PR

1. Fork the repo and create a branch
2. Make your change and add tests
3. Make sure `python3.10 -m pytest tests/ -v` passes
4. Open a PR , describe what you changed and why

## Questions

Open an issue or start a discussion. Happy to help.
