# In-Repo Primitives (reference)

Standard library or DuckDB calls that look right in isolation often violate an invariant the package enforces only through a wrapper. Commons exposes those wrappers across four submodules.

## Lookup table

Search the relevant submodule for the primitive before reaching for the stdlib or DuckDB call directly.

| Call shape | Reach for | In-repo primitive | Reason the wrapper exists |
|---|---|---|---|
| Embed a user-controlled or runtime string into a DuckDB SQL statement | Inline f-string with `'<value>'` | `commons.sql.escape_sql_literal(value)` | DuckDB DDL does not accept parameter binding. A bare single quote in the value closes the literal and turns the suffix into SQL. Doubling single quotes (the DuckDB literal escape) is the only safe path. |
| Wrap a table or index name in a DDL statement | Inline `"<name>"` | `commons.sql.quote_identifier(name)` | A `"` embedded in the name (rare but legal) closes the quoted identifier and turns the suffix into SQL. Doubling embedded `"` is the DuckDB identifier escape. |
| Refuse non-bare-column HNSW expression keys | Custom regex per call site | `commons.sql.is_bare_identifier(name)` | The HNSW DDL parse truncates expression keys mid-clause; the bare-identifier predicate is the documented refusal pair. Refusing in two places with two regexes lets them drift. |
| `LOAD` the `vss` extension | Hand-written `INSTALL` + `LOAD` against a network registry | `commons.vss.load_bundled_vss(conn)` | The package is offline-safe by design. The bundled `duckdb-extension-vss` wheel ships the `.duckdb_extension` binary; `INSTALL` would force a network round-trip and lose that guarantee. |
| Locate the `vss` binary on disk | Hard-coded path under the wheel's install location | `commons.vss.bundled_vss_path()` | The wheel's internal path includes a version-suffixed `v*/` directory that drifts with each `duckdb-extension-vss` release. The helper globs `v*/vss.duckdb_extension` and picks the highest. |
| Build a topological order over FK-dependent tables | Sort by `table_name`, or rely on `duckdb_tables()` row order | `commons.schema.topological_order(table_ddls)` | The catalog gives no FK information directly; the primitive parses `FOREIGN KEY (...) REFERENCES <table>` out of each `CREATE TABLE` DDL, builds the dependency graph, and raises on a cycle. Parent-before-child insertion is what avoids the `COPY FROM DATABASE` FK race. |
| Find FK targets in a single DDL | Custom regex per call site | `commons.schema.referenced_tables(ddl)` | The bare-identifier `FOREIGN KEY (...) REFERENCES <name>` regex is centralized so a regex bug (or widening to quoted names) is one fix in one place. |
| Refuse source shapes a rebuild cannot reproduce | Per-consumer catalog queries | `commons.schema.reject_unsupported_objects(conn, *, database_name=...)` | The front gate (non-`main` schemas, views, UDTs, generated columns, self-ref FKs) is identical for the compactor and the merger; duplicating it would mean five places to keep in sync. `database_name` is required (no default) — callers state intent at the site. |
| Detect HNSW indexes in `duckdb_indexes().sql` output | Substring search for `HNSW` | `commons.vss.is_hnsw_index_ddl(ddl)` | `HNSW` may appear in a comment, an identifier, or a stripped form; the `USING HNSW` shape is the catalog-DDL form and the only one a rebuilder cares about. |
| Parse the indexed column from an HNSW DDL | Custom string slicing | `commons.vss.parse_hnsw_column(ddl)` | The column expression sits inside `USING HNSW(...)` and the non-greedy capture truncates expression keys at the first inner `)` — that's the documented inherited limitation; callers pair with `is_bare_identifier` to refuse. |
| Recover HNSW metric across a rebuild | `duckdb_indexes().sql` (strips `WITH (...)`) | `commons.vss.capture_hnsw_metrics(conn)` | The catalog DDL drops `WITH (metric = '<m>')`; only `pragma_hnsw_index_info()` surfaces the live metric. The primitive returns `index_name -> metric` for every HNSW index visible to `conn`. Requires `vss` loaded. |
| Recreate an HNSW index with a recovered metric | Inline `CREATE INDEX ... USING HNSW (...) WITH (metric = '...')` | `commons.vss.recreate_hnsw_index(conn, *, name, table, column, metric)` | One place to keep the DDL shape, one place to apply identifier quoting and literal escaping. Caller owns the session-level `hnsw_enable_experimental_persistence` flag. |
| Resolve a path that may be a ChunkHound index directory or a file | Manual `glob` + `is_file` checks | `commons.resolve.resolve_chunkhound_source(source)` | Identifies the database by DuckDB header magic, not by filename. A directory with no `*.root.json` sidecar, or with more than one, raises `FileNotFoundError` listing candidates rather than guessing. |
| Confirm a path is a DuckDB file | Filename or extension check | `commons.resolve.is_duckdb_file(path)` | The check reads the first 12 bytes and matches `DUCK` at offset 8. An unreadable file returns `False` rather than raising, so a directory scan survives a single broken sibling. |

## Decision Test

Before writing the stdlib or DuckDB call, ask:

> Does this call build a SQL literal, quote a DDL identifier, load the vss
> extension, locate the bundled binary, order FK-dependent tables, refuse
> an unsupported source shape, work with HNSW index DDL, or resolve a
> ChunkHound index source — and does the relevant submodule already wrap
> the primitive for that case?

- yes, primitive exists → use the primitive
- yes, no primitive exists but the case is in scope of an existing one → extend the primitive; don't add a parallel one
- yes, no primitive exists and the case is new → flag and propose adding one to the right submodule rather than reaching past the missing wrapper
- no → stdlib / DuckDB call is fine

## What the lookup is not

The table is not exhaustive. It captures the categories where missed routing through the primitive would defeat a package-wide invariant (SQL injection through DDL, network round-trip on extension load, metric drift across rebuild, FK race on streaming insert). New categories appear when a new primitive lands; extend the table when it does. Treat the table as evidence-based, not definitional: if a call sits clearly outside these categories, the table does not apply.

## What deliberately does NOT live in commons

Some primitives a consumer might expect from a "DuckDB substrate" library are intentionally not exposed. Recognize them so a missing primitive does not get re-implemented inside commons.

| Shape | Owner | Reason |
|---|---|---|
| `human_size(num_bytes)` byte formatter | Consumer CLI | CLI presentation, not a substrate primitive. |
| `_compactor_hnsw_recipe` table format, recipe-table read/write, `restore_indexes` orchestration | Compactor | The table name is the compactor's cross-tool contract; primitives commons exposes (`capture_hnsw_metrics`, `recreate_hnsw_index`) compose into it. |
| `CompactionResult`, `MergeResult`, or any operation-specific result dataclass | Consumer | Result types belong to the operation, not the substrate. |
| `replace_with_compacted` in-place swap | Compactor | UX shape specific to the compactor's `--replace` flow. |
