# Honeybon

Honeybon captures every coding solution you submit, returns a four-tier AI review (your code improved → slightly better → optimal → CP master), and shows which techniques you avoid even when they're optimal.

See [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) for the full product spec.

## Quick start

Prerequisites: Docker, [uv](https://docs.astral.sh/uv/), Node 20+.

```sh
docker compose up -d

cd backend
cp .env.example .env          # then set MASTER_KEY (command in the file)
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
uv run arq app.worker.main.WorkerSettings   # in another terminal: the review worker

# in another terminal
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

## Deploying

Free-tier setup on Vercel, Render and Neon: see [`docs/DEPLOY.md`](docs/DEPLOY.md).

## Status

Phase 1 (Core) is built: GitHub login (plus a local dev login), provider keys, manual paste, the two-call review pipeline with Anthropic, Gemini and Groq, live progress over SSE, and the Review, Library, Paste, Settings and Today screens. From Phase 2, the discussion panel is done. Next: the first deployment, then the LeetCode extension.
