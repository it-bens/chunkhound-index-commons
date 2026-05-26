# Writing Style (reference)

## Sentence and paragraph constraints

- Sentences ≤25 words, averaging 12 to 17.
- Active voice predominant. Passive only when the agent is genuinely uninteresting (`the partial target is unlinked on failure`).
- Paragraphs ≤4 sentences.

## Headings predict their content

`§<section name>` cross-refs are the navigation backbone between README, CONTRIBUTING.md, AGENTS.md, and (if they exist) architecture.md / out-of-scope.md. They break the moment a heading goes vague, so heading clarity is load-bearing rather than cosmetic.

| Heading | Verdict |
|---|---|
| `## Submodules` | Predicts content; safe to cite as `§Submodules` |
| `## Compatibility limitations inherited from the source primitives` | Predicts content; safe to cite |
| `## Bundled vss extension` | Predicts content; safe to cite |
| `## Implementation notes` | Vague; `§Implementation notes` will rot when content drifts |
| `## Details` | Vague; rename to what the section actually covers |

When you rename a heading, search for `§<old name>` across the repo and update every cross-ref in the same edit.

## Jargon discipline

Project-specific jargon is defined once at the surface that owns the term, and never re-defined. Examples currently in use:

- `§Submodules` in README defines the four-submodule split (`resolve`, `schema`, `sql`, `vss`).
- `§The shopware fixture` in CONTRIBUTING.md defines the sibling-repo lookup pattern with `pytest.skip` fallback.
- If `docs/architecture.md` is added, `§Bundled vss extension` would own the vss-bundling rationale, and `§ChunkHound compatibility` would own the ChunkHound-shape facts.

A doc surface that re-defines one of these is creating a second canonical definition that will drift from the first.

Python stdlib and language vocabulary stays undefined. The audience knows what `pathlib.Path`, `dataclass`, a `with` block, a pytest fixture, `monkeypatch`, `from __future__ import annotations`, `tmp_path`, `mypy strict`, and `ruff` are. Defining them adds noise and signals the wrong audience.

DuckDB-specific vocabulary (`ATTACH`, `pragma_hnsw_index_info()`, HNSW, `vss` extension, `duckdb_tables().sql`, `duckdb_indexes().sql`) stays undefined in body prose because commons' audience is the DuckDB-using consumer (the compactor, the future merger) that reached for the substrate after running into the DuckDB / ChunkHound interaction these primitives encode. The README pitch may briefly name the substrate target, but the body assumes DuckDB literacy.

## Numbers earn their place

Include a numeric value only when the reader cannot derive it from surrounding text. Decision test: if replacing the number with "several" or deleting it entirely loses no information, delete.

**Keep** (value carries information):

- Thresholds: `64 KiB` line cap, ChunkHound's `50`-row HNSW-batch threshold
- Version pins: `duckdb>=1.4.0,<1.5.3.dev0`, `Python >=3.10,<3.15`
- Indexing conventions: 1-based vs 0-based
- Grammar bounds: `[A-Z0-9_]{1,64}` (where the cap is load-bearing)
- Byte offsets: `DUCK` magic at byte 8 of the DuckDB header

**Strip** (value restates or invents):

- Counts labeling an enumeration the text then gives ("four-submodule split" when the four submodules follow; "all five refusals" when the five are listed)
- Speculative future cardinalities ("adding a fifth submodule", "the sixth refusal") — write "a new submodule" / "a new refusal" instead

## Reject consumer-readability heuristics

Two heuristics from consumer/editorial writing routinely surface as suggested rewrites. Both are wrong for this audience.

**Flesch-Kincaid Grade 8-12** is calibrated for editorial or consumer prose. Python library / substrate docs live at FK 10-14 and that is correct for the audience. A rewrite pass targeting FK 8-12 forces over-simplification and drops technical precision. Reject the metric, not the prose.

**Mermaid / diagram mandates** are invented constraints for this project. The README and (potential) architecture.md have zero diagrams today and no contract needs one; a "prefer diagrams" rule is precisely the *invented constraints are misinformation* failure mode. Add a diagram only when a table cannot express the relationship.

## Worked rejections

| Suggested rewrite | Rejection |
|---|---|
| "Let me rewrite this paragraph to hit Flesch-Kincaid 8" | Developer docs target FK 10-14; consumer-grade readability drops precision. |
| "A diagram would make the substrate section friendlier" | The substrate is a four-submodule table; a flowchart adds nothing the table cannot express. |
| "Giving the count upfront frames the list that follows" | The list already gives the count. The label is noise; delete it. |
| "Future-proof the rule for when a fifth submodule appears" | "Fifth" bakes in today's count and breaks on the next add. Write "a new submodule". |
| "Add an intro paragraph so readers know what the doc covers" | The H1 already names the topic. Self-describing intros are noise; the no-self-describing-intro rule applies. |
