from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from chunkhound_index_commons.schema import (
    reject_unsupported_objects,
    topological_order,
)
from chunkhound_index_commons.vss import (
    bundled_vss_path,
    capture_hnsw_metrics,
    is_hnsw_index_ddl,
    load_bundled_vss,
    parse_hnsw_column,
    recreate_hnsw_index,
)


@pytest.mark.parametrize(
    "ddl",
    [
        "CREATE INDEX i ON t USING HNSW (embedding)",
        "create index i on t using hnsw (embedding)",
        "CREATE INDEX i ON t USING  HNSW (embedding) WITH (metric = 'cosine')",
    ],
)
def test_is_hnsw_index_ddl_positive(ddl: str) -> None:
    assert is_hnsw_index_ddl(ddl)


@pytest.mark.parametrize(
    "ddl",
    [
        "CREATE INDEX i ON t(col)",
        "CREATE INDEX i ON t USING ART (col)",
        "",
    ],
)
def test_is_hnsw_index_ddl_negative(ddl: str) -> None:
    assert not is_hnsw_index_ddl(ddl)


def test_parse_hnsw_column_basic() -> None:
    assert parse_hnsw_column("CREATE INDEX i ON t USING HNSW (embedding)") == "embedding"


def test_parse_hnsw_column_with_metric_clause() -> None:
    assert (
        parse_hnsw_column("CREATE INDEX i ON t USING HNSW (embedding) WITH (metric = 'cosine')")
        == "embedding"
    )


def test_parse_hnsw_column_truncates_expression() -> None:
    # Documented inherited limitation: the non-greedy capture stops at the
    # first close paren that allows the trailing `\s*\)` to match, which
    # truncates expression keys mid-clause. Callers refuse via
    # sql.is_bare_identifier rather than try to fix the regex.
    captured = parse_hnsw_column("CREATE INDEX i ON t USING HNSW (CAST(x AS FLOAT[4]))")
    assert captured == "CAST(x AS FLOAT[4]"
    from chunkhound_index_commons.sql import is_bare_identifier

    assert not is_bare_identifier(captured)


def test_parse_hnsw_column_unparseable_raises() -> None:
    with pytest.raises(ValueError, match="could not parse HNSW column"):
        parse_hnsw_column("CREATE INDEX i ON t USING HNSW")


def test_bundled_vss_path_returns_existing_file() -> None:
    path = bundled_vss_path()
    assert path.is_file()
    assert path.name == "vss.duckdb_extension"


def test_bundled_vss_path_missing_file_attribute_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import duckdb_extension_vss

    monkeypatch.setattr(duckdb_extension_vss, "__file__", None)
    with pytest.raises(RuntimeError, match="cannot locate duckdb_extension_vss"):
        bundled_vss_path()


def test_bundled_vss_path_missing_binary_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import duckdb_extension_vss

    monkeypatch.setattr(duckdb_extension_vss, "__file__", str(tmp_path / "__init__.py"))
    with pytest.raises(RuntimeError, match="no bundled vss.duckdb_extension found"):
        bundled_vss_path()


def test_load_bundled_vss() -> None:
    conn = duckdb.connect(":memory:")
    try:
        load_bundled_vss(conn)
        # If LOAD worked, pragma_hnsw_index_info() is callable (returns 0 rows).
        rows = conn.execute("SELECT count(*) FROM pragma_hnsw_index_info()").fetchone()
    finally:
        conn.close()
    assert rows is not None and rows[0] == 0


def test_capture_hnsw_metrics_default_l2sq(hnsw_db: Path) -> None:
    conn = duckdb.connect(str(hnsw_db), read_only=True)
    try:
        load_bundled_vss(conn)
        metrics = capture_hnsw_metrics(conn)
    finally:
        conn.close()
    assert metrics == {"vec_idx": "l2sq"}


def test_capture_hnsw_metrics_explicit_cosine(cosine_hnsw_db: Path) -> None:
    # Regression guard: the catalog DDL strips `WITH (...)`. The metric is
    # only recoverable via pragma_hnsw_index_info().
    conn = duckdb.connect(str(cosine_hnsw_db), read_only=True)
    try:
        load_bundled_vss(conn)
        metrics = capture_hnsw_metrics(conn)
    finally:
        conn.close()
    assert metrics == {"cos_idx": "cosine"}


