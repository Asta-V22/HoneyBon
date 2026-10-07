# Deploying Honeybon (free tier)

| Piece | Host | Notes |
| --- | --- | --- |
| Frontend | Vercel (Hobby) | Static Vite build; `/api/*` is proxied to Render |
| API + review worker | Render free web service (Docker) | Worker runs inside the API (`RUN_WORKER_IN_API=true`) |
| Redis | Render free Key Value | Job queue and live progress; not persisted |
| Postgres | Neon free | Render's free Postgres expires after 30 days |

The browser only ever talks to the Vercel domain. Vercel forwards `/api/*` to Render
(`frontend/vercel.json`), so the httpOnly session cookie is first-party and login works in every
browser. Do not point the frontend straight at the onrender.com URL.

Do the steps in this order; each one produces something the next needs.

## 1. Neon (Postgres)

1. Create a project at [neon.tech](https://neon.tech). Pick the **AWS Asia Pacific (Singapore)**
   region to sit next to Render's Singapore region.
2. In **Connect**, turn **Connection pooling off** and copy the connection string. It looks like
   `postgresql://user:pass@ep-xxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require`.
   Use it as-is; the app converts it for asyncpg. (The pooled `-pooler` host does not work with
   asyncpg's prepared statements.)

## 2. Secrets

Generate a production encryption key, separate from your local one:

```sh
cd backend
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Keep a copy somewhere safe. It encrypts everyone's saved API keys; if it is lost or changed,
those keys can no longer be read and have to be entered again.

## 3. Vercel (frontend)

1. **Add New → Project**, import `Asta-V22/HoneyBon`.
2. Set **Root Directory** to `frontend`. Vercel detects Vite (build `npm run build`, output `dist`).
3. Deploy, then note the production URL, e.g. `https://honeybon.vercel.app`. Pages load now;
   API calls fail until Render is up.

## 4. GitHub OAuth app

GitHub → Settings → Developer settings → **OAuth Apps → New OAuth App**:

- Homepage URL: your Vercel URL
- Authorization callback URL: `<your Vercel URL>/api/auth/github/callback`

Copy the **Client ID**, then generate and copy a **Client secret**.

## 5. Render (API, worker, Redis)

1. **New → Blueprint**, connect `Asta-V22/HoneyBon`. Render reads `render.yaml` and creates
   `honeybon-api` and `honeybon-kv`.
2. Fill in the prompted values:
   - `DATABASE_URL`: the Neon string from step 1
   - `MASTER_KEY`: the key from step 2
   - `FRONTEND_ORIGIN`: your Vercel URL, no trailing slash
   - `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`: from step 4

   `SESSION_SECRET` is generated for you.
3. Apply. The first build takes a few minutes; migrations run on every start.
4. Check the service URL. If it is not `https://honeybon-api.onrender.com` (the name was taken),
   put the real URL in `frontend/vercel.json`, commit and push; Vercel redeploys.

## 6. Check it works

1. Open the Vercel URL. After a quiet spell the API is asleep and the page says it is waking up;
   this takes up to a minute.
2. Sign in with GitHub, add a provider key in Settings, paste a solution and watch the review fill
   in. That is the Phase 1 "done" bar.

## Living with the free tier

- **Sleep:** Render stops the API after 15 minutes without traffic; the next visit waits about a
  minute. Neon also pauses after 5 idle minutes and resumes in under a second.
- **Restarts:** Render's free Redis is not persisted. On start the worker queues any unfinished
  reviews again and marks interrupted chat replies as failed, so nothing is silently lost.
- **Long streams:** Vercel cuts proxied requests at 120 seconds. Progress streams reconnect on
  their own and the page refetches, so a slow review still finishes on screen.
- **Preview deployments:** GitHub login only works on the production URL, because the OAuth
  callback is fixed to it.
- **Logs:** Render dashboard → `honeybon-api` → Logs.
