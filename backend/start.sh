#!/usr/bin/env bash
# DRIFTIQ — production start: apply migrations, then serve.
# Used by Railway (railway.toml) and Render (render.yaml).
set -e
cd "$(dirname "$0")"
alembic upgrade head
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
