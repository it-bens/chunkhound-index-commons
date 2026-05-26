"""ChunkHound index directory resolution by DuckDB header magic.

A ChunkHound index lives in a directory with one DuckDB database file and a
sidecar JSON file (`<name>.root.json`). `resolve_chunkhound_source` lets a
consumer accept either the database file directly or that directory, and
identifies the database file by its `DUCK` magic bytes rather than by
filename.
"""

from __future__ import annotations

from pathlib import Path

DUCKDB_MAGIC = b"DUCK"
ROOT_JSON_SUFFIX = ".root.json"


def is_duckdb_file(path: Path) -> bool:
    """True if `path` is a regular file whose header bytes 8..12 equal `DUCK`.

    DuckDB writes `DUCK` at byte offset 8 of a database file (an 8-byte
    checksum precedes it). An unreadable file is reported as not-a-database
    rather than raised, so a directory scan can survive a single broken
    sibling and still report the rest as suggestions.
    """
    if not path.is_file():
        return False
    try:
        with path.open("rb") as fh:
            header = fh.read(12)
    except OSError:
        return False
    return header[8:12] == DUCKDB_MAGIC


def resolve_chunkhound_source(source: Path) -> Path:
    """Resolve `source` to a single DuckDB file, accepting a file or a ChunkHound directory.

    A directory carrying exactly one ChunkHound index — a `<name>.root.json`
    sidecar whose sibling `<name>` is a valid DuckDB file — resolves to that
    file. Any other directory shape raises `FileNotFoundError` listing the
    DuckDB files found (by magic bytes) as suggestions. A non-directory
    `source` passes through unchanged.

    Raises:
        FileNotFoundError: `source` is a directory that does not resolve to
            a single ChunkHound index.
    """
    if not source.is_dir():
        return source

    sidecar_dbs: list[Path] = []
    for sidecar in source.glob(f"*{ROOT_JSON_SUFFIX}"):
        db = sidecar.with_name(sidecar.name[: -len(ROOT_JSON_SUFFIX)])
        if is_duckdb_file(db):
            sidecar_dbs.append(db)
    if len(sidecar_dbs) == 1:
        return sidecar_dbs[0]

    candidates = sorted(p for p in source.iterdir() if is_duckdb_file(p))
    if candidates:
        listing = "\n".join(f"  {p}" for p in candidates)
        raise FileNotFoundError(
            f"{source} is a directory; did you mean one of these DuckDB files:\n{listing}"
        )
    raise FileNotFoundError(f"no DuckDB database found in directory: {source}")
