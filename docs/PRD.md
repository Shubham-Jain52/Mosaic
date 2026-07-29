# Mosaic — Product Requirements Document (PRD)

## Summary

Mosaic is a CLI tool that connects to a GitHub repository, scrapes pull-request review comments into a local SQLite database, and prepares that corpus for a future RAG (retrieval-augmented generation) system that can answer questions about how a codebase is reviewed.

## Goals

- Let a developer **connect one GitHub repo** with a Personal Access Token (PAT).
- On first use, **ingest all PRs and line-level review comments** into a local dataset.
- Provide a **read API** so a later RAG pipeline can load comment text for embedding and retrieval.
- Keep auth simple for a CLI: prompt once, store in `.env`, never commit secrets.

## Non-goals (current phase)

- OAuth / GitHub App install flows
- Multi-repo databases
- Re-fetching new comments on *existing* PRs during sync (v1 sync is new PR numbers only)
- `mosaic ask` / LLM answering (next phase)
- Web UI / hosted API product
- Auto sync-on-ask / GitHub Actions cron (later)

## Personas

- **Individual developer / maintainer** who wants institutional memory of review comments for one repo they have access to.

## User flows

### 1. Initialize

```text
mosaic init
```

1. Prompt for GitHub repo URL (`https://github.com/owner/repo` or `owner/repo`).
2. Prompt for GitHub PAT (hidden input).
3. Write `GITHUB_TOKEN`, `REPO_OWNER`, `REPO_NAME`, `REPO_URL` to `.env`.
4. Create SQLite schema in `mosaic.db`.
5. Instruct user to run `mosaic build`.

### 2. First build (scrape + index)

```text
mosaic build
```

1. Configure embedding backend (API or local fastembed) and persist settings.
2. Full paginated scrape of all PRs and labeled comments into SQLite.
3. Full Chroma vector index (one comment = one doc).
4. Write `.mosaic/sync_state.json` (known PRs, indexed ids, timestamps).
5. Print “Mosaic is ready for your questions.”

### 3. Sync (delta updates)

```text
mosaic sync
```

1. Require a prior `build` (embeddings configured).
2. List GitHub PR numbers; compare to SQLite / sync state.
3. If none missing → “Everything up to date.”
4. Else fetch only missing PRs → save → delta vectorize → update sync state → ready message.

### 4. Read for RAG (library)

Downstream code calls:

- `get_all_comments()` / `get_comments_for_pr()`
- `get_all_prs()` / `get_pr_numbers()`
- `get_comment_corpus()` — text blobs for embedding
- `build_vector_index()` / `index_corpus_delta()` — full or delta Chroma index

## Functional requirements

| ID | Requirement |
|----|-------------|
| FR-1 | CLI entry point `mosaic` with `init`, `build`, and `sync` commands |
| FR-2 | Accept GitHub HTTPS URL, SSH URL, or `owner/repo` shorthand |
| FR-3 | Store PAT and repo identity in `.env` (gitignored) |
| FR-4 | `mosaic build` scrapes all PRs + comments and creates a Chroma vector DB |
| FR-5 | Persist PRs and comments in SQLite with upsert-on-primary-key |
| FR-6 | Expose read helpers for comments and an embedding-oriented corpus |
| FR-7 | Fail clearly on missing config or GitHub rate-limit exhaustion |
| FR-8 | `mosaic sync` imports only PR numbers not yet in SQLite and delta-indexes them |
| FR-9 | API path verifies embeddings via live ping; Hugging Face also checks Hub model metadata |

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

- A user can go from zero config → connected repo → indexed Chroma DB via `init` + `build`.
- Re-running ingest paths does not inflate row counts (duplicates are merged).
- `mosaic sync` with no new PRs reports up to date; with new PRs only indexes the delta.

## Future work

- `mosaic ask` / LLM retrieval answers
- Re-sync comments on existing PRs; automation calling `sync`
- Deduplication / clustering of similar review feedback
- Token-based chunking of long comments
- Multi-repo support
