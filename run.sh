#!/usr/bin/env bash
# DRIFTIQ MVP — start the backend
set -e
cd "$(dirname "$0")/backend"
exec python main.py
