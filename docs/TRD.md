# Mosaic — Technical Requirements Document (TRD)

## Stack

| Layer | Choice |
|-------|--------|
| Language | Python ≥ 3.9 |
| CLI | Typer (`mosaic` console script) |
| HTTP | `requests` |
| Config | `python-dotenv` → `.env`; project metadata under `.mosaic/` |
| ORM / DB | SQLAlchemy 2.x → SQLite (`mosaic.db`) |
| Vectors | Chroma persistent client under `.mosaic/chroma/` |
| Packaging | `pyproject.toml` + setuptools (`mosaic-cli`; optional extra `[local]`) |

## Phases (technical)

| Phase | Status |
|-------|--------|
| Foundation | Shipped — ingest, embeddings, index, sync |
| v1.0.0 | Target — `mosaic check` (BYOK chat + retrieval); see below |
| Post-1.0.0 | [ROADMAP.md](ROADMAP.md) |

## Repository layout

Matches the real tree (stubs under `api/` / `automation/` are reserved for later):

```text
cli/                 # Typer: init, build, sync, help (+ check in v1.0.0)
  main.py
core/
  config.py          # parse repo URL, load/write .env, embedding settings, .mosaic/config.json
  models.py          # dataclasses (PR_Structure, Comment_Structure)
  database.py        # ORM models, init_db, save_data_to_db (merge upsert)
  repository.py      # read API for corpus / RAG consumers
  sync_state.py      # .mosaic/sync_state.json read/write
scrapers/
  github.py          # paginated GitHub API client (not a CLI command)
ai/
  embeddings.py      # API embedders + optional fastembed; ping / HF metadata verify
  analyzer.py        # v1.0.0: Feedback + BaseAnalyzer (planned)
pipeline/
  indexer.py         # Chroma full + delta index from comment corpus
api/                 # placeholder (hosted API — not v1.0.0)
automation/          # placeholder (scheduler — not v1.0.0)
docs/                # PRD, TRD, ROADMAP
tests/
pyproject.toml
requirements.txt
requirements-local.txt
```

Earlier drafts listed `mosaic scrape` as a CLI command; scrape is an internal step of `build` / `sync` only.

## Configuration

Config is **per project** (not a global `~/.mosaic/config.toml`) so multi-repo usage is “one working directory per repo.”

| Location | Contents |
|----------|----------|
| `.env` | `GITHUB_TOKEN`, `REPO_OWNER`, `REPO_NAME`, `REPO_URL`; `EMBEDDING_*` / provider keys; (v1.0.0) BYOK chat key / base URL / model for `check` |
| `.mosaic/config.json` | Non-secret build metadata: embedding backend/provider/model, chroma path, collection name, `built_at` |
| `.mosaic/sync_state.json` | `known_pr_numbers`, `indexed_comment_ids`, `embedding_model`, `last_synced_at`, `last_full_build_at` |
| `.mosaic/chroma/` | Persistent Chroma store |
| `mosaic.db` | SQLite corpus |

`.env` keys written by `mosaic init`:

| Key | Purpose |
|-----|---------|
| `GITHUB_TOKEN` | Optional per-project PAT (legacy / override) |
| `MOSAIC_GITHUB_TOKEN` | Preferred global PAT in `~/.mosaic/.env` |
| `REPO_OWNER` | GitHub owner/org |
| `REPO_NAME` | Repository name |
| `REPO_URL` | Canonical `https://github.com/owner/repo` |

`core.config.parse_repo_url` accepts:

- `https://github.com/owner/repo[.git]`
- `git@github.com:owner/repo.git`
- `owner/repo`

## Auth model (foundation / v1)

- **User Personal Access Token** collected interactively (or via `--token`).
- Token is used for all GitHub API calls; rate limits belong to that user.
- No OAuth app or GitHub App in foundation / v1.0.0.
- **BYOK** for embeddings (optional) and for **chat** used by `mosaic check` (required for analysis at v1.0.0).

Required token capabilities for private repos: ability to read pull requests and review comments (classic: `repo`; fine-grained: Pull requests Read).

## GitHub API usage

| Resource | Endpoint | Stored as `comment_type` |
|----------|----------|--------------------------|
| PRs | `GET /repos/{owner}/{repo}/pulls?state=all&per_page=100` | — |
| Inline review comments | `GET /repos/{owner}/{repo}/pulls/{n}/comments` | `review_comment` |
| PR conversation comments | `GET /repos/{owner}/{repo}/issues/{n}/comments` | `issue_comment` |
| Review summaries | `GET /repos/{owner}/{repo}/pulls/{n}/reviews` | `review` |

All list endpoints paginate with `per_page=100` until a short/empty page.

Headers: `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`, `User-Agent: Mosaic-CLI`, `X-GitHub-Api-Version: 2022-11-28`.

