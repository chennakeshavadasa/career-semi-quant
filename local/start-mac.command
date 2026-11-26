#!/usr/bin/env bash
# Double-click in Finder to start Semi Quant Terminal (macOS). The first run installs
# everything into a private .venv folder; your browser opens when it is ready.
# If macOS blocks it: right-click > Open, or run:  chmod +x start-mac.command
cd "$(dirname "$0")"
exec ./start-linux.sh "$@"
