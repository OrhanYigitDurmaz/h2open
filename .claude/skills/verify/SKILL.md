---
name: verify
description: Run every lint, format, type, import-boundary and test check for the h2open backend (ruff, basedpyright, import-linter, pytest) and frontend (prettier, eslint, svelte-check), regenerate the API docs (docs/openapi.json), then report what fails. Use when the user runs /verify or asks to verify, check or validate the code, and before committing changes.
---

# Verify h2open

Run all checks and report the results. This skill only reports: do not change
code, loosen config, or add `# noqa` / `# pyright: ignore` unless the user asks.
The one file it writes is the generated API description, `docs/openapi.json`.

## Checks

Run each command from the directory shown. Run all of them even if an earlier
one fails, so the user sees every problem at once. The backend and frontend
groups are independent and can run in parallel.

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

Backend tests need Postgres. If `docker compose ps postgres` shows it is not
running, start it with `docker compose up -d --wait postgres` (from the repo
root) and say so. Tests use a separate `<POSTGRES_DB>_test` database that
they recreate on every run.

## Scope

- With no argument, run everything.
- `/verify backend` or `/verify frontend` runs only that half.

## Config is intentionally strict

The backend uses ruff `select = ["ALL"]` and basedpyright
`typeCheckingMode = "all"`. Failures are expected to be real issues; never
suggest relaxing `pyproject.toml` as the fix. If a rule is genuinely wrong for
one line, the right fix is a targeted suppression with a reason, and the user
decides that.

## Report

Start with a one-line verdict: everything passes, or how many checks failed.
Then a table with one row per check (pass/fail, plus error count when failing).
For the API docs row, say "updated" or "unchanged". For each failure, list the
file:line, the rule code and a short fix suggestion. Group repeated rule violations instead of listing each one.
Mention `uv run ruff check --fix .`, `uv run ruff format .` or `bun run format`
when they would fix the reported issues automatically.
