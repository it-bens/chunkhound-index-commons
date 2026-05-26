## Pre-Step-8

A change to the `duckdb` or `duckdb-extension-vss` version constraint in `pyproject.toml` (or the resolved version in `uv.lock`) can shift on-disk DuckDB file-format compatibility with ChunkHound. Commons owns these floors on behalf of the compactor and the future merger, so the impact is amplified — every consumer inherits the floor move. When the supported format range moves, mark the commit breaking (`!`) and state the format impact in the body. A bump that stays within the same on-disk format is `build` without `!`.

## Pre-Step-9

Override the universal scope default with the rules below. Apply in priority order; fall back to the universal default only if no rule matches.

Module scopes (changes confined to one source submodule):

- `src/chunkhound_index_commons/resolve.py` → `resolve`
- `src/chunkhound_index_commons/schema.py` → `schema`
- `src/chunkhound_index_commons/sql.py` → `sql`
- `src/chunkhound_index_commons/vss.py` → `vss`
- `src/chunkhound_index_commons/__init__.py` → omit when only the module docstring changed; if re-exports are introduced (none today), scope to the submodule whose public surface changed.
- `src/chunkhound_index_commons/py.typed` → omit (PEP 561 marker; packaging concern, type `build`).

Other scopes:

- Only files under `tests/` → `tests`.
- Only files under `docs/` → omit scope (type is `docs`). Commons has no `docs/` directory yet; the migration doc lives at the repo root.
- Only root packaging files (`pyproject.toml`, `uv.lock`) → omit scope (type is `build`).
- Only agent/tooling docs (`AGENTS.md`, `CLAUDE.md`, root migration / scoping reports) or `.claude/` config → omit scope.

Scope omission (overrides the above):

- Changes spanning two or more submodules with no dominant one → omit scope. The natural pair is `sql` + `vss` (vss imports from sql); a change touching both is repository-wide unless one submodule clearly dominates.
- Repository-wide or cross-cutting changes → omit scope.

Confidence handling:

- HIGH: all changed source files map to one submodule scope.
- LOW: source changes span two submodules evenly → use `AskUserQuestion` to confirm scope or omission.
