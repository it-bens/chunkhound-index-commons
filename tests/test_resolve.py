from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from chunkhound_index_commons.resolve import (
    DUCKDB_MAGIC,
    ROOT_JSON_SUFFIX,
    is_duckdb_file,
    resolve_chunkhound_source,
)


def _make_duckdb_file(path: Path) -> None:
    conn = duckdb.connect(str(path))
    try:
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.execute("CHECKPOINT")
    finally:
        conn.close()


def test_is_duckdb_file_positive(tmp_path: Path) -> None:
    db = tmp_path / "real.duckdb"
    _make_duckdb_file(db)
    assert is_duckdb_file(db)


def test_is_duckdb_file_rejects_non_existent(tmp_path: Path) -> None:
    assert not is_duckdb_file(tmp_path / "missing.duckdb")


def test_is_duckdb_file_rejects_directory(tmp_path: Path) -> None:
    assert not is_duckdb_file(tmp_path)


def test_is_duckdb_file_rejects_random_binary(tmp_path: Path) -> None:
    fake = tmp_path / "notduckdb.bin"
    fake.write_bytes(b"\x00" * 64)
    assert not is_duckdb_file(fake)


def test_is_duckdb_file_rejects_short_file(tmp_path: Path) -> None:
    short = tmp_path / "short.bin"
    short.write_bytes(b"DUCK")  # less than 12 bytes total
    assert not is_duckdb_file(short)


def test_is_duckdb_file_magic_position(tmp_path: Path) -> None:
    # `DUCK` at byte 0 instead of byte 8 is not a DuckDB file. Guards against
    # a regression that checks magic at the wrong offset.
    misplaced = tmp_path / "wrong_offset.bin"
    misplaced.write_bytes(DUCKDB_MAGIC + b"\x00" * 8)
    assert not is_duckdb_file(misplaced)


def test_resolve_passthrough_for_files(tmp_path: Path) -> None:
    db = tmp_path / "real.duckdb"
    _make_duckdb_file(db)
    assert resolve_chunkhound_source(db) == db


def test_resolve_passthrough_for_nonexistent_path(tmp_path: Path) -> None:
    # `_resolve_source` does not stat for existence; it returns non-directory
    # paths unchanged so the caller's own existence check fires later with
    # the original path in the error message.
    missing = tmp_path / "missing.duckdb"
    assert resolve_chunkhound_source(missing) == missing


def test_resolve_valid_chunkhound_dir(chunkhound_dir: Path) -> None:
    expected = chunkhound_dir / "chunks.db"
    assert resolve_chunkhound_source(chunkhound_dir) == expected


def test_resolve_empty_directory_raises(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError, match="no DuckDB database found"):
        resolve_chunkhound_source(empty)


def test_resolve_directory_with_orphan_dbs_lists_candidates(tmp_path: Path) -> None:
    # Two DuckDB files but no `.root.json` sidecar — caller has to disambiguate.
    _make_duckdb_file(tmp_path / "a.duckdb")
    _make_duckdb_file(tmp_path / "b.duckdb")
    with pytest.raises(FileNotFoundError, match="did you mean") as exc:
        resolve_chunkhound_source(tmp_path)
    msg = str(exc.value)
    assert "a.duckdb" in msg
    assert "b.duckdb" in msg


def test_resolve_directory_with_two_sidecars_lists_candidates(tmp_path: Path) -> None:
    # Two valid sidecar pairs → ambiguous, raise listing both.
    _make_duckdb_file(tmp_path / "first.db")
    (tmp_path / ("first.db" + ROOT_JSON_SUFFIX)).write_text("{}")
    _make_duckdb_file(tmp_path / "second.db")
    (tmp_path / ("second.db" + ROOT_JSON_SUFFIX)).write_text("{}")
    with pytest.raises(FileNotFoundError, match="did you mean"):
        resolve_chunkhound_source(tmp_path)


def test_resolve_sidecar_without_matching_db_falls_back(tmp_path: Path) -> None:
    # A `.root.json` with no matching DuckDB sibling is ignored. If another
    # standalone DuckDB file exists, the dir resolves through the candidates
    # path (ambiguous), not the sidecar path.
    (tmp_path / ("orphan.db" + ROOT_JSON_SUFFIX)).write_text("{}")
    _make_duckdb_file(tmp_path / "real.duckdb")
    with pytest.raises(FileNotFoundError, match="did you mean"):
        resolve_chunkhound_source(tmp_path)
