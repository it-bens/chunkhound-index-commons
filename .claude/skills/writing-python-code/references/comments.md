# Code Comments and Docstrings (reference)

## Classification table

| Bucket | Action |
|---|---|
| **Redundant with package docs** (70%+ wording overlap with a README section or migration doc) | Remove or compress to one line |
| **Explains-what** (paraphrases the identifier or the code below) | Remove |
| **Tutorial / novice-facing** (narrates stdlib or flow) | Remove or compress sharply |
| **Over-specified why** (five lines where one would do) | Tighten |
| **Load-bearing why** (names the failure mode the code guards against) | **Keep verbatim**; rewrite new why-comments toward this shape |
| **Public docstring** (PEP 257 for an exported function / class / dataclass) | Keep when load-bearing; compress pure paraphrase to one line, never remove from the public surface |

## When to write a docstring vs a `#` comment

- **Public symbol (exported, no leading underscore):** PEP 257 docstring. One-line if behavior is obvious from the signature plus identifier; multi-line only when the function carries non-obvious raise behavior, ordering constraint, or side effect.
- **Private helper (`_`-prefixed):** no docstring unless the helper carries a load-bearing why. A `#` comment above the body is fine when the why is point-of-use.
- **Inline why inside a function body:** `#` comment, one to four lines, sitting directly above the line it explains.

The current submodules show the pattern: `schema.reject_unsupported_objects` carries a docstring because the catalog-flag subtlety is load-bearing, `vss.recreate_hnsw_index` carries one because the precondition (vss loaded, persistence flag set) is not derivable from the signature, `sql.escape_sql_literal` carries a one-liner because the body is one line and the name is the contract.

## Load-bearing why: worked example

A load-bearing why-comment names the failure mode, gives a concrete instance, and shows what the code does to prevent it. Compare against this shape when writing or keeping a why-comment:

```python
def reject_unsupported_objects(
    conn: duckdb.DuckDBPyConnection,
    *,
    database_name: str,
) -> None:
    """Fail hard for source shapes a verbatim rebuild cannot faithfully reproduce.

    Inspects objects inside `database_name` (the ATTACH alias under which the
    source was opened). The compactor passes `"src"`; the merger will pass
    each attached source's alias in turn.

    Raises:
        ValueError: source contains a non-`main` schema object, a view, a
            user-defined type, a table with a generated column, or a
            self-referential foreign key.
    """
```

The docstring names what the function guards against (verbatim-rebuild loss), names *which* shapes it refuses (so a reader does not have to enumerate the body), and tells the caller about the parameter contract (`database_name` is required, no default — both consumers state intent at the call site). None of those facts is fully recoverable from the body alone.

A second shape is the *negative* invariant comment: justify why an obvious-looking guard is deliberately omitted. Example: `sql.escape_sql_literal` only doubles single quotes; if someone "improves" it to also escape double quotes, identifier-quoted names break. A one-line comment explaining "DuckDB DDL accepts double-quoted identifiers; only literal-text single quotes need doubling" would prevent that regression. Without that comment, the next editor will "fix" the missing escape and break correctness.

## Banned patterns

```
WRONG:   def reject_unsupported_objects(
             conn: duckdb.DuckDBPyConnection, *, database_name: str
         ) -> None:
             """Reject unsupported objects.

             Opens the catalog, finds non-main schemas, finds views, finds
             user-defined types, finds generated columns, finds self-ref FKs,
             raises if any are present.
             """
CORRECT: def reject_unsupported_objects(
             conn: duckdb.DuckDBPyConnection, *, database_name: str
         ) -> None:
             """Fail hard for source shapes a verbatim rebuild cannot faithfully reproduce.

             Raises:
                 ValueError: ... (the parts that are not obvious from the body)
             """
```

The WRONG version narrates the function body. The body already says what the function does. The docstring's job is the contract a caller cannot infer.

```
WRONG:   # See README §Submodules
         from chunkhound_index_commons.sql import escape_sql_literal
CORRECT: from chunkhound_index_commons.sql import escape_sql_literal
```

The submodule layout is documented in the README. The cross-reference inside a code comment dilutes the link's value and rots when the section renames. The README is the authoritative narrative; the code is the authoritative behavior. Pointing from code to docs gets the direction wrong.

```
WRONG:   # see src/chunkhound_index_commons/vss.py:78
CORRECT: # see src/chunkhound_index_commons/vss.py §capture_hnsw_metrics
```

Line numbers shift the moment anyone reformats. Section/symbol names survive heading-internal edits.

```
WRONG:   # increment counter by one
         i += 1
CORRECT: i += 1
```

The "explains-what" pattern. The code is shorter than the comment.

## Type hints carry contract too

A complete type signature replaces several lines of docstring. `def f(p: Path, *, database_name: str) -> None:` already states "first arg is a path, database_name is keyword-only and required, returns nothing". The docstring only needs to add what the signature can't say (raised exceptions, side effects, ordering constraints, preconditions like "vss must be loaded").

`from __future__ import annotations` is required at the top of every file. With it, `dict[str, str]`, `list[T]`, and `X | None` work on the project's 3.10 floor (the annotations are strings until something reflects on them).
