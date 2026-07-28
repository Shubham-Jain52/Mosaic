# Mosaic — Technical Requirements Document (TRD)

## Stack

| Layer | Choice |
|-------|--------|
| Language | Python ≥ 3.9 |
| CLI | Typer (`mosaic` console script) |
| HTTP | `requests` |
| Config | `python-dotenv` → `.env` |
| ORM / DB | SQLAlchemy 2.x → SQLite (`mosaic.db`) |
| Packaging | `pyproject.toml` + setuptools |

## Repository layout

```text
cli/main.py          # mosaic init / scrape / build
core/config.py       # parse repo URL, load/write .env, embedding settings
core/models.py       # dataclasses (PR_Structure, Comment_Structure)
core/database.py     # ORM models, init_db, save_data_to_db (merge upsert)
core/repository.py   # read API for RAG consumers
scrapers/github.py   # paginated GitHub API client
ai/embeddings.py     # API embedders + optional fastembed local; ping / HF metadata verify
pipeline/indexer.py  # Chroma vector index from comment corpus
docs/PRD.md, TRD.md
pyproject.toml       # package mosaic-cli; optional extra [local]
requirements.txt     # API-only base
requirements-local.txt
```

## Configuration

`.env` keys written by `mosaic init`:

| Key | Purpose |
|-----|---------|
| `GITHUB_TOKEN` | User PAT (Bearer auth) |
| `REPO_OWNER` | GitHub owner/org |
| `REPO_NAME` | Repository name |
| `REPO_URL` | Canonical `https://github.com/owner/repo` |

`core.config.parse_repo_url` accepts:

- `https://github.com/owner/repo[.git]`
- `git@github.com:owner/repo.git`
- `owner/repo`

## Auth model (v1)

- **User Personal Access Token** collected interactively (or via `--token`).
- Token is used for all GitHub API calls; rate limits belong to that user.
- No OAuth app or GitHub App in v1.

Required token capabilities for private repos: ability to read pull requests and review comments on the target repository (classic: `repo`; fine-grained: Pull requests Read).

## GitHub API usage

| Resource | Endpoint | Stored as `comment_type` |
|----------|----------|--------------------------|
| PRs | `GET /repos/{owner}/{repo}/pulls?state=all&per_page=100` | — |
| Inline review comments | `GET /repos/{owner}/{repo}/pulls/{n}/comments` | `review_comment` |
| PR conversation comments | `GET /repos/{owner}/{repo}/issues/{n}/comments` | `issue_comment` |
| Review summaries | `GET /repos/{owner}/{repo}/pulls/{n}/reviews` | `review` |

All list endpoints paginate with `per_page=100` until a short/empty page.

Headers: `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`, `User-Agent: Mosaic-CLI`, `X-GitHub-Api-Version: 2022-11-28`.

On HTTP 403 with `X-RateLimit-Remaining: 0`, raise `GitHubAPIError` including reset time. No automatic retry queue in v1.

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
- **Single-repo DB** in v1: changing `REPO_*` to another repository requires a fresh `mosaic.db` (or a future migration that adds a repo key).

## Read module (`core.repository`)

| Function | Returns |
|----------|---------|
| `get_all_prs()` | list of PR dicts |
| `get_all_comments()` | list of comment dicts (+ joined `pr_title`, `pr_state`) |
| `get_comments_for_pr(n)` | comments for one PR |
| `get_comment_corpus()` | `{id, pr_number, file_path, author, pr_title, text}` where `text` concatenates file / diff / body for embedding |

## CLI commands

| Command | Behavior |
|---------|----------|
| `mosaic init` | Prompt (or `--repo` / `--token`), write `.env`, `init_db()` |
| `mosaic scrape` | Full paginated fetch → `save_data_to_db` → print counts |
| `mosaic build` | Choose local/API embedder, verify, persist config, build Chroma index |

## Embedding + vector index

| Piece | Path / choice |
|-------|----------------|
| Local model | Optional `fastembed` (ONNX) via `mosaic-cli[local]`; default `BAAI/bge-small-en-v1.5`; cache is user/HF cache, not project tree |
| API providers | `openai`, `huggingface`, `openai_compatible` (custom base URL) |
| Config | `.env` (`EMBEDDING_*`, keys) + `.mosaic/config.json` |
| Vector store | Chroma persistent client at `.mosaic/chroma/`, collection `mosaic_comments` |
| Document unit | One `get_comment_corpus()` entry → one vector (no extra chunking yet) |

**Verification:** no name allowlists. OpenAI/compatible = embeddings ping (`"ping"`). Hugging Face = Hub metadata (`pipeline_tag` / tags must be embedding-capable) then Inference feature-extraction ping.

Install:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .                 # API-only (lightweight)
# pip install -e '.[local]'      # optional on-device fastembed
mosaic init
mosaic scrape
mosaic build
```

Base install does **not** pull PyTorch/`sentence-transformers`. Local path needs `pip install 'mosaic-cli[local]'` (or `-e '.[local]'`).
## Error handling requirements

- Missing `.env` / token / repo → clear `RuntimeError` directing user to `mosaic init`
- Invalid URL → `ValueError` surfaced as CLI exit code 1
- Non-200 PR list → `GitHubAPIError` with status snippet
- Per-PR comment failures log and continue with comments collected so far for that PR when appropriate; PR list failures abort the scrape

## Security

- `.env` is gitignored
- PAT never printed in full after init (`***` only)
- Prefer fine-grained tokens scoped to one repository when possible

## Implemented so far / next technical phase

**Done:** config, CLI init/scrape/build, full pagination, labeled comments, SQLite upsert, repository read helpers, API embeddings (OpenAI/HF/compatible) with ping + HF Hub metadata verify, optional fastembed local via `mosaic-cli[local]`, Chroma index.

**Next:** incremental sync, `mosaic ask` / LLM answers, token chunking, optional multi-repo schema.
