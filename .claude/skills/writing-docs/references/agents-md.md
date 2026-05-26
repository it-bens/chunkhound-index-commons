# AGENTS.md (reference)

AGENTS.md is a pointer-only map into adjacent human prose surfaces (root README, CONTRIBUTING.md, docs/architecture.md if present, docs/out-of-scope.md if present). It is consumed by LLM coding tools (Claude Code, Codex, similar) and is opaque to humans by policy. No human-facing pitch, no welcome copy, no narrative motivation. Every bullet under `## Invariants enforced by code` is a pointer `(README §X)` / `(CONTRIBUTING.md §Y)` / `(architecture.md §Z)` / `(out-of-scope.md §W)` or it gets deleted. Hard ceiling: 30 lines outside section headers, 3 to 8 bullets per section.

## LLM-only discipline

The file's audience is the tool that auto-loads it on session start. A reader who is not that tool should bounce off. Banned content:

- Project pitch / "What this does" narrative
- Install steps, command examples (those belong in README / CONTRIBUTING.md)
- Step-by-step explanation of primitive rationale (architecture.md owns that)
- Emoji-decorated section headers
- Motivation sentences attached to bullets
- "For details, see X" prefaces in the body — the bullet ends with the pointer, no preamble

## Skeleton

```markdown
# AGENTS.md

## Layout

```
<directory tree with one-line role per node>
```

## Submodule → symbols

| Submodule | Public | Module-internal |
|---|---|---|
| ... | ... | ... |

## When to modify

| Task | File / symbol |
|---|---|
| ... | ... |

## Invariants enforced by code

- <one-line invariant> (README §<heading>)
- ...

## Build / verify

<commands the agent runs to validate>
```

The `## Layout` / `## Submodule → symbols` / `## When to modify` sections carry navigation. The `## Invariants enforced by code` section carries warnings (the bullets that change behavior on edit). `## Build / verify` carries the verification commands.

## Bullet discipline (`## Invariants enforced by code`)

Every bullet ends with `(README §<heading>)`, `(CONTRIBUTING.md §<heading>)`, `(architecture.md §<heading>)`, or `(out-of-scope.md §<heading>)` pointing at a real heading. The bullet states the rule; the linked surface carries the *why*.

- **No motivation in the bullet.** Motivation lives in README or architecture.md. AGENTS.md only points at it.
- **Front-load by stakes.** The first bullet under `## Invariants enforced by code` carries the most attention weight. Order by stakes, not by source-file order.
- **Cross-refs use `§<heading name>`, never line numbers, never anchor links.** Headings survive edits; line numbers don't.
- **3 to 8 bullets per section.** Twelve is a smell; prose drift is the failure mode the 30-line ceiling prevents.
- **Identifiers mirror the code.** Don't shorten `reject_unsupported_objects` to `reject` to tighten the bullet — abbreviations that drift from the identifiers defeat grep and break the pointer-to-prose coupling.

## Worked WRONG / CORRECT

```
WRONG:   - The vss extension binary lives inside the duckdb-extension-vss
           wheel under extensions/v<duckdb-version>/vss.duckdb_extension; the
           loader globs that pattern and picks the highest-sorted match so
           wheel version churn does not require a code change.
CORRECT: - vss binary is loaded from the bundled `duckdb-extension-vss`
           wheel; no INSTALL, no network. (README §Submodules → `vss.load_bundled_vss`)
```

The WRONG version explains the *why* (wheel layout, version churn). That belongs in architecture.md. The bullet's job is to flag the rule and point.

```
WRONG:   - SQL literal escape: see src/chunkhound_index_commons/sql.py:21
CORRECT: - Every interpolated SQL literal goes through
           `sql.escape_sql_literal`; every identifier through
           `sql.quote_identifier`. (README §Submodules)
```

Line numbers shift the moment anyone reformats the file. Section names survive heading-internal edits and only break on a rename — at which point the cross-ref integrity gate in SKILL.md catches the rename and forces the sweep.

## Decision Test (per bullet)

Three questions, one bullet at a time:

1. **Shape.** Does the bullet end with `(README §<heading>)`, `(CONTRIBUTING.md §<heading>)`, `(architecture.md §<heading>)`, or `(out-of-scope.md §<heading>)` pointing at a real heading, and avoid explaining *why* in the bullet itself?
2. **Provenance.** Can the rule trace to a specific incident, a recurring class of bug the project has corrected, or a load-bearing test invariant? "We might want this someday" is not provenance.
3. **Visibility.** If the rule were violated tomorrow, would the failure be visible — a test breaks, a guarantee voids, a contract refuses — or invisible (a stylistic preference)? Invisible rules are noise.

Outcomes:

- All three pass → proceed.
- No pointer → delete the bullet, or rewrite as a pointer.
- Explains motivation → move the motivation to README, architecture.md, or out-of-scope.md; leave only the rule + pointer.
- Pointer targets a vague or missing heading → fix the heading first (heading-predicts-content discipline), then repoint.
- No traceable provenance → do not add the rule. Wait for evidence to surface.
- Violation would be invisible → drop the rule; AGENTS.md is for warnings, not preferences.

## CLAUDE.md companion

`CLAUDE.md` at the project root contains the single line `@AGENTS.md`. CLAUDE.md is not authored prose; it is a one-line include directive that Claude Code resolves on session start. When AGENTS.md is created, CLAUDE.md is created adjacent. When AGENTS.md is deleted, CLAUDE.md is deleted.

## Common rationalizations to refuse

| Thought | Reality |
|---|---|
| "I'll add a one-line summary so readers don't need the README" | The summary will drift. The pointer is the discipline. |
| "An intro paragraph helps the agent orient" | The agent does not need orientation prose. The H1 + section headings are the orientation. |
| "Every entry needs the *why*" | The *why* lives in README / architecture.md. AGENTS.md only points. |
| "I'll shorten the identifier to tighten the bullet" | Abbreviations that drift from the identifiers defeat grep. |
| "Markdown emojis make sections friendlier" | AGENTS.md has no human readers to befriend. Decoration is noise. |
