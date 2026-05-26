# Behavior Under Test (reference)

## Behavior, not implementation, trivial, or internal

Tests verify observable behavior of the public API.

### Do test

- Return values and raised exceptions
- Observable state changes (files written on disk, rows persisted in a DuckDB table, output streams flushed)
- Computed or derived values
- Validation logic (the `ValueError`, `FileNotFoundError`, `RuntimeError` paths in `commons.resolve`, `commons.schema`, `commons.vss`)

### Do NOT test

- Calls into dependencies. The return value already verifies the call happened.
- Module-internal helpers (`_NAME_RE`, helpers that the submodule does not export) via a dedicated test when the submodule's public API covers the behavior.
- Internal call order or algorithmic decomposition.
- Logic-free value carriers (`assert obj.field == passed_value` for a frozen dataclass that simply stored what was passed in). Test when the carrier computes a derived value.
- `assert isinstance(result, dict)` on a function whose return type is `dict[str, str]`. Trivially true; delete it or replace with a behavior assertion that uses the dict's contents.
- Pure delegation: a function that forwards to a dependency without transforming input or output; test when delegation transforms input/output or includes conditional logic.

### Carve-outs

- `with pytest.raises(...)` before the act step is fine — `pytest.raises` *is* the act for an error-path test. The two-phase shape (arrange → expect + act inside the `with` block) is idiomatic.
- Commons publishes primitives directly (no orchestrator wraps them in the way the compactor wraps its private helpers); each primitive is tested directly. `topological_order`, `referenced_tables`, `reject_unsupported_objects`, `parse_hnsw_column`, `capture_hnsw_metrics`, `recreate_hnsw_index`, `resolve_chunkhound_source`, `is_duckdb_file`, `is_hnsw_index_ddl`, `escape_sql_literal`, `quote_identifier`, `is_bare_identifier`, `bundled_vss_path`, `load_bundled_vss` are *all* public primitives — testing them directly is testing the public surface, not a private-helper exception.
- Drift-guard tests that iterate two registries and assert index-alignment or set-equality are valid behavior tests of the registry contract. The behavior under test is "registry A and registry B stay in sync as entries land." Assert via the public surface.

### Worked examples

```python
# WRONG: dict round-trip with no derivation
def test_capture_hnsw_metrics_returns_dict() -> None:
    conn = duckdb.connect(":memory:")
    load_bundled_vss(conn)
    result = capture_hnsw_metrics(conn)
    assert isinstance(result, dict)     # trivially true; the type annotation already says this

# WRONG: pure delegation
def test_load_bundled_vss_calls_execute(monkeypatch) -> None:
    called = {}
    class FakeConn:
        def execute(self, sql: str) -> None:
            called["sql"] = sql
    load_bundled_vss(FakeConn())
    assert "LOAD" in called["sql"]    # the act of loading is the test; an outcome-side check
                                       # would open a real conn and verify pragma_hnsw_index_info works

# RIGHT: validation
def test_resolve_empty_directory_raises(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError, match="no DuckDB database found"):
        resolve_chunkhound_source(empty)

# RIGHT: derived behavior
def test_capture_hnsw_metrics_explicit_cosine(cosine_hnsw_db: Path) -> None:
    conn = duckdb.connect(str(cosine_hnsw_db), read_only=True)
    try:
        load_bundled_vss(conn)
        metrics = capture_hnsw_metrics(conn)
    finally:
        conn.close()
    assert metrics == {"cos_idx": "cosine"}
```

### Seam introduction patterns when behavior is not observable

When the behavior is real but the current public API hides it, four production-code seams have surfaced as legitimate paths to observability. Each survives in production for reasons unrelated to the test — real injection points the production caller already wants. Choose the seam that matches what production wants; if none fits without contorting production code, the behavior is implementation detail and the test should be reframed or deleted instead.

| Pattern | Production-code shape | Test usage |
|---|---|---|
| Keyword `out: TextIO` parameter | Function takes `*, out: TextIO = sys.stdout`; the caller default flows through. | Test passes `out=io.StringIO()` and asserts on `.getvalue()`. |
| `monkeypatch.setattr` on a module-level attribute | Production code reads through `from .x import value`; the attribute is overridable. The existing `monkeypatch.setattr(commons_vss, "bundled_vss_path", fake)` pattern in compactor tests works because `load_bundled_vss` looks up `bundled_vss_path` from its module globals at call time. | Test `monkeypatch.setattr("chunkhound_index_commons.vss.bundled_vss_path", fake)`; auto-restored on teardown. |
| Exported pure primitive | Logic that consumers and tests both invoke is exposed as a top-level submodule function (e.g. `topological_order`, `parse_hnsw_column`). | Test exercises the primitive directly without staging a surrounding pipeline. |
| Protocol-typed constructor parameter | `class Service: def __init__(self, *, store: Storage = DiskStorage()): ...` where `Storage` is a `typing.Protocol`. Not used in commons today (no classes), but valid if a Service emerges. | Test instantiates `Service(store=FakeStorage())`; no monkeypatching. |

Anti-pattern: introducing a keyword-only parameter that no production caller actually passes, only to make the test pass. That is the same "test the private helper" smell, dressed in a parameter.

## Single behavior per test

Each test function exercises exactly one behavior. Violation signs:

- Name contains *and* (`test_capture_and_recreate_roundtrip`)
- Comment banners splitting the body into phases (`# capture`, `# recreate`, `# assert`)
- Multiple unrelated assertions after distinct act steps

