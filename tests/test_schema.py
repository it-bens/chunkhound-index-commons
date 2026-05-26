from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from chunkhound_index_commons.schema import (
    referenced_tables,
    reject_unsupported_objects,
    topological_order,
)


def _attach(conn: duckdb.DuckDBPyConnection, source: Path, alias: str = "src") -> None:
    conn.execute(f"ATTACH '{source}' AS {alias} (READ_ONLY)")


def test_referenced_tables_basic() -> None:
    ddl = (
        "CREATE TABLE cats (id INTEGER, owner_id INTEGER, "
        "FOREIGN KEY (owner_id) REFERENCES owners(id))"
    )
    assert referenced_tables(ddl) == {"owners"}


def test_referenced_tables_multiple() -> None:
    ddl = (
        "CREATE TABLE link (a_id INTEGER, b_id INTEGER, "
        "FOREIGN KEY (a_id) REFERENCES a(id), "
        "FOREIGN KEY (b_id) REFERENCES b(id))"
    )
    assert referenced_tables(ddl) == {"a", "b"}


def test_referenced_tables_no_fk() -> None:
    assert referenced_tables("CREATE TABLE t (id INTEGER)") == set()


def test_topological_order_sorts_parent_before_child() -> None:
    ddls = {
        "cats": (
            "CREATE TABLE cats(id INTEGER PRIMARY KEY, owner_id INTEGER, "
            "FOREIGN KEY (owner_id) REFERENCES owners(id))"
        ),
        "owners": "CREATE TABLE owners(id INTEGER PRIMARY KEY)",
    }
    order = topological_order(ddls)
    assert order.index("owners") < order.index("cats")


def test_topological_order_three_level_chain() -> None:
    ddls = {
        "c": "CREATE TABLE c(id INTEGER, b_id INTEGER, FOREIGN KEY (b_id) REFERENCES b(id))",
        "b": "CREATE TABLE b(id INTEGER, a_id INTEGER, FOREIGN KEY (a_id) REFERENCES a(id))",
        "a": "CREATE TABLE a(id INTEGER PRIMARY KEY)",
    }
    order = topological_order(ddls)
    assert order.index("a") < order.index("b") < order.index("c")


def test_topological_order_keeps_independent_tables() -> None:
    ddls = {
        "a": "CREATE TABLE a(id INTEGER)",
        "b": "CREATE TABLE b(id INTEGER)",
        "c": "CREATE TABLE c(id INTEGER)",
    }
    assert sorted(topological_order(ddls)) == ["a", "b", "c"]


def test_topological_order_rejects_cycle() -> None:
    ddls = {
        "x": "CREATE TABLE x(id INTEGER, y_id INTEGER, FOREIGN KEY (y_id) REFERENCES y(id))",
        "y": "CREATE TABLE y(id INTEGER, x_id INTEGER, FOREIGN KEY (x_id) REFERENCES x(id))",
    }
    with pytest.raises(ValueError, match="cyclic"):
        topological_order(ddls)


def test_topological_order_ignores_unknown_fk_targets() -> None:
    # FK targets outside the map are ignored — the source might reference a
    # table the caller doesn't intend to include in the order.
    ddls = {
        "t": "CREATE TABLE t(id INTEGER, x_id INTEGER, FOREIGN KEY (x_id) REFERENCES external(id))",
    }
    assert topological_order(ddls) == ["t"]


def test_reject_accepts_clean_source(fk_chain_db: Path) -> None:
    conn = duckdb.connect(":memory:")
    try:
        _attach(conn, fk_chain_db)
        reject_unsupported_objects(conn, database_name="src")
    finally:
        conn.close()


