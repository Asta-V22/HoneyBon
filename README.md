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

# in another terminal
cd frontend
npm install
npm run dev                   # http://localhost:5173
```

## Status

Phase 1 (Core) in progress: foundations only — review schema, data model, provider interface, app shell.
