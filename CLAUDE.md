# DRIFTIQ — Claude Code project brief

> This file gives Claude Code everything it needs to keep building DRIFTIQ
> from where the Cowork sessions left off. Read it before every session
> and refer back to it when making design decisions.

---

## 1. What DRIFTIQ is

**DRIFTIQ** is an AI-powered classroom documentation and knowledge management
platform for Indian higher-education institutions. It records a lecture, transcribes
it (multilingual), interprets it with an LLM, extracts structured knowledge
(definitions, formulas, examples, assignments), aligns spoken explanations with the
professor's uploaded slides, and produces a formatted lecture note plus a
searchable institutional knowledge repository.

**Prepared by:** D Maaran — Department of CSE (Core), SCOPE, VIT Chennai.
**Current TRL:** 3 (experimental proof of concept). Target: TRL 6 within 24 months.

## 2. Current codebase state (Cowork MVP v2)

```
driftiq_mvp/
├── backend/
│   ├── main.py         # FastAPI: /api/health, /api/process, /api/extract, serves frontend
│   ├── config.py       # env-driven config (LLM_PROVIDER, ASR_PROVIDER, keys)
│   ├── asr.py          # Whisper providers: local | groq | openai
│   ├── llm.py          # LLM providers:    ollama | gemini | openai | claude
│   ├── extract.py      # Prompt + JSON schema + Markdown renderer
│   └── requirements.txt
├── frontend/
│   └── index.html      # Single-page app: setup → record → notes
├── .env / .env.example
├── run.sh
└── README.md
```

**What already works:**
- Single-page web UI with class-setup form (subject, classroom, end-time, remind-before)
- Browser mic recording with live countdown timer + audible chime + banner reminders
  at T-N min, T-1 min, T-0
- "★ Mark this moment" button → captures timestamps → sent to backend as `moments`
- Audio file upload path (skip mic)
- Text-only extraction (skip audio) for LLM testing
- Full pipeline: audio → Whisper transcript → LLM structured extraction → Markdown
- Structured note schema:
  `subject, topics[], definitions[], formulas[], examples[], assignments[],
   highlights[] (from bookmarks), recap (3-min summary), key_takeaways[]`
- Provider abstraction: switch ASR/LLM via `.env` — no code change

## 3. Where we're going — the 12-week plan

### Weeks 1–4 → "Working pilot" (blocking before we can hand to any professor)

1. **PostgreSQL persistence** (Neon or Supabase free tier) — SQLAlchemy + Alembic
   - Tables: `users`, `subjects`, `classrooms`, `lectures`, `notes`, `notes_versions`
