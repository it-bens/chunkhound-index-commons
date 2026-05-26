# Surface Shapes (reference)

Four human-prose surfaces in scope here: root `README.md`, `CONTRIBUTING.md`, `docs/architecture.md` (when present), and `docs/out-of-scope.md` (when present). AGENTS.md is covered by `references/agents-md.md`; code comments live with `writing-python-code`.

## Root README

**Audience:** an experienced Python developer evaluating commons for task-fit or learning its API.

**Sections (in order):**

1. Title + one-paragraph pitch (what commons is; what it works on; who consumes it)
2. Submodules — table mapping each submodule to its job; tells the reader where to look without reading the code
3. Install — minimal `uv add chunkhound-index-commons` plus the floor-pin note (commons owns `duckdb` / `duckdb-extension-vss` floors so consumers don't pin them)
4. Versioning — SemVer + the contract on floor moves
5. Compatibility limitations inherited from the source primitives — terse list of inherited gaps (regex limitations, HNSW knobs not surfaced by pragma)
6. License — single line + link to `LICENSE`

**Delegate, don't expand.** Deeper structure delegates to `docs/architecture.md` if it exists. The README does not restate the front-gate reasoning or the vss-bundling rationale; it points at architecture.md and stops. Setup commands live in CONTRIBUTING.md; the README does not duplicate them.

**No self-describing intro.** The README does not open with "This document covers the commons library". The H1 already names the topic. The first sentence carries the pitch (what it does + who consumes it).

## CONTRIBUTING.md

**Audience:** a contributor setting up the project locally and reading the release process.

**Sections (in order):**

1. Setup — `uv sync --extra dev`, `uv run pre-commit install`
2. Local checks — `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy src/`, `uv run typos`
3. The shopware fixture — sibling-repo lookup pattern, `$CHUNKHOUND_INDEX_COMMONS_SHOPWARE_FIXTURE` env override, `pytest.skip` fallback
4. CI workflows — per-workflow table of jobs and what they run
5. Release process — bump version, commit, tag, push; trusted-publisher OIDC flow
6. Before the first release — one-time setup of GitHub repo + PyPI project + trusted-publisher binding

CONTRIBUTING.md does not restate the README's submodule table or the AGENTS.md layout tree. Setup commands appear here, not in the README.

## docs/architecture.md (when present)

**Audience:** a reader who has already read the README and is now investigating the substrate's internals — typically a future merger session, a maintainer extending commons, or a downstream consumer debugging an unexpected refusal.

**Job:** mechanism, not pitch. Why each primitive looks the way it does; what DuckDB and ChunkHound facts shape it; what each refusal guards against. Per-case reasoning for refused / dropped / not-pursued items lives in `out-of-scope.md`; architecture.md's §Not supported section enumerates the refused cases briefly and points at `out-of-scope.md §<topic>` for each.

**Sections (in order):**

1. Why these primitives (rationale: what the substrate guards consumers against; the DuckDB FK race that `topological_order` exists to defeat; the catalog DDL strip that `capture_hnsw_metrics` exists to recover from)
2. Front-gate refusal (what `reject_unsupported_objects` enforces and why each refusal exists)
3. HNSW metric recovery (what `pragma_hnsw_index_info()` surfaces, what it doesn't, what consumers must do with the recovered metric)
4. Bundled `vss` extension (how the binary is located and loaded from the `duckdb-extension-vss` wheel; offline-safe by design)
5. ChunkHound compatibility (the substrate facts: ChunkHound writes HNSW with `metric='cosine'`, ChunkHound's drop-recreate HNSW churn shapes which rebuild approaches work, ChunkHound stores its index as a directory with a `*.root.json` sidecar)
6. Not supported (and why) — brief enumeration of refused cases, each pointing at the matching `out-of-scope.md §<topic>` for full reasoning and fix shape

**No self-describing intro.** Do not open with "This document describes the substrate primitives. For X see README." The H1 already names the topic. Cross-references attach inline to the paragraph that benefits from them, not to a meta-preface.

**No content the README already carries.** If a sentence appears in the README, architecture.md links to it via `(README §<heading>)` rather than restating. The README owns the pitch and submodule table; architecture.md owns the mechanism.

**No per-case reasoning out-of-scope.md owns.** §Not supported is the enumeration surface; the deep reasoning lives in out-of-scope.md. A bullet here is "Generated columns. (see out-of-scope.md §Generated columns)" not a paragraph restating why generated columns are refused.

## docs/out-of-scope.md (when present)

**Audience:** a maintainer answering "why doesn't commons handle X?" or "what would it take to broaden scope to X?".

**Job:** per-topic catalog. Each refusal, drop, latent edge, or rejected approach gets one `##` section that owns both the why-not AND the fix shape (when one applies). One concept, one section, both aspects on the same surface.

**Section shape (each `##` heading):**

1. Why-not prose: one or two paragraphs naming the refusal mechanism (catalog function, regex, raise site) and the reason scope was not widened.
2. `**Fix shape.**` lead-in (optional): a numbered list of concrete steps to close the gap, followed by a regression-test sentence. Omit when no fix shape applies (structural property, downstream-of-vss limitation); say so in one sentence instead.

**Structure is flat.** No `###`-level groupings of topics. Order conveys grouping: refused source shapes, then silently-dropped metadata, then latent code edges, then alternative approaches considered.

**Do not split a topic across files.** A separate "fix-shape" sibling doc creates triangular duplication: the topic appears on both surfaces with overlapping prose, and single-surface discipline does not survive normal edits. Both aspects of one topic stay in one section here.

**No self-describing intro.** Same rule as README and architecture.md. The H1 + the opening one-sentence frame are the whole intro.

## §Contracts H/R/NC pattern (when an invariant emerges)

Commons is small enough today that the README and (potential) architecture.md cover the surface without formal contract sections. If an invariant emerges that the code actively enforces (a refused input, a documented residual risk, a precondition the caller owns), promote it to a `## Contracts` section under architecture.md using the **Handled / Refused / Not covered** skeleton verbatim:

```markdown
## Contracts

### {Invariant name}

**Handled.** {What the submodule does to satisfy the invariant. One sentence per case the implementation covers.}

- {Case 1.}
- {Case 2.}

**Refused.** {What the submodule rejects rather than handle. The refusal is part of the contract.}

- {Refused case 1, with the error or exception the caller sees.}

**Not covered.** {What the submodule does not address. The residual risk the caller carries.}

- {Uncovered case 1, with the consequence if the caller hits it.}
```

Every invariant has rows in all three buckets, even if a bucket has only "none" — explicit "none" is a contract, an absent bucket is a gap.

### §Limitations anti-pattern

A §Limitations heading is a §Contracts entry in disguise whenever the named constraint is actively enforced by code. The signal: a paragraph that says "the substrate does not handle X" right next to a function that detects, refuses, or rewrites X. The detection is the contract; "limitation" is the wrong frame.

The current "Compatibility limitations inherited from the source primitives" section in README enumerates inherited gaps that the substrate does *not* actively guard against (the regex truncates, the pragma doesn't surface `M`/`ef_construction`, ChunkHound uses bare identifiers so the regex case never bites in practice). These are genuine limitations, not contracts — promotion to a §Contracts section is wrong unless code starts actively enforcing them.
