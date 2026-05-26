"""vss extension loading, HNSW metric capture, and HNSW index recreation.

DuckDB cannot create or read an HNSW index without the `vss` extension.
This module loads the bundled binary shipped by the `duckdb-extension-vss`
wheel (offline-safe, no `INSTALL`, no network), reads HNSW metric metadata
from `pragma_hnsw_index_info()`, and recreates HNSW indexes with their
recovered metric — the catalog DDL strips the `WITH (...)` clause, so
metric preservation across a rebuild requires the pragma-based recovery.

Composition note: `capture_hnsw_metrics`, `parse_hnsw_column`, and
`recreate_hnsw_index` are intentionally separate primitives. A consumer
that wants per-index recipe rows builds them by walking
`duckdb_indexes()`, filtering with `is_hnsw_index_ddl`, calling
`parse_hnsw_column` per row, looking up the metric in
`capture_hnsw_metrics`'s result, and optionally pairing with
`sql.is_bare_identifier` to refuse expression keys. The recipe table
format is the consumer's contract, not the library's.
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb

from .sql import escape_sql_literal, quote_identifier

_HNSW_RE = re.compile(r"USING\s+HNSW", re.IGNORECASE)
_HNSW_COLUMN_RE = re.compile(r"USING\s+HNSW\s*\(\s*(.+?)\s*\)", re.IGNORECASE)


def is_hnsw_index_ddl(ddl: str) -> bool:
    """True if `ddl` is a `USING HNSW` index definition."""
    return _HNSW_RE.search(ddl) is not None


def parse_hnsw_column(ddl: str) -> str:
    """Return the indexed column captured from a `USING HNSW (col)` clause.

    The capture is non-greedy and truncates at the first inner `)`, so an
    expression key like `CAST(col AS FLOAT[N])` round-trips malformed.
    Callers that need to refuse expression keys should pair this with
    `chunkhound_index_commons.sql.is_bare_identifier`.

    Raises:
        ValueError: `ddl` does not contain a parenthesised HNSW column clause.
    """
    match = _HNSW_COLUMN_RE.search(ddl)
    if not match:
        raise ValueError(f"could not parse HNSW column from index DDL: {ddl!r}")
    return match.group(1)


def bundled_vss_path() -> Path:
    """Return the filesystem path to the bundled `vss.duckdb_extension` binary.

    Locates the binary inside the installed `duckdb-extension-vss` package
    layout (`<package>/extensions/v*/vss.duckdb_extension`) and returns the
    highest-sorted match.

    Raises:
        RuntimeError: the `duckdb-extension-vss` package is not importable
            or its installed layout contains no matching binary.
    """
    import duckdb_extension_vss

    module_file = duckdb_extension_vss.__file__
    if module_file is None:
        raise RuntimeError("cannot locate duckdb_extension_vss on disk")
    pkg_root = Path(module_file).parent / "extensions"
    candidates = sorted(pkg_root.glob("v*/vss.duckdb_extension"))
    if not candidates:
        raise RuntimeError(f"no bundled vss.duckdb_extension found under {pkg_root}")
    return candidates[-1]


def load_bundled_vss(conn: duckdb.DuckDBPyConnection) -> None:
    """LOAD the bundled `vss` binary into `conn` from disk.

    Raises:
        RuntimeError: see `bundled_vss_path`.
    """
    path = bundled_vss_path()
    conn.execute(f"LOAD '{escape_sql_literal(str(path))}'")


def capture_hnsw_metrics(conn: duckdb.DuckDBPyConnection) -> dict[str, str]:
    """Return a mapping of HNSW index name to its `metric`, read from the live index.

    Requires `vss` to be loaded on `conn` (call `load_bundled_vss` first).
    Returns metrics for every HNSW index visible to `conn`; if multiple
    databases are attached, the result spans all of them. Callers that need
    to filter by database can join with `duckdb_indexes()` themselves.

    `metric` is the only HNSW build-time parameter `pragma_hnsw_index_info()`
    surfaces. The other knobs (`M`, `M0`, `ef_construction`, `ef_search`)
    are not recoverable from a built index.
    """
    rows = conn.execute("SELECT index_name, metric FROM pragma_hnsw_index_info()").fetchall()
    return dict(rows)


def recreate_hnsw_index(
    conn: duckdb.DuckDBPyConnection,
    *,
    name: str,
    table: str,
    column: str,
    metric: str,
) -> None:
    """Issue `CREATE INDEX <name> ON <table> USING HNSW (<column>) WITH (metric = '<metric>')`.

    `vss` must be loaded and `hnsw_enable_experimental_persistence` must be
    set on `conn`; both are session-level concerns the caller owns. `name`
    and `table` are wrapped via `quote_identifier`; `column` is interpolated
    verbatim so expression keys work for callers that accept them; `metric`
    is escaped via `escape_sql_literal`.
    """
    conn.execute(
        f"CREATE INDEX {quote_identifier(name)} ON {quote_identifier(table)} "
        f"USING HNSW ({column}) WITH (metric = '{escape_sql_literal(metric)}')"
    )
