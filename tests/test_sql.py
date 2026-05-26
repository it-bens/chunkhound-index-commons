from __future__ import annotations

import pytest

from chunkhound_index_commons.sql import (
    escape_sql_literal,
    is_bare_identifier,
    quote_identifier,
)


@pytest.mark.parametrize(
    ("raw", "escaped"),
    [
        ("plain", "plain"),
        ("o'reilly", "o''reilly"),
        ("''", "''''"),
        ("", ""),
        ("two 'quotes' here", "two ''quotes'' here"),
    ],
)
def test_escape_sql_literal(raw: str, escaped: str) -> None:
    assert escape_sql_literal(raw) == escaped


@pytest.mark.parametrize(
    ("raw", "quoted"),
    [
        ("plain", '"plain"'),
        ('he said "hi"', '"he said ""hi"""'),
        ("", '""'),
        ('"', '""""'),
    ],
)
def test_quote_identifier(raw: str, quoted: str) -> None:
    assert quote_identifier(raw) == quoted


@pytest.mark.parametrize(
    "name",
    [
        "plain",
        "_leading_underscore",
        "with123digits",
        "MixedCase",
        '"quoted"',
        '"with ""embedded"" quotes"',
    ],
)
def test_is_bare_identifier_accepts(name: str) -> None:
    assert is_bare_identifier(name)


@pytest.mark.parametrize(
    "expr",
    [
        "CAST(col AS FLOAT[4])",
        "col + 1",
        "func(x, y)",
        "",
        "1col",
        "with space",
        '"unterminated',
    ],
)
def test_is_bare_identifier_rejects(expr: str) -> None:
    assert not is_bare_identifier(expr)
