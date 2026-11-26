---
name: verify
description: Run every lint, format, type, import-boundary, dependency and test check for the h2open backend (ruff, basedpyright, import-linter, pytest), frontend (prettier, eslint, svelte-check) and desktop app (Clang and GCC builds with warnings as errors, Qt Test under ASan/UBSan and TSan, clang-format, clang-tidy, clazy, libFuzzer), regenerate the API docs (docs/openapi.json), look for duplicated code (jscpd), then report what fails. Use when the user runs /verify or asks to verify, check or validate the code, and before committing changes.
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

### Desktop (`desktop/`, C++23 + Qt 6 Widgets via CMake)

| Check | Command |
|---|---|
| Build: Clang, ASan + UBSan, warnings as errors | `cmake --preset dev && cmake --build --preset dev` |
| Tests under ASan + UBSan | `ctest --preset dev` |
| Tests under TSan | `cmake --preset tsan && cmake --build --preset tsan && ctest --preset tsan` |
| Build + tests with GCC | `cmake --preset release && cmake --build --preset release && ctest --preset release` |
| Format | `clang-format --dry-run --Werror src/* tests/*.cpp fuzz/*.cpp` |
| Lint | `clang-tidy -p build/dev --quiet src/*.cpp tests/*.cpp fuzz/*.cpp` |
| Qt lint (clazy) | `cmake --build --preset dev --target clazy` |
| Fuzz | `cmake --preset fuzz && cmake --build --preset fuzz`, then for each `build/fuzz/fuzz_*`: copy `fuzz/corpus/<name>/` to a scratch directory and run `<binary> -max_total_time=30 <that directory>` |

Rules for writing the code are in `desktop/AGENTS.md`; the checks enforce
most of them. What each one covers:

- **Compiler** (`h2open_options` in `CMakeLists.txt`): `-Wall -Wextra
  -Wpedantic -Wconversion -Wshadow -Wold-style-cast …` with `-Werror`, plus
  Clang's `-Wunsafe-buffer-usage` (no raw pointer arithmetic; moc output is
  exempt). `_GLIBCXX_ASSERTIONS` (and the libc++ equivalent) make
  out-of-range `[]`, `front()` on empty containers and similar abort. Qt
  macros (`QT_NO_CAST_FROM_ASCII`, `QT_DISABLE_DEPRECATED_UP_TO` …) refuse
  implicit string conversions and deprecated APIs.
- **Sanitizers**: `dev` builds everything with ASan + UBSan (leaks
  included, and any finding stops the program). `tsan` uses ThreadSanitizer,
  which cannot be combined with ASan. Qt, GLib and D-Bus are not
  instrumented, so `tests/tsan.supp` hides races *inside* those libraries
  only. Never add suppressions for our own code.
- **clang-tidy** (`.clang-tidy`): broad groups as errors, including
  `concurrency-*`; the exceptions and their reasons are listed in the file.
- **clazy**: level0–2 plus some manual checks (the list is in
  `CMakeLists.txt`), with warnings as errors.
- **Fuzzing**: one harness per parser of untrusted input, in `fuzz/`. A
  crash writes `crash-*` in the working directory; report the input and the
  sanitizer output. Do not run the fuzzer inside `fuzz/corpus/` itself, so
  the seed corpus stays small.

All builds live in `desktop/build/<preset>/` (ignored by git). Qt itself comes
from the system (Arch: `qt6-base`; Windows: the Qt online installer), not
from a package manager with a lockfile, so there is no dependency audit step
for the desktop app. clazy comes from the `clazy` package; if
`clazy-standalone` is missing, say so instead of skipping the check silently.

### Whole repository (repo root)

| Check | Command |
|---|---|
| Duplicate code | see below |

```sh
bunx jscpd@5.4.3 --min-lines 4 --min-tokens 50 --reporters console \
  --ignore "**/node_modules/**,**/.venv/**,**/migrations/versions/**,**/__pycache__/**,docs/**,**/build/**" \
  backend/app backend/tests frontend/src desktop/src
```

jscpd finds blocks of code repeated across files (by tokens, so renamed
variables still match). It reads Python, TypeScript, Svelte and C++. The version is pinned: before raising it, check the
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
suggest relaxing `pyproject.toml` (or the desktop app's warning flags and
`.clang-tidy`) as the fix. If a rule is genuinely wrong for
one line, the right fix is a targeted suppression with a reason (in C++,
`// NOLINT(check-name): reason`), and the user decides that.

## Report

Start with a one-line verdict: everything passes, or how many checks failed.
Then a table with one row per check (pass/fail, plus error count when failing).
For the API docs row, say "updated" or "unchanged". For the duplicate code
row, give the number of clones and whether any are new. For each failure, list the
file:line, the rule code and a short fix suggestion. Group repeated rule violations instead of listing each one.
Mention `uv run ruff check --fix .`, `uv run ruff format .`, `bun run format`,
`clang-format -i src/* tests/*.cpp fuzz/*.cpp` (in `desktop/`)
when they would fix the reported issues automatically.
