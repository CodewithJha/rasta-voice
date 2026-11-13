#!/bin/sh
set -eu
# Spaces listens on 7860. Render and similar platforms inject PORT.
port="${PORT:-7860}"
exec uvicorn rasta.main:app --host 0.0.0.0 --port "$port" --workers 1
