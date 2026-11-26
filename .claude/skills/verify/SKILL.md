---
name: verify
description: Run every lint, format, type, import-boundary, dependency and test check for the h2open backend (ruff, basedpyright, import-linter, pytest), frontend (prettier, eslint, svelte-check) and desktop app (cargo fmt, clippy, test, cargo-deny, cargo-machete), regenerate the API docs (docs/openapi.json), look for duplicated code (jscpd), then report what fails. Use when the user runs /verify or asks to verify, check or validate the code, and before committing changes.
---

# Verify h2open

Run all checks and report the results. This skill only reports: do not change
code, loosen config, or add `# noqa` / `# pyright: ignore` unless the user asks.
The one file it writes is the generated API description, `docs/openapi.json`.

## Checks

Run each command from the directory shown. Run all of them even if an earlier
one fails, so the user sees every problem at once. The backend, frontend and
desktop groups are independent and can run in parallel.

### Backend (`backend/`, Python 3.14 via uv)

| Check | Command |
|---|---|
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format --check .` |
| Types | `uv run basedpyright` |
| Module boundaries | `uv run lint-imports` |
| Tests | `uv run pytest -q` |
| API docs | `uv run python -m app.cli export-openapi` |

The API docs step writes `docs/openapi.json` (OpenAPI 3.1: every endpoint,
request and response) from the code. It prints `updated …` when the API
changed and `… is up to date` otherwise. An update is not a failure, but say
so in the report: the file should be committed with the change, since the
app developers and their agents read it from the repo. The step fails only if
the command errors, e.g. because the app cannot be imported.

### Frontend (`frontend/`, SvelteKit via bun)

| Check | Command |
|---|---|
| Format + lint | `bun run lint` (prettier --check, then eslint) |
| Types | `bun run check` (svelte-kit sync + svelte-check) |

If `frontend/node_modules` is missing, run `bun install` first and say so.

### Desktop (`desktop/`, Rust + Slint via cargo)

| Check | Command |
|---|---|
| Format | `cargo fmt --check` |
| Lint + types + UI | `cargo clippy --all-targets --all-features --locked -- -D warnings` |
| Lint for Windows | `cargo clippy --all-targets --all-features --locked --target x86_64-pc-windows-gnu -- -D warnings` |
| Tests | `cargo test --all-features --locked` |
| Dependencies | `cargo deny check` |
| Unused dependencies | `cargo machete` |

Clippy also compiles `ui/*.slint` (through `build.rs`), so Slint type and
binding errors show up there. Its lint levels live in `[lints]` in
`Cargo.toml` (pedantic, nursery and cargo groups; no `unwrap`/`expect`/`panic`;
documented `unsafe`). The app ships for Windows and Linux, so clippy runs a
second time for Windows to catch code behind `cfg(windows)`. If that target
is missing, run `rustup target add x86_64-pc-windows-gnu` and say so.
The code Slint generates sits in `mod ui` in `src/main.rs` with those lints
allowed, since it cannot be changed; never move other code into that module.

`desktop/.cargo/config.toml` sets `global-min-publish-age = "7 days"`, so
cargo never resolves a crate version published less than 7 days ago (Cargo
1.100+). If a check fails because a needed version is too new, say so and
when it becomes eligible; do not override it unless the user asks.

`cargo deny check` reads `deny.toml`: RustSec vulnerabilities and unsound
crates at any depth, unmaintained direct dependencies, licenses compatible
with AGPL-3.0, and crates.io as the only source. "found N duplicate entries"
warnings come from upstream (windows-sys, hashbrown...) and do not fail the
run; mention their count only if it grows. The first run downloads the
advisory database.

`cargo deny` and `cargo machete` are separate tools. If one is missing,
install that pinned version with `cargo install --locked cargo-deny@0.22.0`
or `cargo install --locked cargo-machete@0.10.1` and say so. Before raising
either version, check the new release is at least 7 days old.

### Whole repository (repo root)

| Check | Command |
|---|---|
| Duplicate code | see below |

```sh
bunx jscpd@5.4.3 --min-lines 4 --min-tokens 50 --reporters console \
  --ignore "**/node_modules/**,**/.venv/**,**/migrations/versions/**,**/__pycache__/**,docs/**,**/target/**" \
  backend/app backend/tests frontend/src desktop/src
```

jscpd finds blocks of code repeated across files (by tokens, so renamed
variables still match). It reads Rust but not `.slint` files. The version is pinned: before raising it, check the
new release is at least 7 days old, like any other dependency. Generated
migrations and `docs/` are skipped, since they repeat by design.

This step only reports; it never fails the run. Two clones are known and
intended, so mention them only if they change:

- `customers/_models.py` and `orders/_models.py`: the order keeps its own
  copy of the delivery address, so editing a customer later does not change
  past orders.
- `purchasing/_models.py` (receipts and payments): each table has its own
  "recorded/voided by" audit columns; modules own their tables.

For any other clone, say where it is and whether it is worth merging. Merge
real copies (shared test setup, a helper written twice); keep repetition
that keeps modules independent (each module's own tables, settings, API).

Backend tests need Postgres. If `docker compose ps postgres` shows it is not
running, start it with `docker compose up -d --wait postgres` (from the repo
root) and say so. Tests use a separate `<POSTGRES_DB>_test` database that
they recreate on every run.

## Scope

- With no argument, run everything.
- `/verify backend`, `/verify frontend` or `/verify desktop` runs only that
  group.

## Config is intentionally strict

The backend uses ruff `select = ["ALL"]` and basedpyright
`typeCheckingMode = "all"`. Failures are expected to be real issues; never
suggest relaxing `pyproject.toml` (or the desktop app's `[lints]` and
`deny.toml`) as the fix. If a rule is genuinely wrong for
one line, the right fix is a targeted suppression with a reason (in Rust,
`#[expect(clippy::…, reason = "…")]`), and the user decides that.

## Report

Start with a one-line verdict: everything passes, or how many checks failed.
Then a table with one row per check (pass/fail, plus error count when failing).
For the API docs row, say "updated" or "unchanged". For the duplicate code
row, give the number of clones and whether any are new. For each failure, list the
file:line, the rule code and a short fix suggestion. Group repeated rule violations instead of listing each one.
Mention `uv run ruff check --fix .`, `uv run ruff format .`, `bun run format`,
`cargo fmt` or `cargo clippy --fix`
when they would fix the reported issues automatically.