def test_recreate_hnsw_index_round_trip(tmp_path: Path) -> None:
    db_path = tmp_path / "round_trip.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        load_bundled_vss(conn)
        conn.execute("SET hnsw_enable_experimental_persistence = true")
        conn.execute("CREATE TABLE vectors (id INTEGER, embedding FLOAT[4])")
        conn.execute(
            "INSERT INTO vectors SELECT range, "
            "[random(), random(), random(), random()]::FLOAT[4] FROM range(10)"
        )
        recreate_hnsw_index(
            conn, name="round_idx", table="vectors", column="embedding", metric="cosine"
        )
        conn.execute("CHECKPOINT")
        metrics = capture_hnsw_metrics(conn)
    finally:
        conn.close()
    assert metrics == {"round_idx": "cosine"}


def test_recreate_hnsw_index_escapes_identifiers(tmp_path: Path) -> None:
    # Verify that an embedded quote in the name/table survives interpolation.
    db_path = tmp_path / "escape.duckdb"
    conn = duckdb.connect(str(db_path))
    try:
        load_bundled_vss(conn)
        conn.execute("SET hnsw_enable_experimental_persistence = true")
        conn.execute('CREATE TABLE "weird ""name""" (id INTEGER, embedding FLOAT[4])')
        conn.execute(
            'INSERT INTO "weird ""name""" SELECT range, '
            "[random(), random(), random(), random()]::FLOAT[4] FROM range(5)"
        )
        recreate_hnsw_index(
            conn,
            name='also "weird"',
            table='weird "name"',
            column="embedding",
            metric="l2sq",
        )
        rows = conn.execute(
            "SELECT index_name FROM duckdb_indexes() WHERE sql ILIKE '%USING HNSW%'"
        ).fetchall()
    finally:
        conn.close()
    assert rows == [('also "weird"',)]


# --- shopware-cli integration tests ---


def test_shopware_metrics_all_cosine(shopware_cli_index: Path) -> None:
    # Real ChunkHound indexes write HNSW with metric='cosine'. Verify the
    # primitive captures it on the production-shape artifact, not just the
    # synthetic fixture.
    conn = duckdb.connect(str(shopware_cli_index), read_only=True)
    try:
        load_bundled_vss(conn)
        metrics = capture_hnsw_metrics(conn)
    finally:
        conn.close()
    assert metrics
    assert all(m == "cosine" for m in metrics.values()), metrics


def test_shopware_front_gate_accepts_real_chunkhound_shape(shopware_cli_index: Path) -> None:
    # The front gate must accept the production ChunkHound schema; a false
    # refusal here would reject real-world inputs.
    conn = duckdb.connect(":memory:")
    try:
        conn.execute(f"ATTACH '{shopware_cli_index}' AS src (READ_ONLY)")
        reject_unsupported_objects(conn, database_name="src")
    finally:
        conn.close()


def test_shopware_topological_order_orders_chunks_after_files(shopware_cli_index: Path) -> None:
    # ChunkHound's `chunks` table declares an explicit
    # `FOREIGN KEY (file_id) REFERENCES files(id)`. The `embeddings_*` tables
    # carry `chunk_id INTEGER NOT NULL` but no FK constraint in the DDL —
    # ChunkHound keeps that link at the application layer, so
    # topological_order has nothing to order against and the position of
    # embeddings_* is unconstrained. Only the FK-enforced edge is asserted.
    from chunkhound_index_commons.schema import referenced_tables

    conn = duckdb.connect(":memory:")
    try:
        conn.execute(f"ATTACH '{shopware_cli_index}' AS src (READ_ONLY)")
        rows = conn.execute(
            "SELECT table_name, sql FROM duckdb_tables() WHERE database_name = 'src'"
        ).fetchall()
    finally:
        conn.close()

    ddls = dict(rows)
    order = topological_order(ddls)

    assert "files" in order and "chunks" in order
    assert order.index("files") < order.index("chunks")

    # Every FK-declared parent (as caught by the regex) precedes its child.
    positions = {name: i for i, name in enumerate(order)}
    for name, ddl in ddls.items():
        for parent in referenced_tables(ddl) & ddls.keys():
            assert positions[parent] < positions[name], (parent, name)
