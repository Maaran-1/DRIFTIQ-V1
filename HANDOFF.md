# Handoff: Cowork → Claude Code

You were building this in Cowork and are now moving to Claude Code
to build out weeks 1–12 (persistence → auth → dashboard → student view →
deployment → Ask DRIFTIQ → slide alignment → doubts → recap → search).

## Quick start with Claude Code

```bash
# 1) Install Claude Code (one-time)
npm install -g @anthropic-ai/claude-code

# 2) In this project directory
git init && git add . && git commit -m "MVP v2 from Cowork"
claude                                  # login flow opens first time

# 3) Ask it to read the brief before anything else
> Read CLAUDE.md and give me back a one-paragraph summary
> of what DRIFTIQ is and what the next milestone is.
```

If the summary matches your mental model, you're good — Claude Code has
inherited the full context.

## Suggested first prompt for Week 1

```
Read CLAUDE.md carefully. We are starting Week 1 of the 12-week plan
in section 3.

Task: add PostgreSQL persistence to the FastAPI backend without breaking
the existing endpoints.

Do this incrementally:
1) Add sqlalchemy, alembic, psycopg[binary], asyncpg to requirements.txt
2) Create backend/db.py with an async SQLAlchemy engine + session dependency
3) Create backend/models.py with User, Lecture, Note, NoteVersion models
4) Set up Alembic and generate the initial migration
5) Update /api/process to persist the lecture + note (attributing to a
   placeholder user for now — real auth comes in the next task)
6) Add /api/lectures GET endpoint listing lectures
7) Commit after each step so I can review

Use DATABASE_URL from .env. If DATABASE_URL is not set, fall back to
SQLite so local dev still works without Postgres.
```

## Working style tips

- **Commit after every non-trivial change.** Claude Code is careful with
  git — use `/git` slash command or ask it to commit.
- **Ask for tests** — "add a pytest for this" — it will write them.
- **Use `/plan`** before big changes — Claude Code will draft the plan
  for approval before touching files.
- **Reference REQ numbers** — CLAUDE.md mentions the SRS uses REQ-001…058.
  If you upload the SRS to the project, Claude Code can trace every change
  back to a requirement.
- **Read `.env.example` for what to set locally** — don't commit `.env`.

## After each milestone

Come back to the SRS / Concept Report / Project Plan (from Cowork) and
update them if scope shifts. Claude Code can't update those — it lives
in this repo.
