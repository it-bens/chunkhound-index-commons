"""Shared DuckDB / ChunkHound primitives.

Submodules:

- `resolve`: directory → DuckDB-file resolution for ChunkHound-shaped layouts.
- `schema`: DDL inspection — FK topological sort, front-gate refusal of
  source shapes that cannot be faithfully rebuilt.
- `sql`: DuckDB string-interpolation safety primitives.
- `vss`: vss extension loading, HNSW metric capture, HNSW index recreation.

Symbols are exported from their submodules only; there are no top-level
re-exports. Import from the submodule that owns the contract.
"""
