# Test Shape (reference)

## AAA structure

Tests with 5+ statements separate arrange, act, and assert phases. Assertions live after the final act, not interspersed.

### Skip

- Tests under 5 statements
- Parametrized cases with 2-3 statements in the body
- Exception-path tests (`with pytest.raises(...)` is a two-phase shape: arrange → expect+act-inside-block, which is fine)

```python
# WRONG: assertions scattered through the body
def test_capture_hnsw_metrics(hnsw_db: Path) -> None:
    conn = duckdb.connect(str(hnsw_db), read_only=True)
    assert conn is not None                           # trivial mid-arrange assertion
    load_bundled_vss(conn)
    metrics = capture_hnsw_metrics(conn)
    assert isinstance(metrics, dict)                  # trivial post-act assertion
    conn.close()
    assert metrics == {"vec_idx": "l2sq"}

# RIGHT: arrange, act, assert
def test_capture_hnsw_metrics_default_l2sq(hnsw_db: Path) -> None:
    # Arrange
    conn = duckdb.connect(str(hnsw_db), read_only=True)
    try:
        load_bundled_vss(conn)

        # Act
        metrics = capture_hnsw_metrics(conn)
    finally:
        conn.close()

    # Assert
    assert metrics == {"vec_idx": "l2sq"}
```

Comment banners are optional; blank lines between phases are enough when sections are short.

## No conditional logic in tests

Test bodies do not contain conditional logic that picks between assertions.

### Prohibited

- `if`/`else` selecting which assertion runs
- `match` dispatching on test expectations
- Loops with per-iteration branching on expectations
- Ternary-style `(a if cond else b)` for assertion control flow

### Carve-outs

Not violations:

| Pattern | Why |
|---|---|
| `with pytest.raises(...)` for error-path tests | Idiomatic pytest dispatch for error-vs-success. Bounded, single shape. |
| `for tc in cases: ...` (manual loop) | Replace with `@pytest.mark.parametrize`. Manual loops in tests are a smell. |
| `pytest.skip(...)` based on `sys.platform` / `runtime` checks | Platform gate, not assertion logic. The `shopware_cli_index` fixture's skip-when-not-resolvable is the canonical commons example. |
| `@pytest.mark.slow` deselected by default | Standard slow-test gate. |
| `pytest.raises(...)` short-circuiting on precondition failure | Not an author-written conditional. |

The `expect_error`-vs-success carve-out applies **only** when the success path's assertions are identical across cases. If cases need different positive assertions, split into two parametrize tables or two test functions.

```python
# WRONG: branch picks between two different positive assertions
@pytest.mark.parametrize(("name", "want_valid", "want_match"), [
    ("plain", True, "plain"),
    ('"quoted"', True, '"quoted"'),
    ("with space", False, None),
    ("1col", False, None),
])
def test_is_bare_identifier(name, want_valid, want_match) -> None:
    got = is_bare_identifier(name)
    if want_valid:
        assert got is True
        assert name == want_match
    else:
        assert got is False

# RIGHT: two tables, two test functions
@pytest.mark.parametrize("name", ["plain", '"quoted"', "_under", "MixedCase"])
def test_is_bare_identifier_accepts(name) -> None:
    assert is_bare_identifier(name)

@pytest.mark.parametrize("expr", ["with space", "1col", "CAST(x AS T)", ""])
def test_is_bare_identifier_rejects(expr) -> None:
    assert not is_bare_identifier(expr)
```

### Acceptable expect_error shape

When error vs success is the only branch and the success path has no positive assertions, `pytest.raises` inside a parametrize case works:

```python
@pytest.mark.parametrize(("ddl", "expect_error"), [
    pytest.param("CREATE INDEX i ON t USING HNSW (embedding)", None, id="well-formed"),
    pytest.param("CREATE INDEX i ON t USING HNSW", ValueError, id="missing-parens"),
])
def test_parse_hnsw_column(ddl, expect_error):
    if expect_error is None:
        parse_hnsw_column(ddl)   # must not raise
        return
    with pytest.raises(expect_error):
        parse_hnsw_column(ddl)
```

Preferred when the success path has positive assertions: split into two tests (one for success, one for failure) and skip the branching entirely. The current `tests/test_vss.py` follows the split shape.

