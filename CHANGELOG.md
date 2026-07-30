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

## [0.3.5] - 2026-07-30

### Added

- **Provider aliases for `mosaic check` chat setup** — choose OpenAI / Groq / OpenRouter by number or name (e.g. `Groq`), or paste a custom full URL; aliases resolve to the correct API base automatically.
- **Sample models per provider** — numbered list of known models with an “Other / custom” option (light interactive UX; full TUI remains 0.4.0).
- **Credential-setup logging** — `[mosaic]` lines for resolved base URL, chosen model, verify attempt, and success/failure (failure includes resolved base + model, never the API key).

### Changed

- Groq default / recommended sample model is now `openai/gpt-oss-20b` (current Groq production); `llama-3.3-70b-versatile` remains listed as a sample.

## [0.3.4] - 2026-07-30

### Fixed

- **`mosaic check` chat setup is true OpenAI-compatible BYOK** — prompts clearly for any provider key (Groq, OpenRouter, Together, local gateways, …), not OpenAI-only.
- Asks for **API base URL first** (with Groq / OpenRouter / custom examples), then model; Groq base defaults model to `llama-3.3-70b-versatile`.
- No `sk-` key-format restriction; verification ping uses the user-provided base + key + model; saves `CHAT_API_BASE` when set.

## [0.3.3] - 2026-07-30

### Added

- **`mosaic check` prompts for a chat API key** when `CHAT_API_KEY` / `OPENAI_API_KEY` is missing (instead of failing immediately).
- Key is verified with a cheap chat completion ping before use; settings saved to `~/.mosaic/.env` by default (project `.env` if declined).

### Changed

- Chat credentials follow the same global-first pattern as `MOSAIC_GITHUB_TOKEN`.

## [0.3.2] - 2026-07-30

### Fixed

- **`mosaic init` now updates project `.gitignore`** with `.env`, `.mosaic/`, and `mosaic.db` so secrets and local Mosaic data are not committed by accident.

## [0.3.1] - 2026-07-30

### Added

- Global GitHub PAT: `MOSAIC_GITHUB_TOKEN` in `~/.mosaic/.env` (prompted once on `mosaic init`, reused across projects).
- Per-project `.env` stores `REPO_*` without requiring a local `GITHUB_TOKEN` when the global token is set.

### Changed

- `get_github_token()` resolves `MOSAIC_GITHUB_TOKEN` first, then project `GITHUB_TOKEN` (backward compatible).

## [0.3.0] - 2026-07-30

### Added

- **`mosaic check`** — advisory review of working-tree changes vs `main`/`master` (auto `git diff`; `--stdin` / pipe override).
- Diff parser + trivial-diff guard (`no meaningful changes detected` — no LLM call).
- Chroma retrieval per hunk (`pipeline/retriever.py`) and BYOK OpenAI-compatible chat (`ai/chat.py`, `ai/analyzer.py`).
- Graded findings: BLOCKING / SUGGESTION / NIT with cited PR numbers; blank-drop when history is thin.
- Unit tests and `tests/eval_check.py` for parser / trivial / cheap eval paths.

### Changed

- Docs/roadmap: check engine ships in **0.3.0**; provider → model → key setup UX deferred to **0.4.0**.

### Notes

- Configure chat via `.env`: `CHAT_API_KEY` (or `OPENAI_API_KEY`), optional `CHAT_API_BASE`, `CHAT_MODEL`.
- Interactive TUI / provider dropdown is **not** in 0.3.0 (planned for 0.4.0).

## [0.2.0] - 2026-07-29

### Added

- `mosaic sync` — fetch PRs not yet in SQLite, delta-vectorize, update `.mosaic/sync_state.json`.
- Sync state bookmarks: known PR numbers, indexed comment IDs, `last_synced_at` / `last_full_build_at`.

### Changed

- `mosaic build` now performs full scrape + embedder setup + full vector index (replaces separate `scrape` + `build`).
- Removed the `scrape` CLI command (library scrape helpers remain for build/sync).

## [0.1.1] - 2026-07-29

### Added

- `mosaic help` — overview of Mosaic and available commands.
