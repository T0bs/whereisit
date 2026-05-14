#!/usr/bin/env bash
# Helper to connect to the project's DB for quick debugging.
# Usage: scripts/db_connect.sh [SQLITE_PATH] [-- <litecli args>]

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PIP="$ROOT_DIR/.venv/bin"

DB_URL="${DATABASE_URL:-sqlite:///$ROOT_DIR/whereisit.db}"

if [[ "$DB_URL" =~ ^sqlite3?:// ]]; then
  # Extract path after sqlite:/// or sqlite://
  DB_PATH="${DB_URL#sqlite://}" 
  DB_PATH="${DB_PATH#///}"
  # prefer litecli from venv if available
  if [ -x "$VENV_PIP/litecli" ]; then
    exec "$VENV_PIP/litecli" "$DB_PATH" "$@"
  elif command -v litecli >/dev/null 2>&1; then
    exec litecli "$DB_PATH" "$@"
  else
    # fallback to system sqlite3
    exec sqlite3 "$DB_PATH" "$@"
  fi
else
  echo "Unsupported DATABASE_URL scheme: $DB_URL" >&2
  exit 2
fi
