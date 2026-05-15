# PLAN.md — whereisit roadmap

## Vision

`whereisit` is a robust, fast storage service for everything in a home. Anything that holds things — garages, rooms, cupboards, shelves, drawers, toolboxes — and anything that lives inside them — hammers, screws, batteries — is the same kind of thing: a **node** in a tree. The system stores what you have and where it is, and an AI layer answers questions like _"where can I find a hammer?"_ and _"where should I put this new hammer?"_

Backend, scripts, and an MCP server come first so the assistant can manage the inventory directly from the terminal. The web UI is a later milestone.

## Design principles

- **Tree of nodes** — items and storage are the same concept, separated only by a `can_contain` flag and a `kind`.
- **Reference tables** for things that repeat (`kinds`, `tags`, `property_keys`); a key-value table (`node_properties`) for free-form attributes — no JSON blobs.
- **Backend + scripts + MCP first**, web UI second.
- **Provider-agnostic LLM layer** — one interface, swappable implementations.
- **APIs designed for the end state** — each milestone builds toward the target shape, not a stepping-stone we'll rewrite.
- **Embeddings prepared for, not built yet** — schema choices today (TEXT description, `updated_at`, `mode` query param on search) make a vector layer a future additive change, not a breaking one.

## Decisions (locked in, 2026-05-15)

1. **Unify items + containers into a single `nodes` table** with `kind_id` (FK to a reference table) + `can_contain` flag. Each node still has a free-text `name` (e.g. kind=drawer, name="blue drawer under the sink").
2. **Reference tables everywhere it pays off** — `kinds`, `tags`, `property_keys`. Properties are a key-value table, not a JSON blob.
3. **Quantity defaults to 1.** For multi-location tracking (5 hammers across two rooms), create one row per physical instance — 3 hammer rows parented to the garage, 2 to the basement. For container-as-item cases (a box of 100 nails), quantity stores the contents count. The schema doesn't enforce a semantic; the user decides per row. Aggregation answers "do I have a hammer?" by grouping result rows.
4. **Provider-agnostic LLM abstraction with local-first cascade and two-gate cloud.** `LLMProvider` interface supports multiple providers (local Ollama by default, Anthropic cloud opt-in). AI features tier through DB → local LLM → cloud. Cloud calls require **both** a server-side kill switch (`WHEREISIT_CLOUD_ENABLED`, default `false`) and a per-call `confirm_remote=true` flag — neither alone is sufficient. Keeps the marginal cost of `/ai/*` at zero unless the operator both flips the switch and the caller explicitly opts in. No hardcoded SDK calls leak into business logic.
5. **MCP server as the primary AI surface.** Exposes inventory tools so Claude Code can manage everything from the terminal. A REST `/ai/ask` endpoint comes later for the web UI.
6. **Drop the `views` table.** Doesn't fit the cleaner hierarchy.
7. **Wipe existing data.** Current items/containers are throwaway brainstorm — the new schema lands as a fresh CREATE.
8. **Embeddings are deferred but prepared for.** TEXT description column, `updated_at` on nodes, search endpoint with a `mode` param.
9. **Simple token auth lands early.** Single static token in `WHEREISIT_TOKEN`, checked via `Authorization: Bearer` middleware. Easy to swap for JWT/OAuth later.

## Target schema (sketch)

```
kinds            id, slug UNIQUE, label
nodes            id, name, kind_id FK, parent_id FK (self, nullable),
                 can_contain BOOL, description TEXT, quantity INT DEFAULT 1,
                 width, height, depth, weight (FLOAT, nullable),
                 gps_lat, gps_lng (FLOAT, nullable),
                 created_at, updated_at
                 (FULLTEXT index on name + description)
tags             id, name UNIQUE
node_tags        node_id FK, tag_id FK   (composite PK)
property_keys    id, key UNIQUE, value_type ENUM('string','int','float','bool')
node_properties  id, node_id FK, key_id FK, value TEXT
embeddings       id, node_id FK, model, vector, embedded_at    -- added in M11
```

## Target API (sketch)

REST surface designed for the end state. Milestones build toward this shape rather than evolving it ad-hoc.