```python
# WRONG: test_hnsw_lifecycle exercises three behaviors
def test_hnsw_lifecycle(tmp_path: Path) -> None:
    db_path = tmp_path / "out.duckdb"
    conn = duckdb.connect(str(db_path))
    load_bundled_vss(conn)
    conn.execute("SET hnsw_enable_experimental_persistence = true")
    conn.execute("CREATE TABLE v (id INTEGER, e FLOAT[4])")
    conn.execute("INSERT INTO v SELECT range, [random(),random(),random(),random()]::FLOAT[4] FROM range(10)")

    # recreate
    recreate_hnsw_index(conn, name="i", table="v", column="e", metric="cosine")

    # capture
    metrics = capture_hnsw_metrics(conn)
    assert metrics == {"i": "cosine"}

    # drop
    conn.execute("DROP INDEX i")
    metrics_after = capture_hnsw_metrics(conn)
    assert metrics_after == {}
```

Split into `test_recreate_hnsw_index_round_trip` and `test_capture_hnsw_metrics_after_drop`. Each test fails for one reason.

## Test redundancy

Every parametrize case and every top-level test covers a unique code path, boundary value, or regression. Key on *why* the case exists, not on *what* the input looks like.

A case earns its slot if at least one holds:

- **Unique code path**: triggers a branch no other case triggers
- **Boundary value**: exact threshold where behavior changes
- **Regression**: prevents a specific bug from returning; cite the issue or commit

If none hold, merge into an existing test with extra assertions, or delete.

### Preservation check

Before flagging a case as redundant, scan for preservation indicators:

| Indicator | Pattern |
|---|---|
| Regression marker in id | `regression`, `bug`, `issue`, `#\d+` |
| Issue tracker reference in id | `GH-`, `PR-`, commit SHA |
| Comment at site | `# regression for #123`, `# prevents the ...` |
| Parametrize id key | `"unicode_fix_#123"` |

If present, keep the case and add an explanatory comment. If absent, consolidate.

```python
# WRONG: all three cases exercise the same "doubles single quotes" branch
@pytest.mark.parametrize(("raw", "escaped"), [
    ("o'reilly", "o''reilly"),
    ("o'connor", "o''connor"),
    ("d'angelo", "d''angelo"),
])
def test_escape_sql_literal(raw, escaped):
    assert escape_sql_literal(raw) == escaped

# RIGHT: each case justifies itself by a distinct branch or boundary
@pytest.mark.parametrize(("raw", "escaped"), [
    ("plain", "plain"),                          # no quotes path
    ("o'reilly", "o''reilly"),                   # single quote present
    ("''", "''''"),                              # already-doubled boundary
    ("", ""),                                    # empty-string edge
    ("two 'quotes' here", "two ''quotes'' here"), # multiple-quote case
])
def test_escape_sql_literal(raw, escaped):
    assert escape_sql_literal(raw) == escaped
```

## Guard clause isolation

When a test targets one early-return in a function with multiple sequential guards, the arrange section satisfies every other guard so the tested guard is the only possible exit. Otherwise the test may pass because a different guard fired first; the outcome looks right and the test proves nothing.

1. Read the public function the test exercises.
2. Enumerate its sequential guard clauses.
3. If the function has 2+ guards and the test targets one, verify the arrange satisfies all others.
4. If another guard would short-circuit with the current arrange, flag.

Does not apply when: function has one guard; test explicitly covers the all-preconditions-absent path; guards produce distinguishable outcomes that the assertion discriminates.

```python
# commons.schema.reject_unsupported_objects runs five sequential guards in this order:
#   g1: non-main schema objects     → ValueError("non-main schema")
#   g2: views                       → ValueError("view")
#   g3: user-defined types          → ValueError("user-defined type")
#   g4: generated columns           → ValueError("generated column")
#   g5: self-referential FKs        → ValueError("self-referential foreign key")

# WRONG: targets g3 (UDT refusal) but g2 fires first because a view is also present
def test_reject_user_defined_types(tmp_path: Path) -> None:
    src = tmp_path / "src.duckdb"
    conn = duckdb.connect(str(src))
    try:
        conn.execute("CREATE TYPE color AS ENUM ('r', 'g', 'b')")
        conn.execute("CREATE TABLE t (id INTEGER, c color)")
        conn.execute("CREATE VIEW v AS SELECT * FROM t")    # g2 will fire, not g3
        conn.execute("CHECKPOINT")
    finally:
        conn.close()

    inspect = duckdb.connect(":memory:")
    try:
        inspect.execute(f"ATTACH '{src}' AS src (READ_ONLY)")
        with pytest.raises(ValueError, match="user-defined type"):    # actually raises "view"
            reject_unsupported_objects(inspect, database_name="src")
    finally:
        inspect.close()

# RIGHT: only g3 can fire — no schema-other-than-main, no view, no generated col, no self-ref FK
def test_reject_user_defined_types(tmp_path: Path) -> None:
    src = tmp_path / "src.duckdb"
    conn = duckdb.connect(str(src))
    try:
        conn.execute("CREATE TYPE color AS ENUM ('r', 'g', 'b')")
        conn.execute("CREATE TABLE t (id INTEGER, c color)")
        conn.execute("CHECKPOINT")
    finally:
        conn.close()

    inspect = duckdb.connect(":memory:")
    try:
        inspect.execute(f"ATTACH '{src}' AS src (READ_ONLY)")
        with pytest.raises(ValueError, match="user-defined type"):
            reject_unsupported_objects(inspect, database_name="src")
    finally:
        inspect.close()
```

The existing `test_reject_user_defined_types`, `test_reject_views`, `test_reject_generated_columns`, `test_reject_self_referential_fk`, and `test_reject_non_main_schema` already get this right — each creates exactly the offending shape with nothing else. The worked example is for review of new tests.
