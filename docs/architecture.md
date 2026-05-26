# Architecture

## Why these primitives

DuckDB's single-file format does not reclaim disk space after deletes or drops, and `VACUUM` is a no-op for size reclamation. The obvious workaround for a consumer that wants to rebuild a source database into a fresh file is to `ATTACH` the source and `COPY FROM DATABASE` into a fresh target. That path commits child rows before their foreign-key parents and aborts with a non-deterministic FK violation on FK-bearing [ChunkHound](https://github.com/chunkhound/chunkhound) indexes at scale ([duckdb/duckdb#16785](https://github.com/duckdb/duckdb/issues/16785)). The failing key differs between runs on the same source; the data is referentially clean. It is an insertion-order race, and DuckDB exposes no setting that disables FK enforcement.

`commons.schema.topological_order` orders the source's tables so the consumer can insert one table at a time, parent before child, and sidestep the race.

The other primitives encode equivalent point-of-knowledge facts the consumer would otherwise re-discover by hitting them:

- `commons.schema.reject_unsupported_objects` refuses source shapes a verbatim rebuild cannot faithfully reproduce. The refusal converts a downstream silent-loss or opaque-crash path into a clear pre-target error.
- `commons.vss.capture_hnsw_metrics` reads HNSW `metric` from `pragma_hnsw_index_info()` because the catalog DDL strips the `WITH (metric = '<m>')` clause.
- `commons.vss.bundled_vss_path` and `load_bundled_vss` load the `vss` extension from a disk path inside the `duckdb-extension-vss` wheel so the consumer stays offline-safe.
- `commons.resolve.resolve_chunkhound_source` identifies a ChunkHound database inside a directory by the `DUCK` magic at byte 8 of the file header, not by filename.

Each primitive lives in one of four submodules (`resolve`, `schema`, `sql`, `vss`). The split is by concern: directory I/O, DDL inspection, string-interpolation safety, extension and HNSW handling.

## Front-gate refusal

`commons.schema.reject_unsupported_objects(conn, *, database_name=...)` runs five sequential checks against `database_name`'s catalog:

1. Non-`main` schema objects.
2. Views.
3. User-defined types.
4. Tables with generated columns.
5. Self-referential foreign keys.

Each refusal raises `ValueError` with a message naming the offending objects. The consumer calls this before its rebuild touches the target file, so the user sees the refusal rather than a half-written multi-GB output.

`duckdb_schemas()` marks the source's own `main` as `internal = true`, so non-main objects are detected via the `tables` and `views` catalogs filtered on `schema_name`, not on the `internal` flag. The catalog-flag subtlety is verified on DuckDB 1.5.2 and lives at the call site.