2. **Email + password login** with JWT (skip SSO for pilot)
3. **Professor dashboard** — list of past lectures, drafts vs published
4. **Faculty review + publish workflow** — notes land as Draft, editable, then Publish
5. **Public student view** at `/notes/<slug>` — read-only, nice typography, no login needed
6. **Deployment**: Railway or Render backend, custom subdomain, Gemini for LLM
   (Ollama can't run on free-tier hosts — < 2 GB RAM)

### Weeks 5–8 → "Attractive pilot" (differentiators + student features)

7. **Ask DRIFTIQ** — chat over published lectures. Student types a question, gets
   an answer grounded in the lecture, with a citation to timestamp + slide.
   This is the killer student feature — build it well.
8. **Slide upload + slide alignment** — PPT/PDF parse, embed with pgvector,
   assign each topic segment to the best-matching slide via cosine similarity.
9. **Student doubt-tagging** — student hits "I'm confused" on any paragraph,
   flag lands in the professor's dashboard as an aggregated heatmap.
10. **Missed-class recap page** at `/recap/<slug>` — expose the `recap` field
    as a nicely-styled standalone page (LinkedIn-shareable).
11. **Search across all published lectures** in a subject (semantic + keyword
    via pgvector).

### Weeks 9–12 → "Defensible product"

12. Faculty analytics: viewing rates, doubt density per lecture
13. Assignment tracker: extract deadlines and remind students
14. Onboard 2–3 more pilot professors
15. Bug-fix + polish based on real usage
16. Pilot LoI outreach — collect signed intent from 1 institution
17. Deploy DPDPA compliance page (consent language, retention, data-rights)

## 4. Architecture principles — do not violate

Every design decision must respect these:

- **Provider substitutability** — ASR and LLM calls MUST go through the abstractions
  in `asr.py` and `llm.py`. Never hard-code a specific provider anywhere else.
- **Human-in-the-loop by default** — nothing gets published to students without an
  explicit professor "Publish" action. Draft state exists for a reason.
- **Span grounding** — every extracted knowledge element must be traceable to a
  transcript span. If the LLM invents something it can't ground, discard it.
- **Multi-tenant isolation** — when tenancy is added, no query in one tenant may
  return, mutate, or observe data from another tenant. Enforce at the query layer.
- **DPDPA-aware** — audio retention default 90 days. Consent capture is a first-class
  entity. Data-principal rights (access, correction, erasure) must be reachable.
- **Async processing** — long ASR/LLM jobs must not block the HTTP request handling
  the recording upload. Currently synchronous; upgrade to a job queue (Redis/Celery
  or ARQ) when lectures cross ~10 min.

## 5. Cost model (single-most-important constraint)

Per 50-min lecture in production:
- **Self-hosted Whisper + open LLM (Ollama on GPU):** ~₹10–20/lecture
- **Paid APIs (Whisper API + GPT-4o-mini / Claude Haiku):** ~₹40–70/lecture

Break-even for self-hosting: ~600 lectures/month.

**For deployed MVP (Weeks 1–4):** use **Gemini 2.0 Flash free tier** — 1 M tokens/day
is enough for ~30 lectures/day for free. When we cross that, flip to paid Gemini or
Claude Haiku. Ollama stays for local dev only.

## 6. Tech stack (locked)

- **Backend**: FastAPI (Python 3.10+), SQLAlchemy 2.x, Alembic
- **DB**: PostgreSQL 15+ with `pgvector` extension (Neon or Supabase for MVP)
- **Object storage**: S3-compatible (Cloudflare R2 or Supabase storage for MVP)
- **Async queue**: ARQ (Redis-backed) when needed
- **ASR**: `faster-whisper` local, or Groq / OpenAI API
- **LLM**: Ollama local, or Gemini / OpenAI / Anthropic API
- **Frontend**: single-page HTML for MVP → **Next.js 14 (App Router) + Tailwind**
  when we hit multi-page (student view, dashboard, search)
- **Deploy**: Railway or Render (backend), Vercel (frontend when split)
- **Auth**: JWT + bcrypt (pilot), SAML 2.0 / OIDC (institutional, later)
- **LMS integration**: IMS LTI 1.3 (later, not in pilot)

## 7. Competitive positioning — what to lean into

Direct competitors: Otter.ai, Fireflies.ai, Panopto, Zoom AI Companion.
DRIFTIQ's three real moats:
1. **Slide-aligned notes** — competitors don't have this.
2. **Multilingual + code-switched Indian classroom speech** (English + Hindi/Tamil/etc.).
3. **Institutional knowledge repository with faculty review workflow** — competitors
   give notes to individuals, not institutions.

**Do not spend time on**: speaker separation, meeting summaries, calendar
integration — those are Otter's game, we lose it.

## 8. What NOT to build (yet)

- SSO / SAML / OIDC (email login is fine for pilot)
- LMS integration (LTI 1.3) — build when a customer asks
- Full DPDPA dossier — a consent checkbox + retention policy is enough for pilot
- Native mobile app (responsive web works)
- Admin panel — one config file suffices for pilot
- Attendance system — we only do the reminder chime, nothing else
- Video capture (audio-only)
- Auto-quizzes / flashcards / translation — v1.5 features

## 9. Working conventions for Claude Code

- **Always** run tests / smoke checks after non-trivial changes
- **Never** commit `.env` — only `.env.example`
- **Migrations** for every schema change (`alembic revision --autogenerate`)
- Keep the provider abstractions in `asr.py` / `llm.py` clean — add new providers
  as new functions, register in `_ROUTES`
- Prefer **small PRs / commits** — one feature per commit
- Frontend HTML is currently one file. When it exceeds ~1000 lines, port to Next.js.
- The `extract.SYSTEM_PROMPT` is the product; any change to it must be reviewed
  carefully — it's the schema contract the frontend and future features depend on.

## 10. First-session priorities for Claude Code

Suggested order to bring the project to "working pilot":

1. Add PostgreSQL + models + Alembic migrations (`users`, `lectures`, `notes`)
2. Add JWT-based email/password auth on FastAPI
3. Wire up ownership — each lecture belongs to a user
4. Build professor dashboard page (list of lectures with statuses)
5. Add Draft / Published states to notes; add a `/publish/<id>` endpoint
6. Add read-only `/notes/<slug>` public student view
7. Deploy to Railway with Postgres + Gemini free tier

Then move to Weeks 5–8 (Ask DRIFTIQ, slide upload, doubt-tagging).

## 11. Key source-of-truth documents (from Cowork)

If you have them locally, cross-reference:
- **DRIFTIQ Concept Validation Report** (TRL 3 evidence, full concept)
- **DRIFTIQ Software Requirements Specification** (IEEE 830 format, 58 REQs)
- **DRIFTIQ Project Plan + WBS + Gantt** (24-month TRL 1→6 roadmap)
- **DRIFTIQ DFD + ER Diagrams** (Lab 2 submission)

If you don't have them, ask the user; the SRS especially defines every functional
requirement (REQ-001 through REQ-058) and non-functional requirement
(PER/SAF/SEC/QAT/BR).

---

*Last synced from Cowork: MVP v2 — audio-to-notes with reminders and bookmarks.*
*Next milestone: PostgreSQL + auth + dashboard + student view + deployment.*
