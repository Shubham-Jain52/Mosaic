# Mosaic

CLI tool that turns a GitHub repository’s PR feedback into a local dataset and vector index for RAG.

Connect a repo with a Personal Access Token, run a full build (scrape + embeddings + Chroma), then use `mosaic sync` to pull only new PRs.

## Features

- Connect one GitHub repo via PAT (`mosaic init`)
- **`mosaic build`** — full scrape of labeled comments + embedder setup + vector index
- **`mosaic sync`** — fetch PRs not yet in SQLite, vectorize only the delta
- Comment kinds: review (inline), issue (conversation), review summaries
- Embeddings: OpenAI, Hugging Face, OpenAI-compatible APIs, or optional **fastembed** (`mosaic-cli[local]`)
- Sync bookmarks in `.mosaic/sync_state.json` (`last_synced_at`, known PR numbers, indexed comment IDs)
- `mosaic help` for a quick overview

**V1 sync limitation:** only new PR *numbers* are imported (new comments on existing PRs are not re-fetched yet).

## Requirements

- Python ≥ 3.9
- A GitHub Personal Access Token with read access to the target repo’s pull requests / comments

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
```

For a fresh real build after test data, delete `mosaic.db` (and optionally `.mosaic/`) then re-run `init` + `build`.

## Commands

| Command | Description |
|---------|-------------|
| `mosaic help` | Product overview and available commands |
| `mosaic init` | Save repo URL + PAT to `.env`, create SQLite schema |
| `mosaic build` | Full ingest + configure embeddings + build Chroma index |
| `mosaic sync` | Delta: PRs missing from DB → save → vectorize → ready |

Use `mosaic <command> --help` for flags on a specific command.

## Project layout

```text
cli/           Typer CLI (init, build, sync, help)
core/          Config, models, SQLite ORM, repository, sync_state
scrapers/      GitHub API client (PRs + labeled comments)
ai/            Embedding backends (API + optional fastembed)
pipeline/      Chroma indexer (full + delta)
docs/          PRD and TRD
.env           Secrets and connection settings (gitignored)
.mosaic/       Chroma store, config.json, sync_state.json (gitignored)
mosaic.db      Local SQLite corpus
```

## Configuration

| Location | Contents |
|----------|----------|
| `.env` | `GITHUB_TOKEN`, `REPO_*`, embedding keys / backend settings |
| `.mosaic/config.json` | Non-secret build metadata (model name, chroma path, …) |
| `.mosaic/sync_state.json` | Known PR numbers, indexed comment IDs, `last_synced_at` |
| `.mosaic/chroma/` | Persistent vector index |

Do not commit `.env` or `.mosaic/`.

## Documentation

- [Product requirements (PRD)](docs/PRD.md)
- [Technical requirements (TRD)](docs/TRD.md)
- [Changelog](CHANGELOG.md)

## Status

**Current:** init → build (scrape + index) → sync (delta PRs).

**Next:** `mosaic ask` / LLM answers; re-sync comments on existing PRs; automation (cron / Actions) calling `sync`.
