# DRIFTIQ — MVP (Phase 2)

Lecture audio → transcript → **structured notes** (definitions, formulas, examples,
assignments, key takeaways). Runs as a web app in your browser, backed by a small
FastAPI server. Swappable ASR (Whisper) and LLM (Ollama / Gemini / OpenAI / Claude)
providers behind a single `.env` config switch.

## What you get

- **Frontend** at `http://localhost:8000` — record from your microphone *or* upload an
  audio file, watch structured notes appear.
- **Backend** `POST /api/process` — one endpoint, audio in → JSON + Markdown out.
- **/api/extract** — skip audio, paste text, test the LLM only.

## Requirements

- Python **3.10+**
- **ffmpeg** installed (used by Whisper to decode audio)
- One LLM provider set up (see below)

## Quick start (fully free — Ollama + local Whisper)

```bash
# 1) Install ffmpeg
#    macOS:    brew install ffmpeg
#    Ubuntu:   sudo apt install ffmpeg
#    Windows:  https://ffmpeg.org/download.html and add to PATH

# 2) Install Ollama and pull a model (free, runs locally)
#    Download: https://ollama.com/download
ollama pull llama3.1:8b
# leave Ollama running in the background (its default port is 11434)

# 3) Clone / unzip this project, then:
cd driftiq_mvp
python -m venv .venv
source .venv/bin/activate               # Windows: .venv\Scripts\activate
pip install -r backend/requirements-local.txt   # includes local Whisper

# 4) Copy the sample .env and keep the defaults (Ollama + local Whisper)
cp .env.example .env

# 5) Run
bash run.sh
# → open http://localhost:8000 in Chrome / Edge / Safari
```

The first run of local Whisper will download the `base` model (~150 MB). After
that it's fully offline and free.

## Switching providers

Edit `.env` — no code changes needed.

### Use Google Gemini (free tier, cloud)

```
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_from_https://aistudio.google.com/apikey
```

### Use OpenAI

```
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_LLM_MODEL=gpt-4o-mini
```

### Use Anthropic Claude

```
LLM_PROVIDER=claude
CLAUDE_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-haiku-4-5
```

### Use Groq for ASR (fast, free tier)

```
ASR_PROVIDER=groq
GROQ_API_KEY=your_key_from_https://console.groq.com/keys
```

Restart the server after editing `.env`.

## Project layout

```
driftiq_mvp/
├── backend/
│   ├── main.py             # FastAPI app
│   ├── config.py           # env-driven config
│   ├── asr.py              # Whisper providers (local | groq | openai)
│   ├── llm.py              # LLM providers (ollama | gemini | openai | claude)
│   ├── extract.py          # prompt + structured extraction + Markdown render
│   └── requirements.txt
├── frontend/
│   └── index.html          # single-page app (record + upload + display)
├── .env.example
├── run.sh
└── README.md
```

## Try it without a microphone

- Click **"Extract notes from this transcript"** and paste any lecture-like text.
  This tests your LLM connection without needing audio or Whisper.
- Or upload a short `.mp3` / `.wav` sample.

## Cost expectations at MVP scale

| Provider | Approx cost per 50-min lecture |
|---|---|
| Ollama (local)               | **₹0** (needs 8 GB+ RAM) |
| Gemini free tier             | **₹0** (up to 1M tokens/day) |
| OpenAI GPT-4o-mini           | ~₹0.30 |
| Claude Haiku                 | ~₹0.50 |
| OpenAI Whisper API           | ~₹25 per lecture |
| Local Whisper                | **₹0** |
| Groq Whisper                 | **₹0** on free tier |

## Deploying as a real web app

See **[DEPLOY.md](DEPLOY.md)** — step-by-step Railway (or Render) + Neon
Postgres + Gemini/Groq setup. The repo ships ready to deploy: `railway.toml`,
`render.yaml`, and `backend/start.sh` (migrations, then serve) are all wired.

## What's next (Milestone 3+)

- Login + multi-user (SSO via SAML/OIDC)
- PostgreSQL persistence (multiple lectures, faculty review, publication)
- Slide upload + slide-alignment
- Searchable knowledge repository
- Faculty review + student view workflows

Not in this MVP — see the SRS document for the full spec.
