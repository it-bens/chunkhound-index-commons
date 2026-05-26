# Contributing

## Setup

```bash
uv sync --extra dev              # Python toolchain (mypy, pytest, ruff, typos, pre-commit)
uv run pre-commit install        # wires the git pre-commit hook (one-time per clone)
```

Python 3.10 through 3.14 supported. macOS and Linux are tested.

The pre-commit hook runs ruff, ruff-format, typos, mypy, and pytest on every commit. Bypass with `git commit --no-verify` when you need to ship a WIP commit; CI still runs the same checks.

## Local checks

```bash
uv run pytest
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run mypy src/
uv run typos
```

CI runs the same commands.

### Tooling notes

- **Ruff**: `E W F I B C4 UP ARG SIM PTH`, line length 100, `E501` ignored.
- **MyPy**: strict; `tests.*` relaxed; `duckdb`, `duckdb_extension_vss` missing-imports ignored. The package ships `py.typed` so consumers' mypy sees the annotations.
- **Pytest**: discovers `tests/`. Three integration tests use a real ChunkHound artifact (`shopware_cli_index`) committed under `tests/fixtures/` via Git LFS.
- **Typos**: config at `.typos.toml`.

## The shopware fixture

The `shopware_cli_index` fixture is a real ChunkHound index of [shopware/shopware-cli](https://github.com/shopware/shopware-cli), committed at `tests/fixtures/shopware-cli-chunks.duckdb`. It is large (~204 MiB), so it is tracked with Git LFS rather than stored inline in Git history.

A normal `git clone` with Git LFS installed fetches it automatically. If the file is missing (LFS not installed at clone time), run `git lfs pull` to download it. `tests/conftest.py` raises `FileNotFoundError` rather than skipping when the file is absent, so a misconfigured LFS checkout fails loudly instead of silently dropping the three integration tests.

## CI workflows

Two workflows under `.github/workflows/`. All third-party actions are SHA-pinned with `# vX.Y.Z` comments so Renovate can update them later.

### ci.yml

Runs on every push to `main` and every PR targeting `main`. Five parallel jobs:

| Job         | What                                                                                |
|-------------|-------------------------------------------------------------------------------------|
| `lint`      | `ruff check` and `ruff format --check`                                              |
| `typecheck` | `mypy src/`                                                                         |
| `test`      | `pytest` with coverage on a Python 3.10 / 3.11 / 3.12 / 3.13 / 3.14 matrix          |
| `typos`     | `typos` against the repo                                                            |
| `build`     | `uv build`; uploads wheel + sdist as a `dist` artifact (14-day retention)           |

Coverage is reported but not gated. The `build` job runs independently of the others, so PR reviewers can download a wheel even when other jobs fail. The `test` job checks out Git LFS so the `shopware_cli_index` integration tests run against the real fixture.

### release.yml

Triggers on a `v*.*.*` tag push or manual `workflow_dispatch` against a tag ref.

1. Verifies the ref is a tag.
2. Verifies the tag (minus the `v` prefix) matches `pyproject.toml`'s `version`.
3. Builds wheel + sdist.
4. Publishes to PyPI via Trusted Publisher (OIDC; no PyPI token in the repo).
5. Creates a GitHub Release with the wheel + sdist attached. Release notes are not auto-generated; edit them on GitHub afterward.

## Release process

To cut a release:

1. Bump `version` in `pyproject.toml` (for example, `0.1.0` to `0.2.0`) and update `CHANGELOG.md`.
2. Commit, push, wait for CI to pass on `main`.
3. Tag and push: `git tag v0.2.0 && git push origin v0.2.0`.
4. The release workflow publishes to PyPI and creates a GitHub Release.
5. Open the Release on GitHub and write the release notes.

To re-trigger from a tag manually (for example, after a transient PyPI failure): GitHub Actions, then Release, then Run workflow, then pick the tag from the ref dropdown.

## Before the first release

`chunkhound-index-commons` v0.1.0 needs three one-time setup steps before the release workflow can publish:

1. Create the GitHub repo `it-bens/chunkhound-index-commons` and push the initial commit.
2. Create a PyPI project for `chunkhound-index-commons` (reserve the name; an empty project is fine).
3. Bind the GitHub repo as a Trusted Publisher for the PyPI project, scoped to `release.yml` and environment `pypi`.

After that, tagging `v0.1.0` and pushing the tag triggers the full publish flow.
