# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Versions are listed **oldest first** so the file reads as project history.
When cutting a release, move items from `[Unreleased]` into a new dated section
**below** Unreleased (or clear Unreleased after promoting those notes).

## [0.0.1] - 2026-05-28

### Added

- Initial project scaffold (package stubs for scrapers, pipeline, AI, API, automation, tests).
- GitHub pull-request ingestion script and core dataclasses for PRs / review comments.
- Basic dependency list (`requirements.txt`) and `.gitignore`.

Commits: `debe3f2`, `ecbf232` (PR #1).

## [0.0.2] - 2026-06-11

### Added

- SQLAlchemy SQLite persistence (`core/database.py`) for pull requests and comments.
- Local `mosaic.db` created for storing scraped PR data.

Commits: `de6eac2` (PR #2).

## [0.0.3] - 2026-07-26

### Fixed

- Comment save path into SQLite (ORM mapping and GitHub review-comment `id` field).
- Dataclass / dependency alignment for reliable comment persistence.

Commits: `d9e6489`.

## [0.1.0] - 2026-07-28

### Added

- CLI package `mosaic-cli` with commands:
  - `mosaic init` — connect a GitHub repo + PAT to `.env`, create DB tables
  - `mosaic scrape` — full paginated ingest of PRs and comments
  - `mosaic build` — configure embeddings and build a Chroma vector index
- Config helpers (`.env` + `.mosaic/config.json`) for repo identity and embedding settings.
- Labeled comment kinds: `review_comment`, `issue_comment`, `review` (with Hub/API fetch + composite PK).
- Repository read API (`get_all_comments`, `get_comment_corpus`, etc.) for RAG consumers.
- Embedding backends: OpenAI, Hugging Face Inference, OpenAI-compatible APIs; optional on-device **fastembed** via `mosaic-cli[local]`.
- Provider verification without name allowlists (embeddings ping; HF Hub metadata + ping).
- Chroma indexer (`pipeline/indexer.py`) — one corpus comment → one vector document.
- Product / tech docs: `docs/PRD.md`, `docs/TRD.md`.

### Changed

- Packaging renamed to `mosaic-cli`; base install is API-only (no PyTorch / sentence-transformers).
- Scrapers driven by configured repo instead of a hardcoded target.

Commits: `93812c0`.

## [Unreleased]

### Added

- `mosaic sync` — fetch PRs not yet in SQLite, delta-vectorize, update `.mosaic/sync_state.json`.
- Sync state bookmarks: known PR numbers, indexed comment IDs, `last_synced_at` / `last_full_build_at`.

### Changed

- `mosaic build` now performs full scrape + embedder setup + full vector index (replaces separate `scrape` + `build`).
- Removed the `scrape` CLI command (library scrape helpers remain for build/sync).

## [0.1.1] - 2026-07-29

### Added

- `mosaic help` — overview of Mosaic and available commands.
