"""DDL inspection primitives: FK topological sort and front-gate refusal.

`topological_order` orders table names so every FK parent precedes its
children — parent-before-child INSERT is what avoids the FK race that
`COPY FROM DATABASE` hits on large FK-bearing databases.

`reject_unsupported_objects` raises before a downstream rebuild touches the
target file, for source shapes a verbatim rebuild cannot reproduce
faithfully (non-`main` schemas, views, user-defined types, generated
columns, self-referential FKs). Each refusal converts a downstream
silent-loss or opaque-crash path into a clear pre-target error.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

import duckdb

_FK_REFERENCES_RE = re.compile(r"FOREIGN\s+KEY\s*\([^)]*\)\s*REFERENCES\s+(\w+)", re.IGNORECASE)
_GENERATED_COLUMN_RE = re.compile(r"\bGENERATED\s+ALWAYS\b", re.IGNORECASE)


def referenced_tables(ddl: str) -> set[str]:
    """Return the set of table names referenced by FOREIGN KEY clauses in `ddl`.

    Matches only bare identifiers; a `REFERENCES "tab"(id)` is missed. The
    motivating ChunkHound workload uses bare identifiers; widening the
    pattern is on the fix-shape list, not implemented yet.
    """
    return {m.group(1) for m in _FK_REFERENCES_RE.finditer(ddl)}


def topological_order(table_ddls: Mapping[str, str]) -> list[str]:
    """Order table names so every FK parent precedes its children.

    `table_ddls` maps table name to its CREATE TABLE DDL. FK targets outside
    the map are ignored. Independent tables keep input order.

    Raises:
        ValueError: the FK graph contains a cycle.
    """
    deps = {
        name: referenced_tables(ddl) & (table_ddls.keys() - {name})
        for name, ddl in table_ddls.items()
    }
    ordered: list[str] = []
    placed: set[str] = set()
    remaining = list(table_ddls)
    while remaining:
        progressed = False
        for name in list(remaining):
            if deps[name] <= placed:
                ordered.append(name)
                placed.add(name)
                remaining.remove(name)
                progressed = True
        if not progressed:
            raise ValueError(f"cyclic foreign-key dependency among tables: {remaining}")
    return ordered


def reject_unsupported_objects(
    conn: duckdb.DuckDBPyConnection,
    *,
    database_name: str,
) -> None:
    """Fail hard for source shapes a verbatim rebuild cannot faithfully reproduce.

    Inspects objects inside `database_name`, the ATTACH alias under which the
    source was opened.

    Raises:
        ValueError: source contains a non-`main` schema object, a view, a
            user-defined type, a table with a generated column, or a
            self-referential foreign key.
    """
    non_main = conn.execute(
        "SELECT schema_name, table_name FROM duckdb_tables() "
        "WHERE database_name = ? AND schema_name != 'main'",
        [database_name],
    ).fetchall()
    if non_main:
        names = ", ".join(f"{s}.{t}" for s, t in non_main)
        raise ValueError(f"source contains non-main schema objects (out of scope): {names}")

    views = conn.execute(
        "SELECT view_name FROM duckdb_views() WHERE database_name = ?",
        [database_name],
    ).fetchall()
    if views:
        names = ", ".join(v for (v,) in views)
        raise ValueError(f"source contains views (out of scope): {names}")

    user_types = conn.execute(
        "SELECT type_name FROM duckdb_types() WHERE database_name = ? AND NOT internal",
        [database_name],
    ).fetchall()
    if user_types:
        names = ", ".join(t for (t,) in user_types)
        raise ValueError(f"source contains user-defined types (out of scope): {names}")

    table_rows: list[tuple[str, str]] = conn.execute(
        "SELECT table_name, sql FROM duckdb_tables() WHERE database_name = ?",
        [database_name],
    ).fetchall()
    generated = [name for name, sql in table_rows if _GENERATED_COLUMN_RE.search(sql)]
    if generated:
        raise ValueError(
            f"source contains tables with generated columns (out of scope): {', '.join(generated)}"
        )

    self_ref = conn.execute(
        "SELECT DISTINCT table_name FROM duckdb_constraints() "
        "WHERE database_name = ? "
        "AND constraint_type = 'FOREIGN KEY' "
        "AND table_name = referenced_table",
        [database_name],
    ).fetchall()
    if self_ref:
        names = ", ".join(t for (t,) in self_ref)
        raise ValueError(
            f"source contains tables with self-referential foreign keys (out of scope): {names}"
        )
