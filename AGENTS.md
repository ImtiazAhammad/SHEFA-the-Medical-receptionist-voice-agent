## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Testing

- Run: `.venv/bin/python -m pytest` (pytest 9, config in `pyproject.toml` under `[tool.pytest.ini_options]`).
- Unit tests live in `tests/unit/` as plain `test_*` functions; `conftest.py` holds shared fixtures.
- `scripts/test_standalone.py` is a standalone smoke script (not part of the pytest suite).
- Test expectations:
  - 100% test coverage is the goal — tests make vibe coding safe.
  - When writing new functions, write a corresponding test.
  - When fixing a bug, write a regression test.
  - When adding error handling, write a test that triggers the error.
  - When adding a conditional (if/else, switch), write tests for BOTH paths.
  - Never commit code that makes existing tests fail.
