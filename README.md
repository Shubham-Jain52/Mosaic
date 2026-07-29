# Mosaic

CLI tool that turns a GitHub repository’s PR feedback into a local dataset and vector index for RAG.

Connect a repo with a Personal Access Token, scrape review and conversation comments into SQLite, then embed them (API or optional on-device) into Chroma.

## Features

- Connect one GitHub repo via PAT (`mosaic init`)
- Full first scrape of PRs plus labeled comments: review (inline), issue (conversation), and review summaries
- SQLite persistence with upsert-safe IDs
- Vector index build (`mosaic build`) with OpenAI, Hugging Face, or OpenAI-compatible APIs
- Optional local embeddings via **fastembed** (`mosaic-cli[local]`) — ONNX, no PyTorch in the base install
- `mosaic help` for a quick command overview

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
mosaic scrape                # fetch all PRs and comments → mosaic.db
mosaic build                 # choose embeddings, build Chroma index under .mosaic/
```

For a fresh real scrape after test data, delete `mosaic.db` and run `mosaic init` again before scraping.

## Commands

| Command | Description |
|---------|-------------|
| `mosaic help` | Product overview and available commands |
| `mosaic init` | Save repo URL + PAT to `.env`, create SQLite schema |
| `mosaic scrape` | Paginate all PRs and comments into `mosaic.db` |
| `mosaic build` | Configure embeddings and build the Chroma vector DB |

Use `mosaic <command> --help` for flags on a specific command.

## Project layout

```text
cli/           Typer CLI (init, scrape, build, help)
core/          Config, models, SQLite ORM, repository read API
scrapers/      GitHub API client (PRs + labeled comments)
ai/            Embedding backends (API + optional fastembed)
pipeline/      Chroma indexer
docs/          PRD and TRD
.env           Secrets and connection settings (gitignored)
.mosaic/       Chroma store + build config (gitignored)
mosaic.db      Local SQLite corpus
```

## Configuration

| Location | Contents |
|----------|----------|
| `.env` | `GITHUB_TOKEN`, `REPO_*`, embedding keys / backend settings |
| `.mosaic/config.json` | Non-secret build metadata (model name, chroma path, …) |
| `.mosaic/chroma/` | Persistent vector index |

Do not commit `.env` or `.mosaic/`.

## Documentation

- [Product requirements (PRD)](docs/PRD.md)
- [Technical requirements (TRD)](docs/TRD.md)
- [Changelog](CHANGELOG.md)

## Status

**Current:** ingest → SQLite → embedding config → Chroma index.

**Next (not shipped yet):** `mosaic ask` / LLM answers, incremental sync of new PRs, token-based chunking of long comments.