On HTTP 403 with `X-RateLimit-Remaining: 0`, raise `GitHubAPIError` including reset time. No automatic retry queue in foundation.

## Database schema

**`pull_requests`**

| Column | Type | Notes |
|--------|------|-------|
| number | INTEGER PK | GitHub PR number (single-repo assumption) |
| title | VARCHAR(512) | |
| state | VARCHAR(50) | open / closed |
| description | TEXT NULL | PR body |

**`comment_table`**

| Column | Type | Notes |
|--------|------|-------|
| comment_type | VARCHAR(50) PK | `review_comment` \| `issue_comment` \| `review` |
| comment_id | INTEGER PK | GitHub id within that kind (composite PK with type) |
| pr_number | INTEGER FK → pull_requests.number | |
| review_state | VARCHAR(50) NULL | For `review`: APPROVED / CHANGES_REQUESTED / COMMENTED / … |
| comment_body | TEXT | |
| diff_hunk | TEXT | |
| file_path | TEXT | widened for long paths |
| author | VARCHAR(255) | login |

### Duplicate strategy

- Primary keys + SQLAlchemy `session.merge()` upsert on every scrape.
- Re-scrape updates existing rows; does not insert duplicates.
- **Single-repo DB** in foundation: changing `REPO_*` to another repository requires a fresh `mosaic.db` (or a future migration that adds a repo key).

## Read module (`core.repository`)

| Function | Returns |
|----------|---------|
| `get_all_prs()` | list of PR dicts |
| `get_all_comments()` | list of comment dicts (+ joined `pr_title`, `pr_state`) |
| `get_comments_for_pr(n)` | comments for one PR |
| `get_comment_corpus()` | `{id, pr_number, file_path, author, pr_title, text}` where `text` concatenates file / diff / body for embedding |

## CLI commands

| Command | Status | Behavior |
|---------|--------|----------|
| `mosaic init` | Shipped | Prompt (or `--repo` / `--token`), write `.env`, `init_db()` |
| `mosaic build` | Shipped | Embedder setup + full scrape + full Chroma index + sync state |
| `mosaic sync` | Shipped | PRs not in SQLite → delta scrape + delta vectorize + update sync state |
| `mosaic help` | Shipped | Product overview |
| `mosaic check` | **0.3.0** | Auto git diff vs main (stdin override) → retrieve → BYOK LLM → graded cited output; exit 0 |

## Embedding + vector index (shipped)

| Piece | Path / choice |
|-------|----------------|
| Local embeddings | Optional `fastembed` (ONNX) via `mosaic-cli[local]`; default `BAAI/bge-small-en-v1.5`; cache is user/HF cache, not project tree |
| API providers | `openai`, `huggingface`, `openai_compatible` (custom base URL) |
| Config | `.env` (`EMBEDDING_*`, keys) + `.mosaic/config.json` |
| Sync state | `.mosaic/sync_state.json` |
| Vector store | Chroma at `.mosaic/chroma/`, collection `mosaic_comments` |
| Document unit | One `get_comment_corpus()` entry → one vector (no extra chunking yet) |

**Verification:** no name allowlists. OpenAI/compatible = embeddings ping (`"ping"`). Hugging Face = Hub metadata (`pipeline_tag` / tags must be embedding-capable) then Inference feature-extraction ping.

**Note:** Local embeddings ≠ local chat. Chat for `mosaic check` is a separate BYOK path (next section). Fully local chat is post-1.0.0 ([ROADMAP.md](ROADMAP.md)).

Install (foundation):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .                 # API-only (lightweight)
# pip install -e '.[local]'      # optional on-device fastembed
mosaic init
mosaic build
mosaic sync
```

Base install does **not** pull PyTorch/`sentence-transformers`. Local embeddings need `pip install 'mosaic-cli[local]'` (or `-e '.[local]'`).

---

## `mosaic check` — v1.0.0 Technical Design

This section is the source of truth for implementing `check`. It supersedes any earlier vague “LLM adapter” / “ask-first RAG” sketches. `mosaic ask` / `describe` are **not** designed here.

### Product behavior

```text
git diff main | mosaic check
```

Advisory soft gate only: print feedback; **exit code 0** always in v1.0.0. No git pre-push hard gate.

### Typed seam (`Feedback`)

In `ai/analyzer.py` (or equivalent), the only object that leaves the analyzer into CLI / formatters / future TUI:

```text
Feedback:
  issue: str
  severity: Literal["blocking", "suggestion", "nit"]
  file_path: str
  line_hint: str | None
  cited_prs: list[int]
```

Raw LLM response text must not leak past this module.

### `BaseAnalyzer`

```text
BaseAnalyzer (ABC):
  check(diff_hunk: str, past_comments: list[dict]) -> list[Feedback]
