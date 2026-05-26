# Out of Scope

Source shapes the commons primitives refuse, metadata the substrate drops rather than carrying, latent code edges no real workload hits, and approaches considered against the motivating [ChunkHound](https://github.com/chunkhound/chunkhound) workload and not pursued. Each section carries the why-not and, where the gap is mechanical enough to describe, a fix shape so a future maintainer (ChunkHound's schema evolves, a third consumer arrives) starts from an inventory rather than rediscovering each gap from a test failure.

## Non-`main` schemas

Reproducing non-`main` schemas in a downstream rebuild requires emitting `CREATE SCHEMA` before tables and rewriting `REFERENCES` clauses to be schema-qualified. Silently dropping schemas would corrupt the user's data model. `commons.schema.reject_unsupported_objects` refuses any source object whose `schema_name != 'main'` and raises `ValueError` before the consumer can touch its target.

**Fix shape.**

1. Capture schema DDL from `duckdb_schemas() WHERE NOT internal`, emit `CREATE SCHEMA "<name>"` before any `CREATE TABLE` for that schema.
2. Qualify the INSERT target on the consumer side: `INSERT INTO "<schema>"."<table>" SELECT * FROM src."<schema>"."<table>"`.
3. Rewrite `REFERENCES` clauses so cross-schema FKs resolve. `duckdb_tables().sql` does not currently qualify them.
4. Pass the qualified `<schema>.<table>` key into `commons.schema.topological_order` so the dependency graph spans schemas.

Regression test: a source with two schemas, the second's table FK-referencing the first's. Assert both round-trip with row content and the FK resolves on the rebuilt file.

## Views

Reproducing views requires resolving them against the rebuilt tables (some DuckDB versions resolve the view's SELECT at CREATE time). `commons.schema.reject_unsupported_objects` refuses any row in `duckdb_views()`.

**Fix shape.**

The consumer captures from `duckdb_views().sql` plus a replay phase after its per-table INSERT loop finishes. A dependency walk on the view set is needed for view-on-view stacks: replay leaves first, parents last. The substrate does not provide a view-topological-order primitive today; if a second consumer needs one, lift it into `commons.schema` mirroring `topological_order`.

Regression test: a base table, one view over it, one view-on-view. Assert both views appear in the rebuilt catalog and return rows.

## User-defined types

`duckdb_tables().sql` inlines ENUM / STRUCT / alias definitions into the column declaration when emitting `CREATE TABLE`. Without refusing, a verbatim rebuild silently drops the named `CREATE TYPE` and any `value::<type>` cast against the rebuilt DB fails with "type does not exist". `commons.schema.reject_unsupported_objects` refuses any row in `duckdb_types() WHERE NOT internal`.

**Fix shape.**

1. Add a capture step for `duckdb_types() WHERE NOT internal` returning name and definition.
2. Emit `CREATE TYPE "<name>" AS <definition>` before any `CREATE TABLE` references it.
3. Verify the rebuilt `duckdb_tables().sql` references the type by name rather than re-inlining; if it re-inlines, the captured DDL has to be rewritten column-by-column.

Regression test: a source with one ENUM type and one table column of that type. Assert the rebuilt schema preserves the type by name, not just the underlying representation.

## Generated columns

`duckdb_tables().sql` keeps the virtual column in the column list, but `INSERT INTO ... SELECT *` rejects it as a write target, so a consumer's rebuild crashes opaquely at the per-table insert. `commons.schema.reject_unsupported_objects` refuses any table whose `duckdb_tables().sql` matches `GENERATED ALWAYS`.

**Fix shape.**

DuckDB 1.5.2's `duckdb_columns()` does not expose a `generated_expression` flag (the expression appears in `column_default`, indistinguishable from a plain DEFAULT), so identifying generated columns needs a parse of `duckdb_tables().sql`:

1. Parse each table's column declarations from `duckdb_tables().sql`; flag any column whose declaration contains `GENERATED ALWAYS`.
2. Build an explicit column list per table (non-generated columns only) and switch the consumer's INSERT from `SELECT *` to `INSERT INTO {q} (cols) SELECT cols FROM src.{q}`.
3. Generated values rederive from the rebuilt rows automatically; no extra step.

Regression test: a source with a `GENERATED ALWAYS AS (id * 2)` column populated by 10 rows. Assert the rebuilt table has 10 rows and the virtual column re-derives.

## Self-referential foreign keys

A self-referential FK survives `duckdb_tables().sql` as invalid DDL: the FK clause gets dropped and the column list keeps a trailing comma. Lenient DuckDB parsers lose the constraint silently; stricter ones crash at `CREATE TABLE`. Reproducing it would require either a post-create `ALTER TABLE ADD CONSTRAINT` (which DuckDB does not support for FKs) or deferred constraints (not portable across DuckDB versions). `commons.schema.reject_unsupported_objects` refuses any row in `duckdb_constraints()` where `constraint_type = 'FOREIGN KEY' AND table_name = referenced_table`.

**Fix shape.**

Two viable paths:

1. **Upstream-dependent.** Wait for DuckDB to grow `ALTER TABLE ADD FOREIGN KEY` or portable deferred constraints, then reconstruct the FK from `duckdb_constraints()` after the table is created and populated.
2. **Two-pass populate.** Capture the FK column from `duckdb_constraints()`. INSERT each row with that column set to NULL, then run a single `UPDATE` to fill the back-edges from the source. Requires the column to be nullable in the rebuilt table, which may need a relaxation that the source did not impose.

Regression test: a `node(id, parent)` table with a single root and a depth-3 chain. Assert the rebuilt table preserves every parent edge and rejects an orphaned parent reference.

## Expression HNSW keys

`commons.vss.parse_hnsw_column` captures the indexed column from the `USING HNSW (...)` clause. The capture is non-greedy and stops at the first close paren that allows the trailing `\s*\)` to match, so an expression like `CAST(col AS FLOAT[N])` round-trips as malformed DDL (the capture truncates mid-clause). A downstream recipe table format that stores the column as a single `VARCHAR` also has no schema for arbitrary expressions. The substrate pairs the parse with a refusal: callers test the captured value against `commons.sql.is_bare_identifier` and raise on non-bare keys.

**Fix shape.**

1. Replace the regex in `commons.vss.parse_hnsw_column` with a parenthesis-balanced parse of the `USING HNSW (...)` body so an expression is captured intact.
2. Widen any downstream recipe table format to store the raw expression alongside the bare-column case, or keep the recipe bare-only and accept that the live HNSW DDL is the source of truth for expression keys (no skip-and-restore support for them).

Regression test: an HNSW on `CAST(raw AS FLOAT[4])`. Assert the index round-trips on a full rebuild and the consumer's restore path rebuilds it correctly.

## Foreign-key cycles

Topological order is undefined for a cycle. Deferring constraints is not generally portable across DuckDB versions. `commons.schema.topological_order` raises `ValueError`. No fix shape: this is a structural property of the source schema, not a code-level gap.

## HNSW tuning beyond `metric`

`M`, `M0`, `ef_construction`, and `ef_search` affect recall and build/query speed. `commons.vss.capture_hnsw_metrics` does not recover them because:

- **They are not surfaced by the catalog or any pragma.** `duckdb_indexes().sql` strips the entire `WITH (...)` clause. `pragma_hnsw_index_info()` returns `catalog_name`, `schema_name`, `index_name`, `table_name`, `metric`, `dimensions`, `count`, `capacity`, `approx_memory_usage`, `levels`, and `levels_stats`. None of the build-time tuning knobs appear there. There is no way to read them off a built index.
- **They are dominated by upstream factors.** The embedding model and reranking strategy (ChunkHound's MultiHopStrategy) move recall far more than these knobs.
- **Defaults are sane.** `vss` defaults (`connectivity`/`M`, `expansion_add`/`ef_construction`, `expansion_search`/`ef_search`) work for the ChunkHound workload.

If a consumer depended on tuned values, those indexes have to be recreated manually. The substrate does not pretend it can preserve them.

**Fix shape.**

The gap is upstream: a `pragma_hnsw_index_info()` extension or sibling pragma that reports build-time parameters. Once that lands, closing the gap on this side needs:

1. Read the extra columns alongside `metric` in `commons.vss.capture_hnsw_metrics`.
2. Widen the return type from `dict[str, str]` to a richer mapping, or add a sibling primitive (`capture_hnsw_recipes_full`) so the simple metric-only path stays cheap.
3. Pass each parameter through to the `WITH (...)` clause of `commons.vss.recreate_hnsw_index`, either by extending its signature or by accepting a structured recipe object.

## Table and column comments

Comments are stored in the `comment` column of `duckdb_tables()` and `duckdb_columns()`, not in the `.sql` DDL the substrate captures via `duckdb_tables().sql` (verified on DuckDB 1.5.2). Any rebuild that replays `duckdb_tables().sql` drops them. ChunkHound does not use comments (verified against the production index), so no real workload is affected today. Preserving them would add a per-table and per-column catalog walk plus `COMMENT ON` emission with no current consumer.

**Fix shape.**

1. Add a `commons.schema.capture_comments` primitive that walks both catalog columns and returns `(table, comment)` and `(table, column, comment)` rows.
2. Consumers emit `COMMENT ON TABLE "<t>" IS '<comment>'` and `COMMENT ON COLUMN "<t>"."<c>" IS '<comment>'` for any non-null comment, after the per-table INSERT phase and before any index rebuild. Both already accept SQL-string literals; route through `commons.sql.escape_sql_literal`.

Regression test: a source with one `COMMENT ON TABLE` and one `COMMENT ON COLUMN`. Assert both round-trip into the rebuilt catalog.

## Quoted referenced tables in `referenced_tables`

`commons.schema.referenced_tables` parses `FOREIGN KEY (<col>) REFERENCES <name>` and matches only bare identifiers for `<name>`. A DDL like `REFERENCES "tab"(id)` is missed, so `commons.schema.topological_order` could lose the parent-to-child edge and a consumer's INSERT could trip the FK at runtime. ChunkHound uses bare identifiers, so the gap does not bite the motivating workload, and the front gate does not currently refuse this shape.

**Fix shape.**

1. Extend the regex inside `commons.schema`: `r'FOREIGN\s+KEY\s*\([^)]*\)\s*REFERENCES\s+("(?:[^"]|"")+"|\w+)'`.
2. Strip surrounding quotes (and un-double any embedded `""`) inside `referenced_tables` so the captured name matches the unquoted `table_ddls` key.

Regression test: a parent table whose name is a SQL reserved word (DuckDB serializes it quoted) and a child FK-referencing it. Assert `topological_order` orders parent before child and the resulting INSERT plan resolves the FK.

## DiskANN or alternative ANN backends

ChunkHound writes HNSW via `duckdb-extension-vss`. Switching to DiskANN (or another on-disk ANN structure) would change the index format, break ChunkHound's read path, and require a coordinated change in ChunkHound itself. The motivating workload for commons is "support tools that operate on what ChunkHound writes," not "replace the ANN."

**Fix shape.**

A coordinated change in ChunkHound on the read side is the load-bearing piece. On the substrate side the implementation shape is straightforward: `commons.vss.load_bundled_vss` already knows how to load extension binaries from disk, and any downstream recipe format would gain an `index_kind` discriminator so the recreate step knows which `CREATE INDEX` syntax to emit. The contract with the consumer (which backend ChunkHound reads from) matters more than the substrate implementation.

## `PRAGMA hnsw_compact_index('<index>')`

The `vss` extension provides an in-place HNSW compaction pragma that prunes tombstones from the index without rebuilding the whole database. The substrate does not expose a primitive for this because:

1. The pragma still loads the HNSW into RAM (so it doesn't help a small-RAM consumer story).
2. It doesn't reclaim space outside the HNSW. The ChunkHound bloat shape is orphaned-used blocks from past HNSW serializations, not live-but-tombstoned entries in the current one, so the pragma touches the wrong region for the motivating workload.

The pragma is the right tool when an HNSW has accumulated deletes; it is not the tool when the source database has accumulated orphaned blocks across many HNSW lifecycles.

**Fix shape.**

For a tombstone-heavy workload (high delete volume rather than the orphaned-block shape), wiring this in is a new commons primitive, not a flag on an existing one. A `commons.vss.compact_hnsw_index(conn, index_name)` that opens read-write, `LOAD`s `vss`, and runs `PRAGMA hnsw_compact_index('<index>')` would suffice. RAM profile, locking, and result schema all differ from the rebuild path the current primitives support, so callers that need it would compose it explicitly rather than expecting `recreate_hnsw_index` to cover it.

## Out-of-core HNSW build

`vss` requires the HNSW to fit fully in RAM at both build and query time. There is no streaming-build or mmap-backed path inside `vss`; the index either fits or doesn't. `commons.vss.recreate_hnsw_index` inherits that constraint as a precondition on the connection's available memory. The substrate does not work around it; consumers that need a small-RAM path defer the rebuild to a RAM-capable machine, not invent an out-of-core build.

**Fix shape.**

The fix lives in `vss`, not in commons. If `vss` grows a streaming-build path, `commons.vss.recreate_hnsw_index` carries it through transparently; no commons-side change is required beyond verifying the new path on a representative source.