```
Nodes
  GET    /nodes                       filters: parent, kind, tag, q; paginated
  POST   /nodes
  GET    /nodes/{id}                  node + tags + properties
  PATCH  /nodes/{id}                  partial update (reparent via parent_id)
  DELETE /nodes/{id}                  ?cascade=true to delete subtree
  GET    /nodes/{id}/children         paginated
  GET    /nodes/{id}/path             ancestor chain
  GET    /nodes/{id}/tree?depth=N     subtree

Reference tables
  GET/POST    /tags                   idempotent create
  GET/POST    /kinds                  idempotent create
  POST/DELETE /nodes/{id}/tags        add by name (creates tag if missing) / remove

Properties
  GET    /nodes/{id}/properties
  PUT    /nodes/{id}/properties/{key} upsert; creates property_key if missing
  DELETE /nodes/{id}/properties/{key}

Search
  GET    /search                      ?q=&parent=&kind=&tag=&mode=keyword|semantic|hybrid

AI
  POST   /ai/suggest-placement        body: {description, dimensions?, tags?}
  POST   /ai/ask                      body: {question}
```

**Auth:** every endpoint except `/health` requires `Authorization: Bearer $WHEREISIT_TOKEN` when the env var is set. When unset, dev mode is open.

## Milestones

Each milestone lands a working slice of the end-state design. The git workflow (branch off `master`, PR per milestone) is documented in [AGENTS.md](AGENTS.md).

- [x] **M0 — Pytest harness.** Add `pytest` to `requirements.txt`, set up a `tests/` dir with a fixture that boots the FastAPI app against the docker-compose MySQL. One smoke test (`/health` → 200).
  - *Considerations:* drop the stale `venv/` while we're in here; keep test DB isolation in mind (separate DB name, or `TRUNCATE` between tests).

- [x] **M1 — Token auth middleware.** Reads `WHEREISIT_TOKEN`; if set, every endpoint except `/health` requires `Authorization: Bearer <token>`. If unset, dev mode (open).
  - *Considerations:* single FastAPI dependency so swapping for JWT/OAuth later is a one-file change; document the env var in AGENTS.md.

- [x] **M2 — Schema reset to the unified model.** Drop every existing migration and table; introduce a fresh initial migration that creates `kinds`, `nodes`, `tags`, `node_tags`, `property_keys`, `node_properties`. Seed `kinds` with `room`, `building`, `cupboard`, `shelf`, `drawer`, `box`, `bag`, `item`, `tool`, `consumable`. FULLTEXT index on `nodes(name, description)`.
  - *Considerations:* `description` is TEXT (not VARCHAR) so embedding context isn't truncated; `updated_at` is what the embedding job will use to find stale rows; `quantity` semantics are user-interpreted (Decision #3).

- [x] **M3 — Core `/nodes` API (end-state shape).** Replace every existing router. CRUD + `/children`, `/path`, `/tree`. PATCH not PUT.
  - *Considerations:* never auto-expand children in the default node response (keep it lean); document responses in OpenAPI from day one.

- [x] **M4 — Tags, kinds, properties APIs.** Endpoints for the reference + join layers; create is idempotent by name/slug.
  - *Considerations:* property value validation happens in the app layer based on `property_keys.value_type`.

- [x] **M5 — Search.** `GET /search?q=&parent=&kind=&tag=&mode=keyword`. MySQL FULLTEXT over `name + description`. Each result carries `score`, `match_reason`, `path` (ancestors).
  - *Considerations:* response shape supports future `mode=semantic|hybrid` without changes. Compute ancestor path on the fly first; materialize a `path` column only if it gets slow.

- [x] **M6 — `scripts/wii` CLI.** Python single-file CLI wrapping the API. Commands: `add`, `find`, `tree`, `move`, `tag`, `prop`, `rm`. Reads `WHEREISIT_TOKEN`, `WHEREISIT_API_URL` (default `http://127.0.0.1:8000`).
  - *Considerations:* every command supports `--json` for agents; default is pretty for humans; mirror MCP tool names so muscle-memory transfers.

- [x] **M7 — MCP server.** Python MCP server exposing inventory tools (same operations as the CLI). Talks to the backend with the same token. Documented Claude Code config snippet.
  - *Considerations:* no LLM here — the MCP server is a thin adapter; write tool docstrings carefully so Claude can call them without further prompting.

- [x] **M8 — `LLMProvider` abstraction.** Interface in `backend/app/ai/provider.py` with `generate(messages)` and `tool_use_loop(messages, tools, on_tool_call)`. Two concrete providers: `LocalProvider` (Ollama HTTP, default) and `AnthropicProvider`. Selected via `LLM_PROVIDER=local|anthropic` (default `local`); local URL via `LLM_LOCAL_URL` (default `http://127.0.0.1:11434`), local model via `LLM_LOCAL_MODEL` (default `llama3.1:8b`); Anthropic via `ANTHROPIC_API_KEY` and `ANTHROPIC_MODEL` (default `claude-haiku-4-5`).
  - *Considerations:* no LLM calls outside `backend/app/ai/`; tests mock both providers (no live API calls in CI). M9/M10 build the cascade orchestration on top — M8 is plumbing only.