```

- Prompt the LLM for structured JSON matching `Feedback`, then parse into real `Feedback` objects.
- **Decision / validation** (normalize severity, drop invent-without-citations when retrieval is empty, etc.) stays in **pure functions** separate from the LLM I/O call (`codeStruct` typed-seam / pure-logic split).
- Do not build `describe` / `ask` in this module for v1.0.0; a short comment that the seam could support them later is fine.

### BYOK chat module (separate from embeddings)

- New chat/completions client under `ai/` (e.g. beside `embeddings.py`), **OpenAI-compatible** API: user-provided API key, optional base URL, model name.
- Reuse the same BYOK spirit as embedding API keys; do **not** require a 1:1 mapping to every embedding backend (local fastembed has no chat).
- **No local chat LLM in v1.0.0.**
- Log an approximate LLM **call count** when `check` runs (cost visibility).

**0.4.0 chat setup UX (after engine is trusted):** guided config — **provider → model list → API key** (CLI prompts first; same flow in TUI dropdowns later). Presets map providers (OpenAI, Groq, Gemini, openai_compatible) to base URLs / default model catalogs; custom base URL only for compatible. Persist `CHAT_PROVIDER` / `CHAT_MODEL` / `CHAT_API_KEY` / optional `CHAT_API_BASE` in `.env`. Check engine (0.3.0) uses raw env vars until this lands.

### Diff parsing

- New small module (preferred: `core/diff_parser.py`): raw unified diff text → iterable per-file / per-hunk chunks (`file_path`, hunk header, body).
- Prefer stdlib / manual `@@` hunk-header parsing; **no** new heavy dependency if avoidable.
- `difflib` is not a unified-diff splitter; use explicit unified-diff parsing.

### Retrieval

- For each hunk, query the **existing** Chroma collection (thin query helper on the current indexer/client — do not build a second vector stack).
- Default **top-k = 5**, configurable (e.g. CLI `--top-k`).
- Past comments passed into `BaseAnalyzer.check` as plain dicts (id, text, `pr_number`, file_path, …) from retrieval metadata / corpus.

### CLI orchestration

- New `mosaic check` Typer command: read stdin → parse → retrieve per hunk → analyze → print formatted output (table or clear sections, **not** raw JSON).
- Keep orchestration thin; prefer a shared runner (e.g. under `pipeline/` or `ai/`) so a future **TUI** can call the same pipeline without rewriting retrieval/analyzer.
- Exit 0 always (advisory).

### Blank-drop and swap verification

Before calling `check` “done”:

1. **Blank-drop:** empty / irrelevant / no-op diff → “not enough relevant history to comment” (or equivalent), **not** hallucinated generic advice.
2. **Swap:** two genuinely different diffs → genuinely different feedback, not identical boilerplate.

Cheap checks: pipe empty stdin / noop diff; run two real diffs and compare citations/issues by eye.

### Evaluation script

- Small script e.g. `tests/eval_check.py`: a handful of known diffs with expected severity/category or “empty history” outcomes.
- Manual sanity check for v1.0.0 quality; need not be exhaustive, but must exist.

### Boundaries (implementation)

- Do not modify `scrapers/`, existing `core/models.py`, or the ingest/sync pipeline unless fixing a blocking bug.
- Do not build `describe`, `ask`, or a pre-push hard gate in the v1.0.0 session.

---

## Error handling requirements

- Missing `.env` / token / repo → clear `RuntimeError` directing user to `mosaic init`
- Invalid URL → `ValueError` surfaced as CLI exit code 1
- Non-200 PR list → `GitHubAPIError` with status snippet
- Per-PR comment failures log and continue with comments collected so far for that PR when appropriate; PR list failures abort the scrape
- **v1.0.0 `check`:** missing index or missing BYOK chat config → clear error; thin retrieval → explicit empty-history messaging (not invented advice)

## Security

- `.env` is gitignored
- PAT never printed in full after init (`***` only)
- Prefer fine-grained tokens scoped to one repository when possible
- BYOK chat keys stay in `.env`; never commit

## Implemented so far / next technical phase

**Done (foundation + 0.3.0):** per-project config (`.env` + `.mosaic/`), CLI `init` / `build` / `sync` / `help` / `check`, full pagination, labeled comments, SQLite upsert, repository read helpers, sync state + delta sync, API embeddings (OpenAI/HF/compatible) with ping + HF Hub metadata verify, optional fastembed local via `mosaic-cli[local]`, Chroma full + delta index, check runner (diff parse, git auto-diff, retrieval, BYOK OpenAI-compatible analyzer).

**Next (0.4.0):** chat provider → model list → API key setup UX (CLI/TUI).

**After:** [ROADMAP.md](ROADMAP.md) — `ask`, `describe`, hard gate, local chat LLM, fuller TUI, PyPI, sync gaps, etc.