Refusal mechanism per case lives at [out-of-scope.md §Non-`main` schemas](out-of-scope.md#non-main-schemas), [§Views](out-of-scope.md#views), [§User-defined types](out-of-scope.md#user-defined-types), [§Generated columns](out-of-scope.md#generated-columns), and [§Self-referential foreign keys](out-of-scope.md#self-referential-foreign-keys).

`commons.schema.topological_order` is a sixth refusal point in practice: it raises `ValueError` on a foreign-key cycle. See [out-of-scope.md §Foreign-key cycles](out-of-scope.md#foreign-key-cycles).

A seventh refusal lives in `commons.vss.parse_hnsw_column` paired with `commons.sql.is_bare_identifier`: HNSW indexes built on a non-bare-column expression (e.g. `CAST(col AS FLOAT[N])`) are refused before the consumer can persist a malformed recipe row. See [out-of-scope.md §Expression HNSW keys](out-of-scope.md#expression-hnsw-keys).

## HNSW metric recovery

ChunkHound writes HNSW indexes with `metric = 'cosine'`. The catalog DDL exposed by `duckdb_indexes().sql` strips the entire `WITH (...)` clause, so a metric-blind rebuild silently resets the index to the `vss` default `l2sq`. ChunkHound's cosine-distance queries then fall through to a brute-force table scan with no error and no warning. That is the regression the metric recovery exists to prevent.

`commons.vss.capture_hnsw_metrics(conn)` reads `pragma_hnsw_index_info()` and returns `{index_name: metric}`. Requires `commons.vss.load_bundled_vss(conn)` first; `pragma_hnsw_index_info()` is exposed only when the extension is loaded.

`commons.vss.parse_hnsw_column(ddl)` captures the indexed column from the DDL. The catalog gives back the `USING HNSW (<col>)` clause but loses the `WITH (...)` parameters, so capturing the column from DDL plus the metric from the pragma is what fully describes the index for recreation.

`commons.vss.recreate_hnsw_index(conn, *, name, table, column, metric)` issues `CREATE INDEX <name> ON <table> USING HNSW (<column>) WITH (metric = '<metric>')`. `vss` must be loaded and `hnsw_enable_experimental_persistence = true` must be set on `conn`. Both are session-level concerns the caller owns; the primitive does not set them because a consumer may want to scope or batch the `SET` differently.

Only `metric` is recovered because it is the only HNSW build-time parameter `pragma_hnsw_index_info()` surfaces. The other knobs (`M`, `M0`, `ef_construction`, `ef_search`) are not recoverable from a built index. See [out-of-scope.md §HNSW tuning beyond `metric`](out-of-scope.md#hnsw-tuning-beyond-metric).

## Bundled vss extension

DuckDB cannot create or read an HNSW index without the `vss` extension loaded. Commons depends on the community-built [`duckdb-extension-vss`](https://pypi.org/project/duckdb-extension-vss/) wheel, which ships the `vss.duckdb_extension` binary as part of its payload. `commons.vss.load_bundled_vss(conn)` `LOAD`s the binary directly from disk; no `INSTALL`, no network round-trip. Downstream consumers stay offline-safe by default.

| Source index type | Extension | Bundled by                                    |
|-------------------|-----------|-----------------------------------------------|
| `HNSW`            | `vss`     | `duckdb-extension-vss` (community-maintained) |

`commons.vss.bundled_vss_path()` locates the binary inside the wheel's `extensions/v<duckdb-version>/vss.duckdb_extension` path and returns the highest-sorted match. The version-suffixed directory drifts with each `duckdb-extension-vss` release, so the locator globs the pattern rather than hard-coding the path.

The wheel's transitive pin (`duckdb==1.5.2` today) is the on-disk file-format pin downstream consumers inherit. Commons owns this pin on their behalf; a consumer should not declare `duckdb` or `duckdb-extension-vss` itself. Moves of either floor that change the supported on-disk format are breaking releases for commons.

## ChunkHound compatibility

Commons primitives are structurally generic, but four ChunkHound behaviors shape the design:

- **ChunkHound writes HNSW with `metric = 'cosine'`.** The catalog DDL strips the `WITH (...)` clause, so a metric-blind rebuild silently resets the index to the `vss` default `l2sq`. ChunkHound's cosine-distance queries would no longer hit the index and would run brute-force against the table. The metric-via-pragma recovery in `commons.vss.capture_hnsw_metrics` is the regression guard.
- **ChunkHound rebuilds HNSW only on the write path.** Its read path runs vector-distance queries with no index-existence check and no `CREATE INDEX` branch. A `--skip-hnsw` style artifact opened by ChunkHound brute-forces every semantic query forever until something rebuilds the index. That is why a downstream consumer that strips HNSW must pair the strip with a restore-by-recipe step, not assume ChunkHound will lazy-rebuild.
- **HNSW non-determinism is already part of ChunkHound's normal operation.** ChunkHound drops and recreates the HNSW on write batches that meet its size threshold (`insert_embeddings_batch`, default 50 rows), so the live index already changes shape across runs even without a downstream rebuild. A rebuild reproduces that property; it does not introduce a new one.
- **ChunkHound stores its index as a directory.** It writes `chunks.db` beside a `chunks.db.root.json` sidecar. `commons.resolve.resolve_chunkhound_source` lets a consumer pass that directory: it resolves only when exactly one `*.root.json` sidecar names a sibling carrying the DuckDB header magic (`DUCK` at byte 8), identifying the database by that magic rather than by file extension. A directory with no such index, or with more than one, raises `FileNotFoundError` and lists the DuckDB files it found rather than guessing which one was meant.

## Not supported (and why)

Source shapes the primitives refuse before a consumer's rebuild touches the target. The first five are caught by `commons.schema.reject_unsupported_objects`; the sixth by `commons.schema.topological_order`; the seventh by `commons.vss.parse_hnsw_column` paired with `commons.sql.is_bare_identifier`.

- Non-`main` schemas. (see [out-of-scope.md §Non-`main` schemas](out-of-scope.md#non-main-schemas))
- Views. (see [out-of-scope.md §Views](out-of-scope.md#views))
- User-defined types. (see [out-of-scope.md §User-defined types](out-of-scope.md#user-defined-types))
- Generated columns. (see [out-of-scope.md §Generated columns](out-of-scope.md#generated-columns))
- Self-referential foreign keys. (see [out-of-scope.md §Self-referential foreign keys](out-of-scope.md#self-referential-foreign-keys))
- Foreign-key cycles. (see [out-of-scope.md §Foreign-key cycles](out-of-scope.md#foreign-key-cycles))
- Expression HNSW keys. (see [out-of-scope.md §Expression HNSW keys](out-of-scope.md#expression-hnsw-keys))

For metadata the substrate drops rather than refuses, latent code edges, rejected alternative approaches, and per-case fix shapes, see [out-of-scope.md](out-of-scope.md).
