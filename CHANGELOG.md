# Changelog

## [Unreleased]

## [0.1.0] - 2026-05-26

### Added

- Four submodules under `chunkhound_index_commons`:
  - `resolve`: `is_duckdb_file`, `resolve_chunkhound_source`. Identifies a DuckDB database by its `DUCK` header magic; resolves a ChunkHound index directory to its single sibling-of-`*.root.json` database file or raises listing candidates.
  - `schema`: `referenced_tables`, `topological_order`, `reject_unsupported_objects`. FK topological sort over `CREATE TABLE` DDLs (raises on cycle), and a front gate refusing non-`main` schemas, views, user-defined types, generated columns, and self-referential FKs. `reject_unsupported_objects` requires a `database_name` keyword argument (no default) so the caller states its ATTACH alias explicitly.
  - `sql`: `escape_sql_literal`, `quote_identifier`, `is_bare_identifier`. DuckDB string-interpolation safety primitives.
  - `vss`: `is_hnsw_index_ddl`, `parse_hnsw_column`, `bundled_vss_path`, `load_bundled_vss`, `capture_hnsw_metrics`, `recreate_hnsw_index`. Loads the bundled `vss.duckdb_extension` binary from the `duckdb-extension-vss` wheel, recovers HNSW `metric` via `pragma_hnsw_index_info()`, and recreates indexes with the recovered metric.
- PEP 561 `py.typed` marker so downstream consumers see commons' type annotations.
- 71 tests across the four submodules. Three integrate against a real ChunkHound index (`shopware_cli_index`), committed at `tests/fixtures/shopware-cli-chunks.duckdb` (~204 MiB) via Git LFS.

### Packaging

- Owns the floors `duckdb>=1.4.0,<1.5.3.dev0` and `duckdb-extension-vss>=1.5.2` on behalf of downstream consumers, which should not pin either themselves.
- Python 3.10 through 3.14 supported.
