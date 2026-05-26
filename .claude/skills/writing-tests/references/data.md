# Test Data and Fixtures (reference)

## File dependency must be locatable from the test

External file dependencies (`open()`, `Path.read_bytes()`, fixture loaders) point to a file the reader can locate from the test file.

### Acceptable

- Synthetic fixtures defined in `tests/conftest.py` (see `chunkhound_dir`, `fk_chain_db`, `hnsw_db`, `cosine_hnsw_db`)
- `tmp_path` for files the test itself creates
- A `tests/<surface>_fixtures/` subdirectory when one fixture set is local to one test module (none today)
- `importlib.resources` for fixtures shipped inside the package (none today; commons does not ship test data)
- **Documented sibling-repo lookup with `pytest.skip` fallback.** The `shopware_cli_index` fixture is the canonical case: the artifact lives in the sibling `chunkhound-index-compactor` repo's `tests/fixtures/`, not in commons. The fixture resolves the path via `$CHUNKHOUND_INDEX_COMMONS_SHOPWARE_FIXTURE` (override) or a default sibling-repo path, and `pytest.skip` when neither resolves. The pattern is acceptable specifically because it (a) goes through a `conftest.py` fixture, (b) advertises the env override, and (c) skips rather than fails when the artifact is absent.

### Flag

