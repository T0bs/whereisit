#!/usr/bin/env bash
# Open an interactive mysql prompt against the running docker compose `db` container.
# Usage:
#   scripts/db_mysql.sh                 # connect as `whereisit` to the `whereisit` DB
#   scripts/db_mysql.sh --root          # connect as root
#   scripts/db_mysql.sh -- -e "SHOW TABLES"   # pass extra args through to mysql

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

USER="whereisit"
PASS="whereisitpw"
if [ "${1:-}" = "--root" ]; then
  USER="root"
  PASS="rootpw"
  shift
fi

# Drop a leading `--` so callers can cleanly separate script args from mysql args.
if [ "${1:-}" = "--" ]; then shift; fi

if ! docker compose ps --status running --services 2>/dev/null | grep -qx db; then
  echo "db container is not running. Start it with: docker compose up -d db" >&2
  exit 1
fi

exec docker compose exec db mysql -u "$USER" "-p$PASS" whereisit "$@"
