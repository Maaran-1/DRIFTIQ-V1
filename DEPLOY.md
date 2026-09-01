# Deploying DRIFTIQ (pilot)

One service: FastAPI serves both the API and the frontend. Postgres lives on
Neon (free tier). ASR and LLM run on free-tier APIs — local Whisper and Ollama
stay dev-only (free hosts have < 2 GB RAM).

**Recommended stack: Railway (app) + Neon (Postgres) + Gemini (LLM) + Groq (ASR).**

---

## 1. Collect the keys (10 minutes, all free)

| What | Where | Notes |
|---|---|---|
| Neon Postgres | https://neon.tech → New project | Copy the **connection string** (`postgresql://…sslmode=require…`). The app handles the asyncpg SSL translation itself. |
| Gemini API key | https://aistudio.google.com/apikey | Free tier ≈ 1M tokens/day ≈ 30 lectures/day |
| Groq API key | https://console.groq.com/keys | Whisper Large-v3, free tier |
| JWT secret | run `openssl rand -hex 32` (or any 32+ char random string) | Never reuse the dev default |

## 2. Environment variables to set on the host

```
DATABASE_URL = <Neon connection string>
JWT_SECRET   = <random 32+ chars>
LLM_PROVIDER = gemini
GEMINI_API_KEY = <key>
ASR_PROVIDER = groq
GROQ_API_KEY = <key>
```

Everything else has sane defaults (`PORT` is injected by the host;
`UPLOAD_DIR` defaults to `/tmp/driftiq_uploads`). Optional tuning:
`MAX_UPLOAD_MB` (default 200) rejects larger uploads with a 413;
`ASR_CHUNK_MB` (default 20) is the per-request size cap for API ASR —
bigger transcoded files are split into sequential chunks automatically.

**ffmpeg** is provisioned automatically: the app prefers a system ffmpeg
but falls back to the static binary from the `imageio-ffmpeg` package,
which pip installs on any host (Render's Python runtime has no apt).

## 3a. Railway (recommended)

1. Push this repo to GitHub.
2. https://railway.app → **New Project → Deploy from GitHub repo**.
3. Railway reads `railway.toml` automatically: build via Nixpacks, start via
   `backend/start.sh` (runs `alembic upgrade head`, then uvicorn), health check
   on `/api/health`.
4. In the service → **Variables**, add the table from step 2.
5. **Settings → Networking → Generate Domain** for a `*.up.railway.app` URL,
   or add a custom subdomain (e.g. `driftiq.yourdomain.in`) — Railway shows the
   CNAME record to create at your DNS provider.

## 3b. Render (alternative)

1. https://render.com → **New → Blueprint**, point it at the repo — it reads
   `render.yaml` (free web service, same start script, auto-generated
   `JWT_SECRET`).
2. Fill in the `sync: false` variables (DATABASE_URL, GEMINI_API_KEY,
   GROQ_API_KEY) when prompted.
3. Note: Render's free tier sleeps after 15 min idle; first request takes
   ~30 s to wake. Railway's trial credit avoids this.

## 4. Verify the deployment

1. `GET https://<your-domain>/api/health` → `{"status":"ok","asr_provider":"groq","llm_provider":"gemini"}`
2. Open the site → create an account → sign in.
3. Paste any lecture-like text into "Extract notes from this transcript" —
   verifies the Gemini key without needing audio.
4. Upload a short audio clip (or record 30 s) — verifies the Groq key and the
   full pipeline; the lecture should appear in the dashboard as DRAFT.
5. Open the lecture → Publish → open the public `/notes/<slug>` link in a
   private/incognito window (no login should be needed).

## 5. Operational notes

- **Migrations** run automatically on every deploy (`start.sh`). To roll back
  a bad migration: `alembic downgrade -1` from a local shell pointed at the
  production `DATABASE_URL`.
- **Audio is not retained.** Uploads stream to `/tmp`, get transcoded to
  16 kHz mono MP3 (a 50-min lecture ≈ 12 MB) for transcription, and both
  files are deleted when processing ends — memory and disk stay flat on a
  512 MB instance. Only the transcript + notes live in Postgres. Durable
  audio storage (R2/Supabase), if ever wanted, is a Week 5+ item.
- **Cost guardrail**: Gemini free tier covers ~30 lectures/day. If
  `/api/process` starts returning quota errors, flip `LLM_PROVIDER` and add
  the corresponding key — no redeploy needed beyond a variable change.
- **Lecture length**: long files no longer risk OOM (transcode + chunked
  transcription bound memory), but processing is still synchronous — the
  browser waits while ASR + LLM run. Keep pilot recordings modest until the
  job queue lands (see CLAUDE.md §4, async processing).