def test_reject_non_main_schema(tmp_path: Path) -> None:
    src = tmp_path / "schemas.duckdb"
    conn = duckdb.connect(str(src))
    try:
        conn.execute("CREATE SCHEMA extra")
        conn.execute("CREATE TABLE extra.t (id INTEGER)")
        conn.execute("CHECKPOINT")
    finally:
        conn.close()

    inspect = duckdb.connect(":memory:")
    try:
        _attach(inspect, src)
        with pytest.raises(ValueError, match="non-main schema"):
            reject_unsupported_objects(inspect, database_name="src")
    finally:
        inspect.close()


def test_reject_views(tmp_path: Path) -> None:
    src = tmp_path / "views.duckdb"
    conn = duckdb.connect(str(src))
    try:
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.execute("CREATE VIEW v AS SELECT * FROM t")
        conn.execute("CHECKPOINT")
    finally:
        conn.close()

    inspect = duckdb.connect(":memory:")
    try:
        _attach(inspect, src)
        with pytest.raises(ValueError, match="view"):
            reject_unsupported_objects(inspect, database_name="src")
    finally:
        inspect.close()


def test_reject_user_defined_types(tmp_path: Path) -> None:
    src = tmp_path / "types.duckdb"
    conn = duckdb.connect(str(src))
    try:
        conn.execute("CREATE TYPE color AS ENUM ('r', 'g', 'b')")
        conn.execute("CREATE TABLE t (id INTEGER, c color)")
        conn.execute("CHECKPOINT")
    finally:
        conn.close()

    inspect = duckdb.connect(":memory:")
    try:
        _attach(inspect, src)
        with pytest.raises(ValueError, match="user-defined type"):
            reject_unsupported_objects(inspect, database_name="src")
    finally:
        inspect.close()


def test_reject_generated_columns(tmp_path: Path) -> None:
    src = tmp_path / "gen.duckdb"
    conn = duckdb.connect(str(src))
    try:
        conn.execute("CREATE TABLE g (id INTEGER, doubled INTEGER GENERATED ALWAYS AS (id * 2))")
        conn.execute("CHECKPOINT")
    finally:
        conn.close()

    inspect = duckdb.connect(":memory:")
    try:
        _attach(inspect, src)
        with pytest.raises(ValueError, match="generated column"):
            reject_unsupported_objects(inspect, database_name="src")
    finally:
        inspect.close()


def test_reject_self_referential_fk(tmp_path: Path) -> None:
    src = tmp_path / "selfref.duckdb"
    conn = duckdb.connect(str(src))
    try:
        conn.execute(
            "CREATE TABLE node (id INTEGER PRIMARY KEY, parent INTEGER, "
            "FOREIGN KEY (parent) REFERENCES node(id))"
        )
        conn.execute("CHECKPOINT")
    finally:
        conn.close()

    inspect = duckdb.connect(":memory:")
    try:
        _attach(inspect, src)
        with pytest.raises(ValueError, match="self-referential foreign key"):
            reject_unsupported_objects(inspect, database_name="src")
    finally:
        inspect.close()


def test_reject_scoped_to_named_database(tmp_path: Path) -> None:
    # `database_name` filters the catalog query — an unsupported shape in a
    # *different* attached database must not trigger refusal.
    clean = tmp_path / "clean.duckdb"
    dirty = tmp_path / "dirty.duckdb"
    duckdb.connect(str(clean)).close()
    dconn = duckdb.connect(str(dirty))
    try:
        dconn.execute("CREATE TABLE t (id INTEGER)")
        dconn.execute("CREATE VIEW v AS SELECT * FROM t")
        dconn.execute("CHECKPOINT")
    finally:
        dconn.close()

    inspect = duckdb.connect(":memory:")
    try:
        _attach(inspect, clean, alias="clean_src")
        _attach(inspect, dirty, alias="dirty_src")
        # Inspecting only `clean_src` should pass even though `dirty_src` has
        # a view.
        reject_unsupported_objects(inspect, database_name="clean_src")
        with pytest.raises(ValueError, match="view"):
            reject_unsupported_objects(inspect, database_name="dirty_src")
    finally:
        inspect.close()
