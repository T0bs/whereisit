# AGENTS.md

Guide for coding agents (and humans) working in this repo. Copy-paste recipes for the everyday loop.

## Project overview

`whereisit` is a personal inventory manager: track tools/items and where they live (drawers, boxes, shelves).

- **Backend**: FastAPI on `:8000` — entrypoint [backend/app/main.py](backend/app/main.py)
- **Frontend**: React + Vite on `:5173` — entrypoint [frontend/src/App.jsx](frontend/src/App.jsx)
- **DB**: MySQL 8 via [docker-compose.yml](docker-compose.yml). SQLite fallback (`whereisit.db`) when `DATABASE_URL` is unset.
- **Migrations**: Alembic — config [alembic.ini](alembic.ini), versions in [alembic/versions/](alembic/versions/)

## Prerequisites

- Python 3.12 venv at `.venv/` (the active one — **not** `venv/`, which is stale)
- Node + npm
- Docker (for MySQL)

## First-time setup

```bash
# Backend
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd frontend && npm install && cd ..

# DB
docker compose up -d db

# Wait for MySQL to accept connections (first boot can take ~30s)
until docker compose exec -T db mysqladmin ping -h 127.0.0.1 -u whereisit -pwhereisitpw --silent; do sleep 2; done

# Apply migrations against MySQL
DATABASE_URL="mysql+pymysql://whereisit:whereisitpw@127.0.0.1:3306/whereisit" \
  .venv/bin/alembic upgrade head
```

## Start everything

Background processes with PID + log files (matches the existing convention):

```bash
docker compose up -d db

# Backend (port 8000)
DATABASE_URL="mysql+pymysql://whereisit:whereisitpw@127.0.0.1:3306/whereisit" \
  nohup .venv/bin/uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000 \
  > backend.log 2>&1 &
echo $! > backend.pid

# Frontend (port 5173)
( cd frontend && nohup npm run dev > ../frontend.log 2>&1 & echo $! > ../frontend.pid )
```

The recipes above each background a single command (no `&&` chain before the `&`) so `$!` reliably captures the right PID. Killing that PID brings down the whole child tree.

Without `DATABASE_URL`, the backend falls back to SQLite (`whereisit.db`) — fine for quick tinkering, but the canonical workflow is MySQL.

Then open:
- App: http://localhost:5173
- API: http://localhost:8000
- Swagger: http://localhost:8000/swagger
- ReDoc: http://localhost:8000/redoc

## Stop everything

```bash
[ -f backend.pid ]  && kill "$(cat backend.pid)"  && rm backend.pid
[ -f frontend.pid ] && pkill -P "$(cat frontend.pid)"; kill "$(cat frontend.pid)" 2>/dev/null; rm -f frontend.pid
docker compose down
```

The frontend kill uses `pkill -P` to also reap the `sh -c vite` / `node` children that `npm run dev` spawns.

Fallback if PID files are stale or missing:

```bash
pkill -f "uvicorn backend.app.main"
pkill -f "vite"
```

## Reload

- **Backend**: `uvicorn --reload` watches files and auto-reloads on save. No action needed.
- **Frontend**: Vite HMR auto-reloads in the browser on save.
- **Hard restart**: run Stop, then Start.

## Auth

Single-token Bearer auth gated by the `WHEREISIT_TOKEN` env var (implemented in [backend/app/auth.py](backend/app/auth.py)).

- **Unset / empty** → dev mode, every endpoint is open.
- **Set** → every endpoint except `/health` requires `Authorization: Bearer <token>`; mismatched or missing header returns `401` with a `WWW-Authenticate: Bearer` header.

```bash
# Strict mode
export WHEREISIT_TOKEN=$(openssl rand -hex 32)
curl -H "Authorization: Bearer $WHEREISIT_TOKEN" http://localhost:8000/items/

# Swagger UI works too — click "Authorize" and paste `Bearer <token>`.
```

The check lives in a single middleware function so swapping for JWT/OAuth later is a one-file change.

## Tests

Backend tests live in [tests/](tests/) and run against the docker-compose MySQL in a dedicated `whereisit_test` database (created/dropped per session by the fixture in [tests/conftest.py](tests/conftest.py)).

```bash
. .venv/bin/activate
docker compose up -d db      # tests need the MySQL container
pytest                       # all backend tests
pytest tests/test_health.py  # single file
pytest -k health             # by keyword
```

The fixture connects as MySQL `root` (password `rootpw`, matches [docker-compose.yml](docker-compose.yml)) to `CREATE DATABASE` and grant the `whereisit` user access. Override defaults with env vars when needed: `WHEREISIT_TEST_DATABASE_URL`, `WHEREISIT_TEST_DB_HOST`, `WHEREISIT_TEST_DB_PORT`, `WHEREISIT_TEST_DB_ROOT_USER`, `WHEREISIT_TEST_DB_ROOT_PASSWORD`, `WHEREISIT_TEST_DB_NAME`, `WHEREISIT_TEST_DB_APP_USER`.

The frontend has no test runner configured.

## Database

Inspect the DB:

```bash
# MySQL (docker compose workflow) — interactive prompt
scripts/db_mysql.sh

# Pass-through args, e.g. one-shot query
scripts/db_mysql.sh -- -e "SHOW TABLES;"

# Connect as root
scripts/db_mysql.sh --root

# SQLite fallback (when DATABASE_URL is unset)
scripts/db_connect.sh
```

[scripts/db_mysql.sh](scripts/db_mysql.sh) shells into the running `db` container via `docker compose exec`. [scripts/db_connect.sh](scripts/db_connect.sh) only supports the `sqlite://` scheme.

Add a migration:

```bash
. .venv/bin/activate
export DATABASE_URL="mysql+pymysql://whereisit:whereisitpw@127.0.0.1:3306/whereisit"
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

## Layout pointers

- Routers: [backend/app/routers/](backend/app/routers/) — `items`, `containers`, `placements`, `tags`, `views`
- Models: [backend/app/models/](backend/app/models/) (plus [backend/app/models.py](backend/app/models.py))
- DB session: [backend/app/database.py](backend/app/database.py) — reads `DATABASE_URL`, defaults to `sqlite:///./whereisit.db`
- Frontend pages: [frontend/src/pages/](frontend/src/pages/)
- Frontend components: [frontend/src/components/](frontend/src/components/)

## Gotchas

- **Two venvs exist** (`.venv/` and `venv/`). Only `.venv/` is active. Ignore `venv/`.
- **`DATABASE_URL` must be set** for the backend to use MySQL. Without it, the app silently falls back to SQLite and any data you saved via Docker won't show up.
- **Vite port fallback**: if `:5173` is in use, Vite picks `:5174` (visible in [frontend.log](frontend.log)). Update the URL you open accordingly.
- **Frontend API base URL**: defaults to `http://127.0.0.1:8000`. Override with `VITE_API_URL` if the backend isn't on localhost:8000.
- **CORS**: the backend enables CORS for all origins in dev — see [backend/app/main.py](backend/app/main.py).