- Absolute paths (`/home/user/data.duckdb`, `/tmp/chunkhound-fixture`)
- Source-tree access (`../../src/chunkhound_index_commons/vss.py` opened at test time)
- **Ad-hoc** cross-package fixture borrow without env override or skip-fallback (`../../some-tool/tests/fixtures/...` hard-coded in a test body)
- Dynamic globs over an unbounded directory
- Reading from `~/...` (the test depends on the developer's home dir)

```python
# WRONG: absolute path, flaky across machines
data = Path("/home/me/samples/index.duckdb").read_bytes()

# WRONG: ad-hoc cross-package borrow with no skip-fallback or env override
data = Path("../../chunkhound/tests/fixtures/index.duckdb").read_bytes()

# RIGHT: documented sibling-repo lookup via conftest fixture (shopware pattern)
def test_thing(shopware_cli_index: Path) -> None:
    conn = duckdb.connect(str(shopware_cli_index), read_only=True)
    # ... fixture pytest.skips when the file is not locally resolvable

# RIGHT: tmp_path for state the test creates
def test_creates_recipe(tmp_path) -> None:
    db = tmp_path / "src.duckdb"
    # ... build the DB inline using duckdb.connect
```

## Descriptive identifiers in code

String literals used as identifiers in assertions are descriptive. Opaque hex blobs make failure messages unreadable.

### Flag

- 32 consecutive hex characters used as a test-constructed identifier: `"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"`
- Repeated-character placeholders: `"0000000000000001"`, `"ffffffffffffffff"`
- Placeholder UUIDs invented for the test body

### Do NOT flag

- Identifiers read from or written to a real on-disk fixture (they mirror real shapes)
- Identifiers produced by the code under test (captured in a var named `generated`)
- Tests that specifically exercise identifier-format validation

```python
# WRONG: unreadable in a failure message
recreate_hnsw_index(conn, name="aaaaaaaa", table="bbbbbbbb", column="cccccccc", metric="cosine")

# RIGHT: descriptive
recreate_hnsw_index(conn, name="vec_idx", table="vectors", column="embedding", metric="cosine")
```

### Descriptive-name conventions

| Context | Good |
|---|---|
| Table names in inline DDL | `t`, `a`, `b`, `c`, `vectors`, `node` |
| Source / target paths | `tmp_path / "src.duckdb"`, `tmp_path / "out.duckdb"` |
| HNSW index names | `vec_idx`, `cos_idx`, `round_idx` |
| FK example tables | `owners`, `cats` (parent-child); `a`/`b`/`c` (chain); `x`/`y` (cycle) |

## Real fixture files for parsers and complex I/O

Tests exercising parsing or complex I/O read real fixture files rather than build content inline. The canonical example is `shopware_cli_index` — a real-world ChunkHound index used by the three commons integration tests (`test_shopware_metrics_all_cosine`, `test_shopware_front_gate_accepts_real_chunkhound_shape`, `test_shopware_topological_order_orders_chunks_after_files`).

### Applies when

- Test writes a multi-line DuckDB DDL blob, then reads it back, and the blob is longer than ~10 lines
- Test exercises a parser, importer, or scanner against representative input
- Test needs a DuckDB file with a specific real-world shape (HNSW metric, FK chain depth, dropped-but-not-enforced FK) that is tedious to reconstruct

### Does not apply when

- Blob is a single statement (`CREATE TABLE items AS SELECT range AS id FROM range(100)`)
- Test specifically exercises a malformed input shape (inline is clearer than a dedicated fixture per malformation)
- Content is not written to any file or stream

```python
# WRONG: 40-line inline DDL builds a synthetic ChunkHound shape
def test_topological_order_chunkhound_shape(tmp_path) -> None:
    src = tmp_path / "src.duckdb"
    conn = duckdb.connect(str(src))
    conn.execute("CREATE TABLE files (...) ...")
    # ... 38 more statements building the schema
    conn.close()
    # ... act + assert

# RIGHT: the real fixture is read from the sibling-repo location
def test_shopware_topological_order_orders_chunks_after_files(shopware_cli_index: Path) -> None:
    # fixture handles the locate-or-skip
    conn = duckdb.connect(":memory:")
    conn.execute(f"ATTACH '{shopware_cli_index}' AS src (READ_ONLY)")
    # ... act + assert
```

### Adding a new committed fixture

Commons does not vendor large fixture artifacts. The `shopware_cli_index` lives in the sibling `chunkhound-index-compactor` repo because the compactor owns the artifact's regeneration recipe (run `chunkhound index` against a fresh shopware-cli checkout) and the artifact is large (~204 MiB). If a new real-world fixture is needed:

1. Prefer locating it in the consumer that owns the regeneration recipe (the compactor for ChunkHound-shaped inputs).
2. Add a `@pytest.fixture` in `tests/conftest.py` that resolves via env override + sibling-repo default path + `pytest.skip` fallback. Mirror the existing `shopware_cli_index` shape.
3. Document the provenance in the fixture docstring (which repo owns it, how it was generated, what it represents).
4. Reference the fixture by name in the tests that need it. Don't `Path(__file__).parent / "fixtures" / "..."` directly — go through the conftest fixture so the path lives in one place.

If a small synthetic fixture suffices (FK chain, single-table HNSW, single-table view), build it inline in `conftest.py` instead — no on-disk artifact, no sibling-repo lookup.

## Helper extraction for repeated arrange code

If two or more tests repeat 5+ consecutive lines of construction with identical types and arguments, extract a fixture.

### Extraction patterns (pytest)

| Pattern | Use when |
|---|---|
| Module-local `@pytest.fixture` (defined inside the test file) | Most common. Test-module-local, single-use across that module's tests. |
| Fixture in `tests/conftest.py` | Three or more test files need the fixture. Promote the module-local fixture to conftest when the third user appears. |
| Fixture with `yield` and post-yield cleanup | Resources that need teardown (open DuckDB connections, spawned subprocesses, monkeypatch under `with`). |
| Parametrized fixture (`@pytest.fixture(params=[...])`) | When the same setup needs to run against multiple variants and every test using it wants all variants. |
| `tmp_path_factory` for session-shared expensive setup | The current `shopware_cli_index` is function-scoped because the underlying file is read-only and the fixture body is cheap. Switch only if profiling shows reopening dominates. |

### Do NOT extract

- Helper would hide the single input that varies per test (the variation is the test)
- Fewer than 5 repeated lines
- Only two current occurrences; wait for the third before extracting

```python
# WRONG: same 7-line setup repeated across three tests
def test_a(tmp_path: Path) -> None:
    db = tmp_path / "src.duckdb"
    conn = duckdb.connect(str(db))
    try:
        load_bundled_vss(conn)
        conn.execute("SET hnsw_enable_experimental_persistence = true")
        conn.execute("CREATE TABLE v (id INTEGER, e FLOAT[4])")
        conn.execute("INSERT INTO v SELECT range, [random(),random(),random(),random()]::FLOAT[4] FROM range(50)")
        conn.execute("CREATE INDEX i ON v USING HNSW (e) WITH (metric = 'cosine')")
        conn.execute("CHECKPOINT")
    finally:
        conn.close()
    # ... act + assert

# RIGHT: shared fixture; the current cosine_hnsw_db fixture in conftest.py follows this shape
@pytest.fixture
def cosine_hnsw_db(tmp_path: Path) -> Path:
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
```

### Placement

- Module-local fixtures go **above** the tests that use them (Python convention: definitions before uses).
- Conftest fixtures live in `tests/conftest.py`; pytest discovers them across the suite without explicit imports.
- Fixture names start lowercase (snake_case). The name is the parameter name in dependent tests.
- Cleanup uses `yield` + post-yield statements, or `request.addfinalizer(...)`. Avoid `finally:` outside the fixture body for teardown; the fixture lifecycle owns it.

## Production-scale large fixtures

A committed fixture exceeding a few MiB is in scope only when it exercises behavior small synthetic data cannot. Commons does not vendor any such fixture — the one real-world artifact (`shopware_cli_index`, ~204 MiB) lives in the sibling `chunkhound-index-compactor` repo and is resolved via the documented lookup pattern (env override or sibling-repo default + `pytest.skip` fallback).

### When to add another

Only when:

1. The smaller synthetic fixtures (`fk_chain_db`, `hnsw_db`, `cosine_hnsw_db`, `chunkhound_dir`) cannot exercise the path the test targets.
2. A real-world artifact is the cheapest path to that path's coverage (extension version churn, accumulated bloat patterns, real FK depth, dropped-but-not-enforced FK).
3. The size is bounded (single-digit hundreds of MiB at most; commons is a substrate library, not a fixture vault).

When the fixture's natural home is a consumer (the compactor for ChunkHound-shaped inputs, the future merger for multi-source artifacts), prefer locating it there and looking it up from commons via the documented sibling-repo pattern over vendoring it into commons.
