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
docker compose up -d                              # Postgres 17 (:5433) + Redis 7
cd backend
uv sync                                           # install
uv run alembic upgrade head                       # migrate
uv run uvicorn app.main:app --reload              # API on :8000
uv run arq app.worker.main.WorkerSettings         # worker
uv run pytest                                     # tests (need docker compose up)
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
- Review streaming: **two structured calls** per review — `ReviewPartA` (verdict + tier 1), then
  `ReviewPartB` (tiers 2–4 + pattern) with part A as context. Each call gets one repair retry.
  Part A is stored and announced over SSE as soon as it validates.
- Provider schemas: `app/reviews/provider_schema.py` strips constraints providers reject; the full
  Pydantic model is still validated server-side.

## Local dev notes

- No GitHub OAuth app needed locally: the login screen has a "Dev login" button (`ENV=dev` only).
- For real GitHub login, register an OAuth app with callback
  `http://localhost:5173/api/auth/github/callback` and set `GITHUB_CLIENT_ID/SECRET` in `backend/.env`.
- Vite proxies `/api` to `127.0.0.1:8000` (not `localhost`, which Node resolves to IPv6).
- `uvicorn --reload` can stall on Windows and keep serving old code; restart the API (and always
  the arq worker, which never reloads) after backend changes.
- Live provider tests are opt-in: `HB_LIVE_PROVIDER=... HB_LIVE_MODEL=... HB_LIVE_API_KEY=... uv run pytest -m live -s`.

## Providers

- Model lists and defaults: `PROVIDER_MODELS` in `app/providers/__init__.py` (first = default).
- Groq: free tier counts prompt + `max_completion_tokens` against 8K tokens/minute and rejects a
  single larger request (413). The adapter sizes output to fit `GROQ_REQUEST_TOKEN_LIMIT`, keeps
  reasoning hidden and at low effort, and lets the SDK wait out 429s.
- Gemini retries 503/429 twice with backoff; Anthropic's SDK does this itself.

## Discussion panel

- One thread per (user, problem) in `chat_threads`; messages ordered by `chat_messages.seq`.
- `POST /api/submissions/{id}/chat` stores the user turn plus a `streaming` assistant row and
  queues `chat_reply` in the worker (keys are only decrypted there). The worker publishes the
  full text so far to `hb:chat:{message_id}`; `GET /api/chat/messages/{id}/events` relays it.
- Context = problem + code + latest review JSON (`app/chat/prompts.py`). Turns beyond
  `CHAT_HISTORY_CHAR_BUDGET` are folded into `chat_threads.summary`.
