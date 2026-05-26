# chunkhound-index-commons

Shared DuckDB / [ChunkHound](https://github.com/chunkhound/chunkhound) primitives for tools that operate on ChunkHound index files. Nothing in this package is end-user-facing; it keeps DuckDB-string-escape, FK topological order, and HNSW metric recovery in one importable place rather than re-derived per tool.

## Submodules

| Module                             | Owns                                                                                                 |
|------------------------------------|------------------------------------------------------------------------------------------------------|
| `chunkhound_index_commons.resolve` | Directory → DuckDB-file resolution for ChunkHound-shaped index directories.                          |
| `chunkhound_index_commons.schema`  | DDL inspection: FK topological sort, front-gate refusal of source shapes a rebuild cannot reproduce. |
| `chunkhound_index_commons.sql`     | DuckDB string-interpolation safety primitives (escape, quote, bare-identifier check).                |
| `chunkhound_index_commons.vss`     | vss extension loading from the bundled binary, HNSW metric capture, HNSW index recreation.           |

No top-level re-exports. Import from the submodule that owns the symbol so the import line pins where the contract lives.

```python
from chunkhound_index_commons.schema import topological_order, reject_unsupported_objects
from chunkhound_index_commons.vss import load_bundled_vss, capture_hnsw_metrics
```

See [docs/architecture.md](docs/architecture.md) for why each primitive exists and which DuckDB and ChunkHound behaviors shape it. Refused source shapes, dropped metadata, and known regex gaps catalog at [docs/out-of-scope.md](docs/out-of-scope.md).

## Install

```bash
uv add chunkhound-index-commons
```

`chunkhound-index-commons` declares `duckdb-extension-vss>=1.5.2`, which transitively pins `duckdb` to a single file-format-compatible version. Consumers should not pin `duckdb` or `duckdb-extension-vss` themselves; commons is the single source of truth for those floors.

## Versioning

SemVer. Floor bumps to `duckdb` or `duckdb-extension-vss` that move out of the previous tested range are majors; signature changes to any module export are majors; new exports are minor.

## Compatibility limitations inherited from the source primitives

- `referenced_tables` matches only bare identifiers; a `REFERENCES "tab"(id)` is missed. The motivating ChunkHound workload uses bare identifiers. ([docs/out-of-scope.md §Quoted referenced tables in `referenced_tables`](docs/out-of-scope.md#quoted-referenced-tables-in-referenced_tables))
- `parse_hnsw_column` truncates expression keys (`CAST(col AS FLOAT[N])`). Callers that need to refuse expression keys pair it with `sql.is_bare_identifier`. ([docs/out-of-scope.md §Expression HNSW keys](docs/out-of-scope.md#expression-hnsw-keys))
- HNSW tuning beyond `metric` (`M`, `M0`, `ef_construction`, `ef_search`) is not surfaced by any pragma and is not recoverable across a rebuild. ([docs/out-of-scope.md §HNSW tuning beyond `metric`](docs/out-of-scope.md#hnsw-tuning-beyond-metric))

## License

MIT
