# Honeybon

Captures coding-problem submissions, returns a four-tier AI review, and surfaces technique avoidance.
Product spec: `docs/REQUIREMENTS.md` (source of truth for scope and phases).
Visual reference: the approved mockup at https://claude.ai/artifact/2Q8itrsBcMLtLheFDnznoB.

## Layout

- `backend/` — FastAPI API + arq worker (Python 3.12+, managed with `uv`)
  - `app/reviews/` — the review contract: `taxonomy.py` (fixed technique + complexity vocabularies),
    `schema.py` (Pydantic `Review`), `validation.py` (parse + validate; error text feeds the repair retry)
  - `app/providers/` — `ProviderAdapter` protocol (structured review + streaming chat) and registry
  - `app/models/` — SQLAlchemy 2 models, one per table in the spec's data model
  - `app/worker/` — arq tasks; every LLM call, import and analysis runs here, never in the API
- `frontend/` — React 19 + TypeScript + Vite + Tailwind v4 + TanStack Query
- `extension/` — Chrome MV3 extension (Phase 2, not started)

## Commands

```sh
docker compose up -d                              # Postgres 17 + Redis 7
cd backend
uv sync                                           # install
uv run alembic upgrade head                       # migrate
uv run uvicorn app.main:app --reload              # API on :8000
uv run arq app.worker.main.WorkerSettings         # worker
uv run pytest                                     # tests
uv run ruff check . && uv run ruff format .       # lint/format
uv run alembic revision --autogenerate -m "..."   # new migration

cd frontend
npm install
npm run dev                                       # :5173, proxies /api to :8000
npm run build                                     # typecheck + build
```

## Rules that matter

- Every query on user data filters by `user_id`.
- Technique and complexity fields use the enums in `app/reviews/taxonomy.py`, never free text.
- Provider API keys: Fernet-encrypted (`app/core/crypto.py`), decrypted only in the worker, never
  returned beyond `last_four`. Extension tokens are stored only as SHA-256 hashes.
- User code and problem text are wrapped as data in prompts. Model output is rendered as sanitized
  Markdown, never raw HTML.
- Never store LeetCode problem statements — metadata only.
- UI: colours only via the CSS variables / Tailwind tokens in `frontend/src/index.css`. One blue
  accent; orange only for attention. Diffs use blue/orange, not green/red.

## Decisions taken (open questions in the spec)

- Job queue: **arq** (async, shares SQLAlchemy async code with the API).
