"""Smoke tests for scripts/wii_mcp.

Loads the MCP server module, injects an httpx.Client that talks to the
FastAPI app in-process (via ASGI transport), and calls each tool as a plain
Python function — FastMCP's `@mcp.tool()` decorator keeps the originals
callable. Marked `committed_writes` so the FULLTEXT search path sees rows.
"""

import importlib.util
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pytestmark = pytest.mark.committed_writes


_MCP_PATH = Path(__file__).resolve().parent.parent / "scripts" / "wii_mcp"


def _load_mcp_module():
    loader = SourceFileLoader("wii_mcp", str(_MCP_PATH))
    spec = importlib.util.spec_from_loader("wii_mcp", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def mcp_module():
    return _load_mcp_module()


@pytest.fixture
def mcp(mcp_module, client):
    """`client` is the session-scoped FastAPI TestClient, which subclasses
    httpx.Client and handles the ASGI sync/async bridge internally."""
    mcp_module._set_client_for_tests(client)
    yield mcp_module
    mcp_module._set_client_for_tests(None)  # type: ignore[arg-type]


def test_add_then_get(mcp):
    node = mcp.add_node(name="Claw hammer", kind="tool")
    assert node["name"] == "Claw hammer"
    assert node["kind"]["slug"] == "tool"
    fetched = mcp.get_node(node["id"])
    assert fetched["id"] == node["id"]
    assert fetched["tags"] == []
    assert fetched["properties"] == []


def test_find_nodes_locates_by_keyword(mcp):
    mcp.add_node(name="Claw hammer", kind="tool")
    mcp.add_node(name="Screwdriver", kind="tool")
    results = mcp.find_nodes(q="hammer")
    assert len(results) == 1
    assert results[0]["name"] == "Claw hammer"
    assert results[0]["score"] > 0
    assert results[0]["path"][-1]["name"] == "Claw hammer"


def test_tree_after_nested_adds(mcp):
    garage = mcp.add_node(name="Garage", kind="room", can_contain=True)
    cupboard = mcp.add_node(
        name="Tool cupboard", kind="cupboard", parent_id=garage["id"], can_contain=True
    )
    mcp.add_node(name="Drill", kind="tool", parent_id=cupboard["id"])
    tree = mcp.get_tree(garage["id"])
    assert tree["name"] == "Garage"
    assert tree["children"][0]["name"] == "Tool cupboard"
    assert tree["children"][0]["children"][0]["name"] == "Drill"


def test_tag_round_trip(mcp):
    node = mcp.add_node(name="Hammer", kind="tool")
    tag = mcp.add_tag(node["id"], "metal")
    assert tag["name"] == "metal"
    detail = mcp.get_node(node["id"])
    assert any(t["name"] == "metal" for t in detail["tags"])
    mcp.remove_tag(node["id"], "metal")
    detail = mcp.get_node(node["id"])
    assert detail["tags"] == []


def test_property_round_trip(mcp):
    node = mcp.add_node(name="Hammer", kind="tool")
    mcp.set_property(node["id"], "weight_g", "600", value_type="int")
    props = mcp.list_properties(node["id"])
    assert props == [{"key": "weight_g", "value": "600", "value_type": "int"}]
    mcp.delete_property(node["id"], "weight_g")
    assert mcp.list_properties(node["id"]) == []


def test_move_and_cascade_delete(mcp):
    garage = mcp.add_node(name="Garage", kind="room", can_contain=True)
    workshop = mcp.add_node(name="Workshop", kind="room", can_contain=True)
    hammer = mcp.add_node(name="Hammer", kind="tool", parent_id=garage["id"])
    mcp.move_node(hammer["id"], workshop["id"])
    assert mcp.get_node(hammer["id"])["parent_id"] == workshop["id"]
    msg = mcp.delete_node(workshop["id"], cascade=True)
    assert "cascade" in msg
    # Both gone
    with pytest.raises(RuntimeError):
        mcp.get_node(workshop["id"])
    with pytest.raises(RuntimeError):
        mcp.get_node(hammer["id"])


def test_list_kinds_includes_seeds(mcp):
    kinds = mcp.list_kinds()
    slugs = {k["slug"] for k in kinds}
    assert {"room", "tool", "drawer", "item"}.issubset(slugs)
