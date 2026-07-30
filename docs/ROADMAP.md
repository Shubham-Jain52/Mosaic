# Mosaic — Roadmap

Versioned product direction. Engine/design detail lives in [PRD.md](PRD.md) and [TRD.md](TRD.md).

## Phases

| Phase | Status | What it is |
|-------|--------|------------|
| **Foundation** | Shipped | `init`, `build`, `sync` — local SQLite + Chroma corpus; embeddings via API or optional local fastembed |
| **0.3.0** | Shipped | **`mosaic check` engine** — auto-diff vs main, retrieve past review comments, graded cited feedback (BYOK chat via `.env`) |
| **0.4.0** | Shipped (this release) | **`mosaic settings`** — view/change chat LLM provider settings (provider → sample models → key); first-run aliases shipped in 0.3.5 |
| **v1.0.0** | Target milestone | Product-complete soft-gate `check` experience (engine + polished BYOK UX); still advisory (no hard gate) |
| **Post-1.0.0** | Backlog below | Everything else |

## 0.3.0 — check engine (shipped)

- Default: `mosaic check` runs `git diff` against `origin/main` / `main` / `master` (stdin / `--stdin` override).
- Trivial/empty diff → `no meaningful changes detected` (no LLM).
- Per-hunk Chroma retrieval + OpenAI-compatible chat → BLOCKING / SUGGESTION / NIT with PR citations.
- Configure chat with `CHAT_API_KEY` / `CHAT_MODEL` / optional `CHAT_API_BASE`.

## 0.4.0 — `mosaic settings` (shipped)

Guided BYOK so users don’t hand-edit obscure env vars — and can **change** chat settings later:

- **`mosaic settings`** — show masked current chat config; reconfigure provider → sample models → API key; verify; save to `~/.mosaic/.env` (default) or project `.env`
- Reuses 0.3.5 provider aliases (OpenAI / Groq / OpenRouter / Custom URL) and sample model lists
- Embedding settings stay out of scope here (change via `mosaic build` + full re-index)
- Env vars remain the backing store (`CHAT_*`). Full interactive TUI shell remains post-1.0.0

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
