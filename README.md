# Mosaic

Local-first, BYOK CLI: turn a GitHub repository’s PR review feedback into a **local** SQLite dataset and Chroma vector index, then (v1.0.0) run **`mosaic check`** for advisory, cited pre-push feedback.

- **Local-first data** — corpus and vectors live in the project (`mosaic.db`, `.mosaic/`).
- **Embeddings** — OpenAI, Hugging Face, OpenAI-compatible APIs, or optional **on-device fastembed** (`mosaic-cli[local]`).
- **Chat for `check`** — bring-your-own-key OpenAI-compatible API. Mosaic is **not** fully offline end-to-end at v1.0.0; local chat LLM is later ([docs/ROADMAP.md](docs/ROADMAP.md)).

Connect a repo with a Personal Access Token, run a full build (scrape + embeddings + Chroma), use `mosaic sync` for new PRs, then (when v1.0.0 ships) pipe a diff into `mosaic check`.

## Features

- Connect one GitHub repo via PAT (`mosaic init`)
- **`mosaic build`** — full scrape of labeled comments + embedder setup + vector index
- **`mosaic sync`** — fetch PRs not yet in SQLite, vectorize only the delta
- Comment kinds: review (inline), issue (conversation), review summaries
- Embeddings: API providers or optional **local fastembed** (embeddings only — not chat)
- Sync bookmarks in `.mosaic/sync_state.json`
- `mosaic help` for a quick overview
- **Coming in v1.0.0:** `mosaic check` — `git diff … | mosaic check` → graded, cited, advisory feedback (BYOK chat)

**V1 sync limitation:** only new PR *numbers* are imported (new comments on existing PRs are not re-fetched yet).

## Requirements

- Python ≥ 3.9
- A GitHub Personal Access Token with read access to the target repo’s pull requests / comments
- For **`mosaic check` (v1.0.0):** an OpenAI-compatible API key (BYOK); embeddings may still be local

## Install

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -e .            # API-only (lightweight)
# pip install -e '.[local]' # optional on-device embeddings (fastembed)
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
# v1.0.0 (upcoming):
# git diff main | mosaic check
```

For a fresh real build after test data, delete `mosaic.db` (and optionally `.mosaic/`) then re-run `init` + `build`.

## Commands

| Command | Description |
|---------|-------------|
| `mosaic help` | Product overview and available commands |
| `mosaic init` | Save repo URL + PAT to `.env`, create SQLite schema |
| `mosaic build` | Full ingest + configure embeddings + build Chroma index |
| `mosaic sync` | Delta: PRs missing from DB → save → vectorize → ready |
| `mosaic check` | **v1.0.0 (upcoming)** — advisory cited feedback from stdin diff |

Use `mosaic <command> --help` for flags on a specific command.

## Project layout

```text
cli/           Typer CLI (init, build, sync, help; check in v1.0.0)
core/          Config, models, SQLite ORM, repository, sync_state
scrapers/      GitHub API client (PRs + labeled comments)
ai/            Embedding backends (API + optional fastembed); chat for check (v1.0.0)
pipeline/      Chroma indexer (full + delta)
docs/          PRD, TRD, ROADMAP
.env           Secrets and connection settings (gitignored)
.mosaic/       Chroma store, config.json, sync_state.json (gitignored)
mosaic.db      Local SQLite corpus
```

## Configuration

Per-project (not a global `~/.mosaic/` profile):

| Location | Contents |
|----------|----------|
| `.env` | `GITHUB_TOKEN`, `REPO_*`, embedding keys / backend settings; (v1.0.0) BYOK chat credentials |
| `.mosaic/config.json` | Non-secret build metadata (model name, chroma path, …) |
| `.mosaic/sync_state.json` | Known PR numbers, indexed comment IDs, `last_synced_at` |
| `.mosaic/chroma/` | Persistent vector index |

Do not commit `.env` or `.mosaic/`.

## Documentation

- [Product requirements (PRD)](docs/PRD.md)
- [Technical requirements (TRD)](docs/TRD.md)
- [Roadmap (post-1.0.0)](docs/ROADMAP.md)
- [Changelog](CHANGELOG.md)

## Status

| Phase | Status |
|-------|--------|
| **Foundation** | Shipped: `init` → `build` (scrape + index) → `sync` (delta PRs) |
| **v1.0.0** | Target: **`mosaic check`** only (BYOK chat; advisory soft gate; local embeddings optional) |
| **After v1.0.0** | `ask`, `describe`, hard gate, TUI, local chat LLM, PyPI, sync gaps, … — see [docs/ROADMAP.md](docs/ROADMAP.md) |
