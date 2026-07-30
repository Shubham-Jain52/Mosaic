# Mosaic — Product Requirements Document (PRD)

## Summary

Mosaic is a **local-first, BYOK** CLI: it connects to a GitHub repository, scrapes pull-request review comments into a local SQLite database and Chroma vector index, then (for **v1.0.0**) uses that history to give **advisory, cited pre-push feedback** via `mosaic check`.

- **Local-first data:** corpus and vectors live on disk in the project (`.env`, `mosaic.db`, `.mosaic/`).
- **Optional local embeddings:** API providers or on-device fastembed (`mosaic-cli[local]`).
- **BYOK chat for analysis:** `mosaic check` calls a user-provided OpenAI-compatible API. Mosaic is **not** a fully offline / fully local product at v1.0.0 — local chat LLM is post-1.0.0 ([ROADMAP.md](ROADMAP.md)).

Config is **per project** (`.env` + `.mosaic/`), not a global `~/.mosaic/config.toml`, so multiple repos map naturally to multiple working directories.

## Phases

| Phase | Meaning |
|-------|---------|
| **Foundation (shipped)** | `init`, `build`, `sync` |
| **v1.0.0 (the product goal)** | Polished **`mosaic check`** soft-gate (engine shipped in 0.3.0; BYOK setup UX in 0.4.0) |
| **Post-1.0.0** | See [ROADMAP.md](ROADMAP.md) |

## Goals

### Foundation (shipped)

- Connect **one** GitHub repo with a Personal Access Token (PAT).
- Ingest PRs and labeled review / conversation comments into a local dataset.
- Embed and index that corpus for retrieval (API or optional local embeddings).
- Keep secrets in `.env`, never commit them.

### v1.0.0 — THE defining feature

**`mosaic check`** is the single defining feature of v1.0.0:

- **Engine:** default auto-diff vs `main` (stdin / `--stdin` override); split into hunks → retrieve similar past comments from Chroma → LLM grades issues with severity and **cites past PRs**.
- **Output:** readable terminal feedback (table or clear sections). Soft gate only — exit 0; does **not** block `git push`.
- **BYOK chat setup UX (0.4.0):** `mosaic settings` (and first-run `mosaic check` prompts) — provider picker → sample model list → API key entry (persist to `.env`). Supports OpenAI, Groq, OpenRouter, and OpenAI-compatible hosts via presets. Embedding changes remain via `mosaic build`.

## Non-goals (v1.0.0)

- `mosaic ask` / `mosaic describe` (deferred — see below)
- Hard gate / git pre-push hook that fails the push (deferred until `check` is trusted)
- Local / on-device **chat** LLM (embeddings may be local; chat is BYOK)
- Fully offline end-to-end product
- OAuth / GitHub App install flows
- Multi-repo databases in one DB file
- Re-fetching new comments on *existing* PRs during sync (foundation sync is new PR numbers only)
- Web UI / hosted API product

## Personas

- **Individual developer / maintainer** who wants pre-push feedback grounded in *this team’s* past review comments for one repo they can access.

## Configuration

Config moved to **per-project** files (not a global `~/.mosaic/config.toml`) so each repo can have its own corpus and secrets.

| Location | Contents |
|----------|----------|
| `.env` | Per-project: `REPO_*`, embedding keys / backend settings; chat/BYOK keys for `check`; optional project `GITHUB_TOKEN` |
| `~/.mosaic/.env` | Global `MOSAIC_GITHUB_TOKEN` (classic PAT shared across projects) |
| `.mosaic/config.json` | Non-secret build metadata (embedding model, chroma path, collection, …) |
| `.mosaic/sync_state.json` | Known PR numbers, indexed comment IDs, `last_synced_at`, `last_full_build_at` |
| `.mosaic/chroma/` | Persistent vector index |
| `mosaic.db` | Local SQLite corpus |

Do not commit `.env` or `.mosaic/`.

## User flows

### 1. Initialize (shipped)

```text
mosaic init
```

1. Prompt for GitHub repo URL (`https://github.com/owner/repo` or `owner/repo`).
2. Prompt for GitHub PAT (hidden input).
3. Resolve GitHub PAT: use global `MOSAIC_GITHUB_TOKEN` if set; otherwise prompt once and offer to save to `~/.mosaic/.env`. Write `REPO_OWNER`, `REPO_NAME`, `REPO_URL` to project `.env` (token only if not using global).
4. Ensure project `.gitignore` includes `.env`, `.mosaic/`, and `mosaic.db` (create or append; idempotent).
5. Create SQLite schema in `mosaic.db`.
6. Instruct user to run `mosaic build`.

### 2. First build (shipped)

```text
mosaic build
```

