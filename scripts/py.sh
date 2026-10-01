#!/bin/sh
# Runs the backend CLI from anywhere: scripts/py.sh tenant:validate graphite
cd "$(dirname "$0")/../api" && exec .venv/bin/python -m app.cli "$@"