- [x] **M9 — Placement suggestion.** `POST /ai/suggest-placement` + MCP tool `suggest_placement`. Input: `{description, tags?, kind?, confirm_remote?: bool, max_suggestions?: int}`. Cascade: (1) tag-overlap + kind-affinity heuristic over `can_contain` nodes; if best score ≥ confidence threshold, return top N immediately. (2) Otherwise, local LLM reranks the top-K heuristic candidates and returns a structured pick list with one-line reasons. (3) `confirm_remote=true` + `WHEREISIT_CLOUD_ENABLED=true` routes the same prompt to `AnthropicProvider`; `confirm_remote=true` with kill switch off returns 400 `cloud_disabled`.
  - *Considerations:* cold-start (empty DB) returns `tier_used: "empty_db"`; cap suggestions at 5 by default; log every cascade decision; per Decision #4, dimensions are deferred until real data has them; the local LLM must return strict JSON or the cascade falls back to tier 1.

- [x] **M10 — Natural-language Q&A and action.** `POST /ai/ask` + MCP tool `ask`. Cascade: (1) literal-match search — strip stopwords from the question and run MySQL FULLTEXT; if matches found, format them as the answer with no LLM call. (2) Local LLM tool-use loop over the inventory tools (read + write — `search`, `get_node`, `get_children`, `get_path`, `list_root_nodes`, `list_kinds`, `list_tags`, `add_node`, `update_node`, `move_node`, `delete_node`, `add_tag`, `remove_tag`, `set_property`). (3) Escalate to Anthropic cloud only when both `WHEREISIT_CLOUD_ENABLED=true` and request `confirm_remote=true` (same two-gate rule as M9). Every tool call is captured in the response trace so the user sees what the assistant did.
  - *Considerations:* prompt-cache the system prompt + tool defs (Anthropic provider only — local model gets no benefit); bound loop iterations (~8); structured logging of every tool call for debugging; tier 1 result format is "Found N: <path>, <path>..." so it composes with aggregation later; write-tool failures (e.g. invalid `move_node`) surface as `is_error` tool results so the LLM can recover or apologise.

- [x] **M11 — Embeddings.** `embeddings` table + a backfill job that finds nodes where `updated_at > embedded_at`. Search gains `mode=semantic|hybrid`. `LLMProvider` extended with `embed(texts)`; `LocalProvider` calls Ollama `/api/embed` (default `nomic-embed-text`, overridable via `LLM_EMBED_MODEL`); `AnthropicProvider.embed()` raises `LLMError`. Backfill exposed as `scripts/wii_embed` CLI + `POST /embeddings/backfill` endpoint. Hybrid mode fuses keyword + semantic via Reciprocal Rank Fusion (no weight tuning needed).
  - *Considerations:* vectors are JSON-serialized in a TEXT column, cosine computed in Python — fine for thousands of nodes; upgrade to pgvector / sqlite-vss / Qdrant when scale demands; semantic search hard-uses the local provider since Anthropic has no embeddings API.

- [ ] **M12 — Web UI rebuild.** Throw out the current React components; build a minimal new UI: tree view of nodes, search bar wired to `/search`, quick-add modal, "ask" panel calling `/ai/ask`. Drag-drop reparenting if it's cheap.
  - *Considerations:* this is where the frontend earns its keep; before this milestone, curl + the CLI is enough.

## Open questions

Captured here so they're not forgotten; not blocking any milestone.

- **Canonical `node_type` reference.** Should "claw hammer" and "ball-peen hammer" both resolve to a type "hammer" for aggregation, or is name + tags + LLM understanding enough? Revisit after M10.
- **Multi-instance ergonomics.** When adding 5 of the same hammer, should the CLI/MCP have a "copy this node N times into these N parents" helper, or always one-by-one? Decide from real usage.
- **Vector storage backend.** Start in-process. Upgrade threshold (~1000 nodes?) and target (pgvector vs sqlite-vss vs Qdrant)?
- **Auth upgrade path.** When does the single-token model stop being enough? Probably never for a personal home tool, but document the hand-off seam in M1.
