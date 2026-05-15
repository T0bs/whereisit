"""Tool definitions and dispatcher for the /ai/ask cascade.

The LLM sees these tools (by name + JSON Schema), decides to call them, and
this module executes them against the DB by reusing the existing route
handler functions — keeps the behaviour identical to the REST API.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Tag
from ..routers import kinds as kinds_router
from ..routers import nodes as nodes_router
from ..routers import search as search_router
from ..routers import tags as tags_router
from ..schemas import NodeCreate, NodeUpdate, PropertyValueSet, TagCreate
from .provider import Tool


@dataclass
class ToolCallTrace:
    tool: str
    input: dict
    output: str
    is_error: bool = False


# ---------------------------------------------------------------------------
# tool schemas — exposed to the LLM
# ---------------------------------------------------------------------------


def build_inventory_tools() -> list[Tool]:
    return [
        Tool(
            name="search",
            description=(
                "Find nodes by keyword (FULLTEXT over name + description), optionally "
                "filtered by kind slug, tag name, or subtree. Start here for "
                "'where is my X?' / 'do I have any Y?' questions."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "Free-text query."},
                    "kind": {"type": "string", "description": "Kind slug filter."},
                    "tag": {"type": "string", "description": "Tag name filter."},
                    "parent": {
                        "type": "string",
                        "description": "'root' or an integer node id (as string) to confine to a subtree.",
                    },
                    "limit": {"type": "integer", "default": 20},
                },
            },
        ),
        Tool(
            name="get_node",
            description="Fetch one node with full details, tags, and properties.",
            input_schema={
                "type": "object",
                "properties": {"node_id": {"type": "integer"}},
                "required": ["node_id"],
            },
        ),
        Tool(
            name="get_children",
            description="List direct children of a node.",
            input_schema={
                "type": "object",
                "properties": {
                    "node_id": {"type": "integer"},
                    "limit": {"type": "integer", "default": 50},
                },
                "required": ["node_id"],
            },
        ),
        Tool(
            name="get_path",
            description="Return the full ancestor chain root→self for a node.",
            input_schema={
                "type": "object",
                "properties": {"node_id": {"type": "integer"}},
                "required": ["node_id"],
            },
        ),
        Tool(
            name="list_root_nodes",
            description="List top-level nodes (the buildings, rooms, garages with no parent).",
            input_schema={
                "type": "object",
                "properties": {"limit": {"type": "integer", "default": 50}},
            },
        ),
        Tool(
            name="list_kinds",
            description="List the available kinds (e.g. room, drawer, tool, consumable).",
            input_schema={"type": "object", "properties": {}},
        ),
        Tool(
            name="list_tags",
            description="List all tags in the inventory.",
            input_schema={"type": "object", "properties": {}},
        ),
        Tool(
            name="add_node",
            description=(
                "Create a new node. Use can_contain=true for storage (drawer, "
                "cupboard, room) and false for leaf items. Parent must accept children."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "kind": {"type": "string", "description": "Kind slug."},
                    "parent_id": {"type": "integer"},
                    "can_contain": {"type": "boolean", "default": False},
                    "description": {"type": "string"},
                    "quantity": {"type": "integer", "default": 1},
                },
                "required": ["name", "kind"],
            },
        ),
        Tool(
            name="update_node",
            description=(
                "Patch a node's fields. Pass only the fields you want changed. "
                "Use parent_id=null to move to root. CONFIRM with the user before "
                "renaming or reparenting items they didn't explicitly ask about."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "node_id": {"type": "integer"},
                    "name": {"type": "string"},
                    "kind": {"type": "string"},
                    "parent_id": {"type": ["integer", "null"]},
                    "description": {"type": "string"},
                    "quantity": {"type": "integer"},
                },
                "required": ["node_id"],
            },
        ),
        Tool(
            name="move_node",
            description=(
                "Reparent a node. Pass parent_id=null to promote to root. The new "
                "parent must accept children and the move must not create a cycle."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "node_id": {"type": "integer"},
                    "parent_id": {"type": ["integer", "null"]},
                },
                "required": ["node_id"],
            },
        ),
        Tool(
            name="delete_node",
            description=(
                "Delete a node. Set cascade=true to delete the whole subtree. "
                "DESTRUCTIVE — get explicit user confirmation before calling."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "node_id": {"type": "integer"},
                    "cascade": {"type": "boolean", "default": False},
                },
                "required": ["node_id"],
            },
        ),
        Tool(
            name="add_tag",
            description="Attach a tag to a node by name. Creates the tag if it doesn't exist.",
            input_schema={
                "type": "object",
                "properties": {
                    "node_id": {"type": "integer"},
                    "name": {"type": "string"},
                },
                "required": ["node_id", "name"],
            },
        ),
        Tool(
            name="remove_tag",
            description="Remove a tag from a node by name.",
            input_schema={
                "type": "object",
                "properties": {
                    "node_id": {"type": "integer"},
                    "name": {"type": "string"},
                },
                "required": ["node_id", "name"],
            },
        ),
        Tool(
            name="set_property",
            description=(
                "Set a typed property on a node. value_type is consulted only when "
                "the property key is created for the first time (then sticky)."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "node_id": {"type": "integer"},
                    "key": {"type": "string"},
                    "value": {"description": "string|int|float|bool"},
                    "value_type": {
                        "type": "string",
                        "enum": ["string", "int", "float", "bool"],
                    },
                },
                "required": ["node_id", "key", "value"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------


def execute_tool(db: Session, name: str, args: dict[str, Any]) -> tuple[str, bool]:
    """Run one tool call. Returns (output_json_string, is_error)."""
    handler = _DISPATCH.get(name)
    if handler is None:
        return json.dumps({"error": f"unknown tool: {name}"}), True

    try:
        result = handler(db, args)
    except HTTPException as exc:
        return json.dumps({"error": str(exc.detail), "status_code": exc.status_code}), True
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"}), True

    return _serialize(result), False


def _serialize(value: Any) -> str:
    if hasattr(value, "model_dump"):
        return json.dumps(value.model_dump(mode="json"), default=str)
    if isinstance(value, list):
        return json.dumps(
            [v.model_dump(mode="json") if hasattr(v, "model_dump") else v for v in value],
            default=str,
        )
    return json.dumps(value, default=str)


def _do_search(db: Session, args: dict) -> Any:
    return search_router.search(
        q=args.get("q"),
        parent=args.get("parent"),
        kind=args.get("kind"),
        tag=args.get("tag"),
        mode="keyword",
        limit=int(args.get("limit", 20)),
        offset=0,
        db=db,
    )


def _do_get_node(db: Session, args: dict) -> Any:
    return nodes_router.get_node(node_id=int(args["node_id"]), db=db)


def _do_get_children(db: Session, args: dict) -> Any:
    return nodes_router.list_children(
        node_id=int(args["node_id"]),
        limit=int(args.get("limit", 50)),
        offset=0,
        db=db,
    )


def _do_get_path(db: Session, args: dict) -> Any:
    return nodes_router.get_path(node_id=int(args["node_id"]), db=db)


def _do_list_root_nodes(db: Session, args: dict) -> Any:
    return nodes_router.list_nodes(
        parent="root",
        kind=None,
        tag=None,
        q=None,
        limit=int(args.get("limit", 50)),
        offset=0,
        db=db,
    )


def _do_list_kinds(db: Session, args: dict) -> Any:
    return kinds_router.list_kinds(q=None, limit=200, offset=0, db=db)


def _do_list_tags(db: Session, args: dict) -> Any:
    return tags_router.list_tags(q=None, limit=200, offset=0, db=db)


def _do_add_node(db: Session, args: dict) -> Any:
    body = NodeCreate(
        name=args["name"],
        kind=args["kind"],
        parent_id=args.get("parent_id"),
        can_contain=bool(args.get("can_contain", False)),
        description=args.get("description"),
        quantity=int(args.get("quantity", 1)),
    )
    return nodes_router.create_node(body=body, db=db)


def _do_update_node(db: Session, args: dict) -> Any:
    payload = {k: v for k, v in args.items() if k != "node_id"}
    body = NodeUpdate(**payload)
    return nodes_router.update_node(node_id=int(args["node_id"]), body=body, db=db)


def _do_move_node(db: Session, args: dict) -> Any:
    body = NodeUpdate(parent_id=args.get("parent_id"))
    return nodes_router.update_node(node_id=int(args["node_id"]), body=body, db=db)


def _do_delete_node(db: Session, args: dict) -> Any:
    nodes_router.delete_node(
        node_id=int(args["node_id"]),
        cascade=bool(args.get("cascade", False)),
        db=db,
    )
    return {"deleted": int(args["node_id"]), "cascade": bool(args.get("cascade", False))}


def _do_add_tag(db: Session, args: dict) -> Any:
    body = TagCreate(name=args["name"])
    response = Response()
    return nodes_router.add_tag_to_node(
        node_id=int(args["node_id"]), body=body, response=response, db=db
    )


def _do_remove_tag(db: Session, args: dict) -> Any:
    tag = db.execute(select(Tag).where(Tag.name == args["name"])).scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=404, detail=f"tag {args['name']!r} does not exist")
    nodes_router.remove_tag_from_node(
        node_id=int(args["node_id"]), tag_id=tag.id, db=db
    )
    return {"removed": args["name"], "node_id": int(args["node_id"])}


def _do_set_property(db: Session, args: dict) -> Any:
    body = PropertyValueSet(value=args["value"], value_type=args.get("value_type"))
    response = Response()
    return nodes_router.set_node_property(
        node_id=int(args["node_id"]),
        key=str(args["key"]),
        body=body,
        response=response,
        db=db,
    )


_DISPATCH: dict[str, Callable[[Session, dict], Any]] = {
    "search": _do_search,
    "get_node": _do_get_node,
    "get_children": _do_get_children,
    "get_path": _do_get_path,
    "list_root_nodes": _do_list_root_nodes,
    "list_kinds": _do_list_kinds,
    "list_tags": _do_list_tags,
    "add_node": _do_add_node,
    "update_node": _do_update_node,
    "move_node": _do_move_node,
    "delete_node": _do_delete_node,
    "add_tag": _do_add_tag,
    "remove_tag": _do_remove_tag,
    "set_property": _do_set_property,
}
