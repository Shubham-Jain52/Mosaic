# Mosaic

Local-first, BYOK CLI: turn a GitHub repository’s PR review feedback into a **local** SQLite dataset and Chroma vector index, then run **`mosaic check`** for advisory, cited pre-push feedback grounded in your team’s past reviews.

- **Local-first data** — corpus and vectors live in the project (`mosaic.db`, `.mosaic/`).
- **Embeddings** — OpenAI, Hugging Face, OpenAI-compatible APIs, or optional **on-device fastembed** (`mosaic-cli[local]`).
- **Chat for `check`** — bring-your-own-key OpenAI-compatible API (OpenAI, Groq, Gemini compat, etc. via `CHAT_API_BASE`). Not fully offline end-to-end; local chat LLM is later ([docs/ROADMAP.md](docs/ROADMAP.md)).

## Features

- Connect one GitHub repo via PAT (`mosaic init`)
- **`mosaic build`** — full scrape of labeled comments + embedder setup + vector index
- **`mosaic sync`** — fetch PRs not yet in SQLite, vectorize only the delta
- **`mosaic check`** — auto-diff vs main → graded, cited feedback (BYOK chat)
- Comment kinds: review (inline), issue (conversation), review summaries
- Embeddings: API providers or optional **local fastembed** (embeddings only — not chat)
- Sync bookmarks in `.mosaic/sync_state.json`
- `mosaic help` for a quick overview

**V1 sync limitation:** only new PR *numbers* are imported (new comments on existing PRs are not re-fetched yet).

## Requirements

- Python ≥ 3.9
- A GitHub Personal Access Token with read access to the target repo’s pull requests / comments
- For **`mosaic check`:** an OpenAI-compatible chat API key (BYOK); embeddings may still be local

## Install

From this repo (recommended while developing):

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -e .            # API-only (lightweight)
# pip install -e '.[local]' # optional on-device embeddings (fastembed)
```

System-wide style (same machine):

```bash
pipx install -e /path/to/Mosaic
# later: pipx install mosaic-cli   # after PyPI publish
```

Or with requirements files:

```bash
pip install -r requirements.txt && pip install -e .
# pip install -r requirements-local.txt   # includes fastembed
```

## Quickstart

```bash
mosaic help                  # what Mosaic does + command list
mosaic init                  # prompt for repo URL + PAT → .env, create tables
mosaic build                 # full scrape + embeddings + Chroma index
mosaic sync                  # later: only new PRs + delta vectors

# Chat for check (prompted on first `mosaic check` if missing; change anytime with `mosaic settings`):
# CHAT_API_KEY=...                  # OpenAI, Groq, OpenRouter, … (also ~/.mosaic/.env)
# CHAT_MODEL=gpt-4o-mini            # or e.g. openai/gpt-oss-20b for Groq
# CHAT_API_BASE=...                 # blank = OpenAI; or set via provider alias
# CHAT_PROVIDER=openai              # optional label written by settings / check setup

mosaic check                 # auto git diff vs main/master
# git diff main | mosaic check --stdin
mosaic settings              # view / change chat LLM provider settings
```

For a fresh real build after test data, delete `mosaic.db` (and optionally `.mosaic/`) then re-run `init` + `build`.

## Commands

| Command | Description |
|---------|-------------|
| `mosaic help` | Product overview and available commands |
| `mosaic init` | Save repo URL + PAT to `.env`, create SQLite schema |
| `mosaic build` | Full ingest + configure embeddings + build Chroma index |
| `mosaic sync` | Delta: PRs missing from DB → save → vectorize → ready |
| `mosaic check` | Advisory cited feedback from changes vs main (BYOK chat) |
| `mosaic settings` | View / change chat LLM provider settings (key, base, model) |

Use `mosaic <command> --help` for flags on a specific command.

## Project layout

```text
cli/           Typer CLI (init, build, sync, check, help)
core/          Config, models, SQLite ORM, repository, sync_state, diff/git helpers
scrapers/      GitHub API client (PRs + labeled comments)
ai/            Embeddings + BYOK chat analyzer for check
pipeline/      Chroma indexer + retriever + check runner
docs/          PRD, TRD, ROADMAP
.env           Secrets and connection settings (gitignored)
.mosaic/       Chroma store, config.json, sync_state.json (gitignored)
mosaic.db      Local SQLite corpus (gitignored)
```

## Configuration

Per-project (not a global `~/.mosaic/` profile):

| Location | Contents |
|----------|----------|
| `.env` | `REPO_*`, embedding keys / backend; optional project `GITHUB_TOKEN`; optional project `CHAT_API_KEY` / `CHAT_MODEL` / `CHAT_API_BASE` / `CHAT_PROVIDER` |
| `~/.mosaic/.env` | Global `MOSAIC_GITHUB_TOKEN`; optional global `CHAT_API_KEY` / `CHAT_MODEL` / `CHAT_API_BASE` / `CHAT_PROVIDER` (shared across projects) |
| `.mosaic/config.json` | Non-secret build metadata (model name, chroma path, …) |
| `.mosaic/sync_state.json` | Known PR numbers, indexed comment IDs, `last_synced_at` |
| `.mosaic/chroma/` | Persistent vector index |

Do not commit `.env`, `.mosaic/`, or `mosaic.db`.

## Documentation

- [Product requirements (PRD)](docs/PRD.md)
- [Technical requirements (TRD)](docs/TRD.md)
- [Roadmap](docs/ROADMAP.md)
- [Changelog](CHANGELOG.md)

## Status

| Phase | Status |
|-------|--------|
| **Foundation** | Shipped: `init` → `build` → `sync` |
| **0.3.0** | Shipped: **`mosaic check`** engine (auto-diff, retrieval, BYOK chat via env) |
| **0.3.1** | Shipped: global GitHub PAT (`~/.mosaic/.env`) so `init` does not re-prompt per repo |
| **0.3.2** | Shipped: `mosaic init` adds `.env` / `.mosaic/` / `mosaic.db` to project `.gitignore` |
| **0.3.3** | Shipped: `mosaic check` prompts + verifies chat API key (global `~/.mosaic/.env` by default) |
| **0.3.4** | Shipped: chat prompt is OpenAI-compatible BYOK (base URL examples + Groq-aware model default) |
| **0.3.5** | Shipped: provider aliases + sample models + credential-setup logging for `mosaic check` |
| **0.4.0** | Shipped: **`mosaic settings`** — view/change chat LLM settings anytime (embeddings stay via `build`) |
| **Toward v1.0.0+** | `ask`, `describe`, hard gate, fuller TUI, PyPI, sync gaps — see [docs/ROADMAP.md](docs/ROADMAP.md) |
