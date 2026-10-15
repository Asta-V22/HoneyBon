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
- `extension/` — Chrome MV3 extension (TypeScript, esbuild). LeetCode specifics only in
  `src/leetcode.ts`; build with `npm run build`, load `extension/dist` unpacked

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
  Database problems use the `sql_*` techniques; their complexity is estimated in table rows.
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

## Deployment (see docs/DEPLOY.md)

- Vercel serves `frontend/` and proxies `/api/*` to Render (`frontend/vercel.json`), so the session
  cookie stays first-party. Never call the onrender.com URL from the browser directly.
- Render runs `backend/Dockerfile` (migrations on start) from `render.yaml`, with the worker inside
  the API (`RUN_WORKER_IN_API=true`) and a non-persistent free Key Value as Redis; Postgres is Neon.
- `app/worker/recovery.py` re-queues unfinished reviews and fails interrupted chat replies on worker
  start; job IDs (`review:<id>`, `chat:<id>`) make re-queueing idempotent.
- `KEEP_AWAKE=true` pings the public `RENDER_EXTERNAL_URL/healthz` every 50 s (`app/core/keep_awake.py`)
  so the free service never sleeps. `/healthz` must stay DB-free so Neon can still scale to zero.
- `ENV` other than `dev` requires `SESSION_SECRET`, `MASTER_KEY` and an https `FRONTEND_ORIGIN`
  (`Settings.check_production`). All `/api` responses are `Cache-Control: no-store`.

## Capture (Phase 2)

- Extension tokens (`/api/me/tokens`) authenticate only `/api/capture*` (`app/api/capture.py`);
  stored as SHA-256 hashes. Capture honours the user's mode: off → ignored, capture → review
  queue (status `queued` with no review row), analyze → review queued immediately.
- `(user_id, external_id)` is unique, so a LeetCode submission is never captured twice.
- LeetCode metadata (title, difficulty, tag slugs, internal question ID) comes from the public
  GraphQL API (`app/leetcode.py`), fetched by the `fetch_problem_metadata` job and before a review.
  It is blocked from Render's IPs in practice, so the extension also reads the metadata from
  LeetCode in the user's browser and sends it with each capture, and backfills problems still
  missing it; those values only fill empty fields. Never fatal either way. Tests set
  `LEETCODE_METADATA=false`.

## Import and insights (Phase 3)

- GitHub import (`app/imports/`) reads a **public** repo as one tarball from codeload.github.com
  (no API rate limit, no GitHub permissions), in memory only. LeetHub folders are
  `<internal question ID>-<slug>`; title and difficulty come from each README's header, and the
  README statement is never stored. Other folders with code go to `import_jobs.unmatched_folders`
  for manual mapping or skipping.
- Imported submissions have status `imported` until analysed and stay off Today. Dedupe: the
  external ID hashes repo + path + normalized code, and identical code already captured for the
  same problem (any source) is skipped, so re-syncing is safe.
- Analysis is chosen after the fetch: `tags_only` (one `TechniqueTags` call, stored as a review of
  kind `tags` whose JSON is a verdict with empty lists), `full`, or `none`. `analyze_import` runs in
  ~4-minute slices that re-queue themselves, one submission at a time, under a Redis lock; it stops
  after 3 failures in a row and can be cancelled and resumed.
- Insights (`app/insights.py`, pure functions) use one row per problem: its latest submission with
  a successful analysis. Rows of the matrix = the technique needed (the one used if it matched,
  else the first optimal), columns = used. Low confidence = LeetCode tags imply techniques and none
  is in the AI's optimal set (`TAG_TECHNIQUES`). The insight card needs `INSIGHT_MIN_PROBLEMS` (5)
  and ignores low-confidence problems.
- Topic tags for imports come from the extension: it polls `/api/capture/metadata/missing` every
  30 minutes and posts LeetCode's metadata back (`/api/capture/metadata`, user's own problems only).

## Verify on LeetCode

- Each tier's code on Review has a "Verify on LeetCode" button (`components/VerifyOnLeetCode.tsx`),
  LeetCode problems only. Honeybon never executes code: there is no sandbox, and AI output is
  never presented as a run result.
- With extension ≥ 0.3.0 (detected via `data-honeybon-extension` on `<html>`, set by
  `extension/src/bridge.ts`), the code goes page → bridge → background (`chrome.storage.session`,
  30 min) → a bar on the LeetCode problem page; its Paste button makes the MAIN-world page hook
  replace the Monaco editor's text as one undoable edit. Without the extension the code is
  copied to the clipboard. The tab is opened inside the click so it isn't pop-up blocked.

## Providers

- Model lists and defaults: `PROVIDER_MODELS` in `app/providers/__init__.py` (first = default).
- Groq: free tier counts prompt + `max_completion_tokens` against 8K tokens/minute and rejects a
  single larger request (413). The adapter sizes output to fit `GROQ_REQUEST_TOKEN_LIMIT`, keeps
  reasoning hidden and at low effort, and lets the SDK wait out 429s.
- Gemini retries 503/429 twice with backoff; Anthropic's SDK does this itself.
- Groq strict mode rejects schema-breaking output with a 400 (`json_validate_failed`); the adapter
  returns its `failed_generation` as an ordinary invalid response so the repair retry still runs.

## Discussion panel

- One thread per (user, problem) in `chat_threads`; messages ordered by `chat_messages.seq`.
- `POST /api/submissions/{id}/chat` stores the user turn plus a `streaming` assistant row and
  queues `chat_reply` in the worker (keys are only decrypted there). The worker publishes the
  full text so far to `hb:chat:{message_id}`; `GET /api/chat/messages/{id}/events` relays it.
- Context = problem + code + latest review JSON (`app/chat/prompts.py`). Turns beyond
  `CHAT_HISTORY_CHAR_BUDGET` are folded into `chat_threads.summary`.
