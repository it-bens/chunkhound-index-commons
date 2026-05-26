from __future__ import annotations

from pathlib import Path

import duckdb
import pytest


@pytest.fixture
def chunkhound_dir(tmp_path: Path) -> Path:
    """A ChunkHound-shaped directory: one DuckDB file plus its matching `.root.json`."""
    index_dir = tmp_path / ".chunkhound"
    index_dir.mkdir()
    db = index_dir / "chunks.db"
    conn = duckdb.connect(str(db))
    try:
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.execute("CHECKPOINT")
    finally:
        conn.close()
    db.with_name(db.name + ".root.json").write_text('{"version": 1}')
    return index_dir


@pytest.fixture
def fk_chain_db(tmp_path: Path) -> Path:
    """3-table FK chain `a → b → c`. b references a; c references b."""
    db_path = tmp_path / "fk_chain.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute("CREATE TABLE a (id INTEGER PRIMARY KEY)")
        conn.execute(
            "CREATE TABLE b (id INTEGER PRIMARY KEY, a_id INTEGER, "
            "FOREIGN KEY (a_id) REFERENCES a(id))"
        )
        conn.execute(
            "CREATE TABLE c (id INTEGER PRIMARY KEY, b_id INTEGER, "
            "FOREIGN KEY (b_id) REFERENCES b(id))"
        )
        conn.execute("INSERT INTO a SELECT range FROM range(5)")
        conn.execute("INSERT INTO b SELECT range, range FROM range(5)")
        conn.execute("INSERT INTO c SELECT range, range FROM range(5)")
        conn.execute("CHECKPOINT")
    finally:
        conn.close()
    return db_path


@pytest.fixture
def hnsw_db(tmp_path: Path) -> Path:
    """A DuckDB file with one HNSW index, default `l2sq` metric."""
    from chunkhound_index_commons.vss import bundled_vss_path

    vss_path = bundled_vss_path()
    db_path = tmp_path / "hnsw.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(f"LOAD '{vss_path}'")
        conn.execute("SET hnsw_enable_experimental_persistence = true")
        conn.execute("CREATE TABLE vectors (id INTEGER, embedding FLOAT[4])")
        conn.execute(
            "INSERT INTO vectors SELECT range, "
            "[random(), random(), random(), random()]::FLOAT[4] FROM range(20)"
        )
        conn.execute("CREATE INDEX vec_idx ON vectors USING HNSW (embedding)")
        conn.execute("CHECKPOINT")
    finally:
        conn.close()
    return db_path


@pytest.fixture
def cosine_hnsw_db(tmp_path: Path) -> Path:
    """A DuckDB file with one HNSW index, explicit `metric = 'cosine'`."""
    from chunkhound_index_commons.vss import bundled_vss_path

    vss_path = bundled_vss_path()
    db_path = tmp_path / "cosine.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(f"LOAD '{vss_path}'")
        conn.execute("SET hnsw_enable_experimental_persistence = true")
        conn.execute("CREATE TABLE vectors (id INTEGER, embedding FLOAT[4])")
        conn.execute(
            "INSERT INTO vectors SELECT range, "
            "[random(), random(), random(), random()]::FLOAT[4] FROM range(20)"
        )
        conn.execute(
            "CREATE INDEX cos_idx ON vectors USING HNSW (embedding) WITH (metric = 'cosine')"
        )
        conn.execute("CHECKPOINT")
    finally:
        conn.close()
    return db_path


_SHOPWARE_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "shopware-cli-chunks.duckdb"


@pytest.fixture
def shopware_cli_index() -> Path:
    """Real-world ChunkHound index of github.com/shopware/shopware-cli.

    A ~204 MiB DuckDB artifact committed under `tests/fixtures/` via Git LFS.
    """
    if not _SHOPWARE_FIXTURE.is_file():
        raise FileNotFoundError(
            f"shopware-cli fixture missing at {_SHOPWARE_FIXTURE}; run `git lfs pull` to fetch it"
        )
    return _SHOPWARE_FIXTURE
