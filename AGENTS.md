# AGENTS.md

## Layout

```
chunkhound-index-commons/
├── pyproject.toml                 # deps, lint/type config, hatch build
├── uv.lock                        # resolved versions; refresh via `uv lock`
├── .github/workflows/             # ci.yml, release.yml
├── .pre-commit-config.yaml
├── .typos.toml
├── .gitattributes
├── renovate.json5
├── README.md                      # install, submodule table, inherited limits
├── AGENTS.md
├── CLAUDE.md                      # @AGENTS.md
├── CONTRIBUTING.md                # setup, local checks, CI, release process
├── CHANGELOG.md
├── LICENSE
├── docs/
│   ├── architecture.md            # why the primitives, front-gate refusal, HNSW metric recovery, vss bundling, ChunkHound compatibility
│   └── out-of-scope.md            # refused source shapes, dropped metadata, latent code edges, rejected approaches
├── src/chunkhound_index_commons/
│   ├── __init__.py                # package docstring; no re-exports
│   ├── py.typed                   # PEP 561 marker
│   ├── resolve.py                 # ChunkHound directory resolution
│   ├── schema.py                  # FK topological sort, front-gate refusal
│   ├── sql.py                     # SQL escape, quote, bare-identifier check
│   └── vss.py                     # vss extension, HNSW metric capture/recreate
└── tests/
    ├── conftest.py                # fixtures: chunkhound_dir, fk_chain_db, hnsw_db, cosine_hnsw_db, shopware_cli_index
    ├── fixtures/                  # shopware-cli-chunks.duckdb (~204 MiB, Git LFS)
    ├── test_resolve.py
    ├── test_schema.py
    ├── test_sql.py
    └── test_vss.py
```

## Submodule → symbols

| Submodule | Public | Module-internal |
|---|---|---|
| `resolve` | `DUCKDB_MAGIC`, `ROOT_JSON_SUFFIX`, `is_duckdb_file`, `resolve_chunkhound_source` | (none) |
| `schema` | `referenced_tables`, `topological_order`, `reject_unsupported_objects` | regexes `_FK_REFERENCES_RE`, `_GENERATED_COLUMN_RE` |
| `sql` | `escape_sql_literal`, `quote_identifier`, `is_bare_identifier` | regex `_BARE_IDENTIFIER_RE` |
| `vss` | `is_hnsw_index_ddl`, `parse_hnsw_column`, `bundled_vss_path`, `load_bundled_vss`, `capture_hnsw_metrics`, `recreate_hnsw_index` | regexes `_HNSW_RE`, `_HNSW_COLUMN_RE` |
| `__init__` | (no re-exports; package docstring only) | (none) |

## When to modify

| Task | File / symbol |
|---|---|
| ChunkHound directory resolution rules | `resolve.py` → `resolve_chunkhound_source` |
| DuckDB header magic byte check | `resolve.py` → `is_duckdb_file` |
| FK topological order or cycle handling | `schema.py` → `topological_order`, `referenced_tables` |
| Front-gate refusal (schemas, views, UDTs, generated cols, self-ref FKs) | `schema.py` → `reject_unsupported_objects` |
| SQL string-interpolation safety | `sql.py` → `escape_sql_literal`, `quote_identifier` |
| Bare-identifier predicate (HNSW expression-key refusal) | `sql.py` → `is_bare_identifier` |
| vss binary loading / wheel layout discovery | `vss.py` → `load_bundled_vss`, `bundled_vss_path` |
| HNSW metric capture from `pragma_hnsw_index_info()` | `vss.py` → `capture_hnsw_metrics` |
| HNSW index recreation DDL shape | `vss.py` → `recreate_hnsw_index` |
| HNSW DDL parsing (presence check, column capture) | `vss.py` → `is_hnsw_index_ddl`, `parse_hnsw_column` |
| New public export under an existing submodule | submodule file + add to README §Submodules and CHANGELOG |
| New submodule | `src/chunkhound_index_commons/<name>.py`, README §Submodules, AGENTS.md §Submodule → symbols, `tests/test_<name>.py` |
| Build / test / lint / release workflows | `.github/workflows/{ci,release}.yml` (CONTRIBUTING.md §CI workflows) |
| Setup / local checks / release process | `CONTRIBUTING.md` (not here) |

## Invariants enforced by code

- Catalog DDL strips HNSW `WITH (...)`; metric is recoverable only through `pragma_hnsw_index_info()` after `vss` is loaded on the connection. (architecture.md §HNSW metric recovery)
- DuckDB DDL does not bind parameters; every interpolated literal goes through `sql.escape_sql_literal`, every identifier through `sql.quote_identifier`. (CONTRIBUTING.md §Tooling notes; README §Submodules)
- `schema.reject_unsupported_objects` requires `database_name` as a keyword argument; the caller states the ATTACH alias at the call site. (README §Submodules → `schema.reject_unsupported_objects`)
- HNSW expression keys (non-bare-column index expressions like `CAST(col AS FLOAT[N])`) are refused by callers pairing `vss.parse_hnsw_column` with `sql.is_bare_identifier`; the parser truncates expression keys mid-clause as an inherited limitation. (out-of-scope.md §Expression HNSW keys)
- `vss.recreate_hnsw_index` requires `hnsw_enable_experimental_persistence = true` on the connection. The flag is a session-level concern the caller owns. (README §Submodules → `vss.recreate_hnsw_index`)
- `commons` owns the `duckdb` and `duckdb-extension-vss` floors on behalf of downstream consumers. Floor moves that change the supported on-disk DuckDB file format are breaking. (architecture.md §Bundled vss extension)
- The package ships `src/chunkhound_index_commons/py.typed` so downstream mypy sees the annotations. Adding a sub-subpackage requires its own marker. (CONTRIBUTING.md §Tooling notes)
- Three integration tests (`test_shopware_*` in `tests/test_vss.py`) use the `shopware_cli_index` artifact committed at `tests/fixtures/shopware-cli-chunks.duckdb` via Git LFS; the fixture raises `FileNotFoundError` when the file is absent. CI checks out LFS and runs them. (CONTRIBUTING.md §The shopware fixture)

## Build / verify

```
uv sync --extra dev --frozen
uv run pytest
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/
uv run typos
```

CONTRIBUTING.md §Local checks owns the canonical command list.
