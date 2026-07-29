# Mosaic — Roadmap

Durable backlog after the foundation and after v1.0.0. Product and technical detail for what ships *in* v1.0.0 lives in [PRD.md](PRD.md) and [TRD.md](TRD.md).

## Phases

| Phase | Status | What it is |
|-------|--------|------------|
| **Foundation** | Shipped | `init`, `build`, `sync` — local SQLite + Chroma corpus; embeddings via API or optional local fastembed |
| **v1.0.0** | Target | **`mosaic check` only** — advisory, cited, soft-gate feedback from team review history (BYOK chat) |
| **Post-1.0.0** | Backlog below | Everything else |

## v1.0.0 target (pointer)

**`mosaic check`** — pipe a diff (`git diff main | mosaic check`), retrieve similar past review comments per hunk, grade BLOCKING / SUGGESTION / NIT with PR citations. Advisory only (exit 0); no hard gate. Embeddings may be local; the LLM step is BYOK OpenAI-compatible API. See PRD / TRD for design.

---

## After v1.0.0

### Product features

- **`mosaic describe`** — generate a PR description from the current diff + review history.
- **`mosaic ask`** — Q&A over team review practices and past feedback (onboarding / “how do we usually…”).
- **Hard gate** — git pre-push (or CI) hook that can block on BLOCKING findings, only after `mosaic check` output is trusted.
- **Local / on-device chat LLM** — optional fully offline analysis; embeddings can already be local, chat stays BYOK until this lands.

### UX

- **Interactive TUI** — Claude Code–style terminal shell over the same core APIs (`check` first; later ask/describe), not a rewrite of ingest/index.

### Distribution

- **PyPI** — `pip install mosaic-cli` (and/or `pipx install mosaic-cli`) for a system-wide `mosaic` command usable in any repo.

### Infra

- **Sync gap** — re-fetch new comments on *existing* PR numbers (v1 sync only imports new PR numbers).
- **Automation** — cron / GitHub Actions (or similar) calling `mosaic sync`.
- **Token-based chunking** of long comments (today: one comment = one vector).
- **Deduplication / clustering** of similar review feedback.
- **Multi-repo** databases (today: one repo per working directory / `mosaic.db`).