1. Configure embedding backend (API or local fastembed) and persist settings.
2. Full paginated scrape of all PRs and labeled comments into SQLite.
3. Full Chroma vector index (one comment = one doc).
4. Write `.mosaic/sync_state.json` (known PRs, indexed ids, timestamps).
5. Print that the corpus/index is ready (for sync and, at v1.0.0, for `mosaic check`).

### 3. Sync (shipped)

```text
mosaic sync
```

1. Require a prior `build` (embeddings configured).
2. List GitHub PR numbers; compare to SQLite / sync state.
3. If none missing → “Everything up to date.”
4. Else fetch only missing PRs → save → delta vectorize → update sync state → ready message.

### 4. Check — v1.0.0

```text
mosaic check
# optional: git diff main | mosaic check --stdin
```

1. Require a prior `build` (index exists) and BYOK chat credentials (`mosaic settings` / first-run `check` prompts / `CHAT_*` env).
2. Default: resolve baseline (`main` / `master` / remotes) and run `git diff <base>`; or use piped/`--stdin` diff.
3. If empty/trivial diff → “no meaningful changes detected” (no LLM).
4. For each hunk, retrieve top-k similar past comments from Chroma.
5. LLM returns graded, cited feedback; if history is thin, say so explicitly (no invented generic advice).
6. Print readable terminal output; exit 0 (advisory).

### 5. Read API (shipped library)

Downstream code calls:

- `get_all_comments()` / `get_comments_for_pr()`
- `get_all_prs()` / `get_pr_numbers()`
- `get_comment_corpus()` — text blobs for embedding
- `build_vector_index()` / `index_corpus_delta()` — full or delta Chroma index

## Functional requirements

| ID | Requirement |
|----|-------------|
| FR-1 | CLI entry point `mosaic` with shipped `init`, `build`, and `sync` |
| FR-2 | Accept GitHub HTTPS URL, SSH URL, or `owner/repo` shorthand |
| FR-3 | Store PAT and repo identity in `.env` (gitignored) |
| FR-4 | `mosaic build` scrapes all PRs + comments and creates a Chroma vector DB |
| FR-5 | Persist PRs and comments in SQLite with upsert-on-primary-key |
| FR-6 | Expose read helpers for comments and an embedding-oriented corpus |
| FR-7 | Fail clearly on missing config or GitHub rate-limit exhaustion |
| FR-8 | `mosaic sync` imports only PR numbers not yet in SQLite and delta-indexes them |
| FR-9 | API path verifies embeddings via live ping; Hugging Face also checks Hub model metadata |
| FR-10 | **0.3.0+:** `mosaic check` analyzes working-tree diff vs main (stdin override), returns graded (blocking / suggestion / nit), cited, advisory feedback; exit 0 |
| FR-11 | **0.4.0:** `mosaic settings` — view/change BYOK chat (provider → sample models → API key); persist `CHAT_*` to `.env`; embeddings unchanged (use `mosaic build`) |

## Data captured

**Pull request:** number, title, state, description

**Comments** (labeled by `comment_type`):

| Type | Meaning |
|------|---------|
| `review_comment` | Inline diff review comments |
| `issue_comment` | PR conversation / issue-thread comments |
| `review` | Review summary (approve / request changes / comment), with `review_state` |

Fields: comment_id, comment_type, pr_number, body, diff_hunk, file_path, author, review_state.

## Success criteria

**Foundation (today):**

- Zero config → connected repo → indexed Chroma DB via `init` + `build`.
- Re-running ingest does not inflate row counts (duplicates merged).
- `mosaic sync` with no new PRs reports up to date; with new PRs only indexes the delta.

**v1.0.0 (target):**

- `mosaic check` prints structured, severity-graded, PR-cited feedback on real diffs.
- Empty / irrelevant diffs do not hallucinate generic advice (“no meaningful changes” / “not enough relevant history”).
- Tool remains advisory (exit 0); no push-blocking hook in v1.0.0.
- Users can configure chat via `.env` or **`mosaic settings`** (0.4.0); first-run prompts on `mosaic check` if missing.

## Planned — Not in v1.0.0

- **`mosaic describe`** — generate a PR description from the current diff and review history.
- **`mosaic ask`** — answer questions about team workflow / review practices for new members.

Full post-1.0.0 backlog (full interactive TUI shell, local chat LLM, PyPI, sync gaps, etc.): [ROADMAP.md](ROADMAP.md). Chat provider reconfigure via **`mosaic settings`** shipped in **0.4.0** (FR-11).

## Planned — v1.1+

- **Hard gate** (git pre-push hook or CI fail-on-BLOCKING) is deferred until `mosaic check` output is trusted. v1.0.0 ships soft-gate / advisory terminal output only.