## Assertion scope

Multiple `assert` statements in a test body are acceptable only when they verify a single logical behavior. Unrelated claims belong in separate tests.

Acceptable clusters:

- Multiple properties of one returned value (`metrics["cos_idx"] == "cosine"` plus `len(metrics) == 1` after one `capture_hnsw_metrics` call)
- Before/after state of one operation
- Related aspects of one behavior

Not acceptable:

- Create + persistence + log line + metric in one test

```python
# WRONG: four unrelated behaviors in one test
def test_recreate_hnsw_index_end_to_end(tmp_path) -> None:
    db_path = tmp_path / "out.duckdb"
    conn = duckdb.connect(str(db_path))
    load_bundled_vss(conn)
    conn.execute("SET hnsw_enable_experimental_persistence = true")
    conn.execute("CREATE TABLE v (id INTEGER, e FLOAT[4])")
    conn.execute("INSERT INTO v SELECT range, [random(),random(),random(),random()]::FLOAT[4] FROM range(10)")
    recreate_hnsw_index(conn, name="i", table="v", column="e", metric="cosine")
    metrics = capture_hnsw_metrics(conn)
    rows = conn.execute("SELECT count(*) FROM v").fetchone()
    indexes = conn.execute("SELECT count(*) FROM duckdb_indexes()").fetchone()
    conn.close()
    assert metrics == {"i": "cosine"}                                  # metric round-trip
    assert rows[0] == 10                                               # row count
    assert indexes[0] == 1                                             # index count
    assert db_path.exists()                                            # file io

# RIGHT: one behavior per test, related assertions grouped
def test_recreate_hnsw_index_round_trip(tmp_path: Path) -> None:
    # ... arrange + act ...
    assert metrics == {"round_idx": "cosine"}
```

## Parametrize over hand-rolled tables

Use `@pytest.mark.parametrize` for tables. Use `pytest.param(...)` with an `id=` when the case needs a descriptive name (regression marker, semantic label). Stack `@pytest.mark.parametrize` decorators only when the cartesian product is what you want; if you want only some combinations, build the case list explicitly.

```python
# RIGHT: parametrize with descriptive ids
@pytest.mark.parametrize(("raw", "escaped"), [
    ("plain", "plain"),
    ("o'reilly", "o''reilly"),
    pytest.param("two 'quotes' here", "two ''quotes'' here", id="multiple_quotes"),
])
def test_escape_sql_literal(raw, escaped) -> None:
    assert escape_sql_literal(raw) == escaped
```

The current `tests/test_sql.py` follows this shape.

## Naming and ordering

### Business-language names

Name after what the code does, not how.

```python
# WRONG
def test_pathlib_with_suffix_in_resolve(): ...
def test_value_error_branch(): ...

# RIGHT
def test_resolve_empty_directory_raises(): ...
def test_topological_order_rejects_cycle(): ...
```

### Test discovery

pytest discovers tests via the file pattern `test_*.py` under `tests/`, with functions prefixed `test_`. The current layout uses snake_case file names that group by submodule (`test_resolve.py`, `test_schema.py`, `test_sql.py`, `test_vss.py`). Add new test functions to the file whose submodule they exercise; create a new `test_<submodule>.py` only when a new submodule lands under `src/`.

### Order: happy → variation → config → edge → error

Within a file, order functions and parametrize cases happy → variation → config → edge → error. Soft convention; reorder only when adding new tests, not as a cleanup pass.

| Category | Indicators |
|---|---|
| Happy | No edge/error language in the name |
| Variation | `with`, `using`, `for` modifiers |
| Config | `mode`, `option`, `flag`, `setting` |
| Edge | `empty`, `null`, `zero`, `max`, `min`, `boundary` |
| Error | `rejects`, `fails`, `invalid`, `error`, `raises` |

### Execution time

If a test is noticeably slow, check for unintended external calls (network, real disk fsync), oversized fixtures, or unbounded iteration. The current suite completes in well under a second; a test that takes seconds is a signal, not a feature. The `shopware_cli_index` integration tests are the heaviest entries today; they read a real ~204 MiB ChunkHound index from the sibling `chunkhound-index-compactor` repo and pytest-skips when the artifact is not locally resolvable.
