# whereisit

> Inventory manager for personal tools and containers (drawers/boxes/shelves)

Quick start (backend only):

```bash
cd whereisit
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Endpoints:
- GET / -> basic health
- GET /health -> service healthwhereisit — inventory manager for tools in containers (drawers/boxes/shelves)
