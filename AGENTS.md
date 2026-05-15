# AGENTS.md

Guide for coding agents (and humans) working in this repo. Copy-paste recipes for the everyday loop.

## Project overview

`whereisit` is a personal inventory manager: track tools/items and where they live (drawers, boxes, shelves).

- **Backend**: FastAPI on `:8000` — entrypoint [backend/app/main.py](backend/app/main.py)
- **Frontend**: React + Vite on `:5173` — entrypoint [frontend/src/App.jsx](frontend/src/App.jsx)
- **DB**: MySQL 8 via [docker-compose.yml](docker-compose.yml). Backend defaults to the docker-compose MySQL URL when `DATABASE_URL` is unset.
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

If `DATABASE_URL` is unset, the backend defaults to `mysql+pymysql://whereisit:whereisitpw@127.0.0.1:3306/whereisit` — same URL the docker-compose `db` service exposes — so the `DATABASE_URL=...` prefixes above are only needed when pointing at a different host.

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

## MCP server

[`scripts/wii_mcp`](scripts/wii_mcp) is an MCP stdio server that exposes the inventory operations as MCP tools. Claude Code picks it up automatically via [.mcp.json](.mcp.json) at the repo root — start a `claude` session inside the project and the tools appear in `/mcp`.

Tools (one per CLI subcommand plus convenience wrappers):
- **Navigation:** `find_nodes`, `get_node`, `get_children`, `get_path`, `get_tree`, `list_root_nodes`
- **Create / update:** `add_node`, `rename_node`, `update_node`, `move_node`, `delete_node`
- **Tags:** `add_tag`, `remove_tag`, `list_tags`
- **Kinds:** `list_kinds`, `create_kind`
- **Properties:** `set_property`, `list_properties`, `delete_property`

Each tool docstring documents when to use it and what each argument means — that text is the prompt the LLM sees.

Run it manually for debugging:

```bash
.venv/bin/python scripts/wii_mcp   # blocks on stdin, speaks JSON-RPC
```

## CLI

[`scripts/wii`](scripts/wii) is the everyday CLI. Stdlib-only (no venv needed), wraps the REST API, reads `WHEREISIT_API_URL` (default `http://127.0.0.1:8000`) and `WHEREISIT_TOKEN`.

```bash
# Inventory
scripts/wii add "Garage" --kind room --container
scripts/wii add "Cordless drill" --kind tool --parent 1 --tag metal --tag battery
scripts/wii find hammer
scripts/wii find --kind tool --tag metal
scripts/wii tree                 # all roots
scripts/wii tree 1               # subtree of node #1
scripts/wii move 5 --to 2        # reparent #5 under #2
scripts/wii move 5 --to root     # promote to top-level

# Tags
scripts/wii tag 5 add metal
scripts/wii tag 5 rm metal

# Properties
scripts/wii prop 5 set weight_g 600 --type int
scripts/wii prop 5 list
scripts/wii prop 5 rm weight_g

# Delete
scripts/wii rm 5
scripts/wii rm 5 --cascade       # delete the whole subtree

# Machine-readable
scripts/wii --json find hammer
```

Every command supports `--json` for agents; the default is pretty text.

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

## AI providers

[`backend/app/ai/`](backend/app/ai/) exposes an `LLMProvider` abstraction with `generate(messages)` and `tool_use_loop(messages, tools, on_tool_call)`. Two concrete providers ship out of the box:

- **`LocalProvider`** (default) — Ollama HTTP at `LLM_LOCAL_URL` (default `http://127.0.0.1:11434`), model `LLM_LOCAL_MODEL` (default `llama3.1:8b`). Zero marginal cost.
- **`AnthropicProvider`** — `claude-haiku-4-5` by default, override via `ANTHROPIC_MODEL`; requires `ANTHROPIC_API_KEY`. Calls are billed against the API key's account, separate from any Claude Code subscription.

Pick at runtime with `LLM_PROVIDER=local|anthropic` (default `local`):

```python
from backend.app.ai import get_provider, Message

provider = get_provider()                             # honours LLM_PROVIDER env var
result = provider.generate(
    [Message(role="user", content="Where can I find a hammer?")],
    system="You answer inventory questions.",
)
print(result.text, result.usage)
```

`AnthropicProvider` caches the system prompt by default (`cache_system=True` → top-level `cache_control: ephemeral`), which M9/M10 rely on for cheap repeat calls. `LocalProvider` ignores caching arguments.

The cascade orchestration — DB lookup → local LLM → cloud (opt-in with explicit confirmation) — lives in the `/ai/*` endpoints. No LLM SDK call should appear outside [backend/app/ai/](backend/app/ai/).

### Cloud kill switch

Tier 3 (Anthropic) is gated by **two** flags, both required:

1. **Server-side**: `WHEREISIT_CLOUD_ENABLED=true` on the backend process. Default is *off*.
2. **Per-request**: `confirm_remote: true` in the request body.

With the kill switch *off*, sending `confirm_remote: true` returns `400 cloud_disabled` — the server can't honour it. With the switch *on* and `confirm_remote` omitted/false, traffic stays on the local provider. Flip `WHEREISIT_CLOUD_ENABLED=true` only once the local stack (Ollama + local model) is validated end-to-end.

### `POST /ai/suggest-placement`

The first cascade endpoint (M9). Asks "where should I put this thing?".

```bash
curl -X POST http://127.0.0.1:8000/ai/suggest-placement \
  -H 'Content-Type: application/json' \
  -d '{"description": "claw hammer with rubber grip", "tags": ["metal", "tool"], "kind": "tool"}'
```

Cascade:
1. **`tier_used: heuristic`** — tag overlap + kind-affinity score over `can_contain` nodes. Returns top N directly if confidence ≥ 0.6.
2. **`tier_used: local`** — heuristic was weak; local LLM (Ollama) reranks the top candidates and returns picks with one-line reasons.
3. **`tier_used: anthropic`** — only if both gates above are on. Same prompt as tier 2 but against `AnthropicProvider`.
4. **`tier_used: heuristic_fallback`** — LLM failed or returned junk; return the heuristic ranking anyway.
5. **`tier_used: empty_db`** — no containers exist; nothing to suggest.

The same operation is exposed as the MCP tool `suggest_placement` for terminal use.

Install Ollama for the local path (one-time):

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b
```

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
```

[scripts/db_mysql.sh](scripts/db_mysql.sh) shells into the running `db` container via `docker compose exec`.

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
- DB session: [backend/app/database.py](backend/app/database.py) — reads `DATABASE_URL`, defaults to the docker-compose MySQL URL
- AI providers: [backend/app/ai/](backend/app/ai/) — `LLMProvider` interface + `LocalProvider` / `AnthropicProvider`
- Frontend pages: [frontend/src/pages/](frontend/src/pages/)
- Frontend components: [frontend/src/components/](frontend/src/components/)

## Gotchas

- **Two venvs exist** (`.venv/` and `venv/`). Only `.venv/` is active. Ignore `venv/`.
- **Vite port fallback**: if `:5173` is in use, Vite picks `:5174` (visible in [frontend.log](frontend.log)). Update the URL you open accordingly.
- **Frontend API base URL**: defaults to `http://127.0.0.1:8000`. Override with `VITE_API_URL` if the backend isn't on localhost:8000.
- **CORS**: the backend enables CORS for all origins in dev — see [backend/app/main.py](backend/app/main.py).
