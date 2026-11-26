#!/usr/bin/env bash
# Semi Quant Terminal (local) - first run creates a private Python environment in .venv
# (1-3 minutes), later runs start in a couple of seconds. Extra arguments go to semiquant,
# e.g.  ./start-linux.sh quote NVDA   or   ./start-linux.sh serve --port 9000
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "Python 3.10 or newer is required: https://www.python.org/downloads/"; exit 1
fi
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  echo "Python 3.10 or newer is required (found $("$PY" --version 2>&1))."; exit 1
fi
if [ ! -x .venv/bin/python ] || [ pyproject.toml -nt .venv/.installed ]; then
  echo "Setting up Semi Quant Terminal (first run or update: 1-3 minutes)..."
  [ -x .venv/bin/python ] || "$PY" -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -e .
  touch .venv/.installed
fi
exec .venv/bin/python -m semiquant "$@"
