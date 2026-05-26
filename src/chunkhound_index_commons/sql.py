"""DuckDB string-interpolation safety primitives.

DuckDB DDL does not accept parameter binding for object names or inline
literals, so DDL is built by string interpolation. These helpers double the
relevant quote characters so a name containing `"` or a literal containing
`'` survives the interpolation intact.
"""

from __future__ import annotations

import re

_BARE_IDENTIFIER_RE = re.compile(r'^(?:[A-Za-z_]\w*|"(?:[^"]|"")+")$')


def escape_sql_literal(value: str) -> str:
    """Double any embedded single quote so `value` is safe inside `'...'`."""
    return value.replace("'", "''")


def quote_identifier(name: str) -> str:
    """Wrap `name` in double quotes, doubling any embedded `"`."""
    return '"' + name.replace('"', '""') + '"'


def is_bare_identifier(name: str) -> bool:
    """True if `name` is a bare or double-quoted SQL identifier (no expressions).

    Callers use this to refuse non-column expressions where the downstream
    contract expects an identifier — for example, an HNSW recipe table that
    stores the indexed column as a single `VARCHAR` has no schema for
    arbitrary expressions like `CAST(col AS FLOAT[N])`.
    """
    return bool(_BARE_IDENTIFIER_RE.match(name))
