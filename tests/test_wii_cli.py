"""Smoke tests for scripts/wii.

Loads the script as a module via importlib and runs each subcommand with an
ApiClient-compatible wrapper around the FastAPI TestClient. Marked
`committed_writes` because the `find` test path goes through MySQL FULLTEXT,
which only sees committed rows.
"""

import importlib.util
import json
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pytestmark = pytest.mark.committed_writes


_WII_PATH = Path(__file__).resolve().parent.parent / "scripts" / "wii"


def _load_wii():
    loader = SourceFileLoader("wii", str(_WII_PATH))
    spec = importlib.util.spec_from_loader("wii", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def wii():
    return _load_wii()


class _TestClientApi:
    """Adapter that exposes ApiClient.request over the FastAPI TestClient."""

    def __init__(self, test_client):
        self._tc = test_client

    def request(self, method, path, params=None, body=None):
        kwargs = {}
        if params:
            kwargs["params"] = {k: v for k, v in params.items() if v is not None}
        if body is not None:
            kwargs["json"] = body
        response = self._tc.request(method, path, **kwargs)
        try:
            payload = response.json() if response.content else None
        except json.JSONDecodeError:
            payload = response.text
        return response.status_code, payload


@pytest.fixture
def wii_client(client):
    return _TestClientApi(client)


def _run(wii, wii_client, *argv):
    wii.main(list(argv), client=wii_client)


def test_add_creates_node(wii, wii_client, capsys):
    _run(wii, wii_client, "add", "Claw hammer", "--kind", "tool")
    out = capsys.readouterr().out
    assert "Claw hammer" in out
    assert "tool" in out


def test_add_with_tag_and_find_locates_it(wii, wii_client, capsys):
    _run(wii, wii_client, "add", "Big hammer", "--kind", "tool", "--tag", "metal")
    capsys.readouterr()
    _run(wii, wii_client, "find", "hammer")
    out = capsys.readouterr().out
    assert "Big hammer" in out


def test_tree_renders_hierarchy(wii, wii_client, capsys):
    _run(wii, wii_client, "add", "Garage", "--kind", "room", "--container")
    out = capsys.readouterr().out
    garage_id = out.split()[0].lstrip("#")
    _run(
        wii, wii_client,
        "add", "Hammer", "--kind", "tool", "--parent", garage_id,
    )
    capsys.readouterr()
    _run(wii, wii_client, "tree")
    tree_out = capsys.readouterr().out
    assert "Garage" in tree_out
    assert "Hammer" in tree_out


def test_tag_add_then_rm(wii, wii_client, capsys):
    _run(wii, wii_client, "add", "Drill", "--kind", "tool", "--tag", "cordless")
    node_id = capsys.readouterr().out.split()[0].lstrip("#")
    # Confirm find-by-tag locates it
    _run(wii, wii_client, "--json", "find", "--tag", "cordless")
    assert any(r["id"] == int(node_id) for r in json.loads(capsys.readouterr().out))
    # Remove the tag, confirm find-by-tag no longer locates it
    _run(wii, wii_client, "tag", node_id, "rm", "cordless")
    capsys.readouterr()
    _run(wii, wii_client, "--json", "find", "--tag", "cordless")
    assert json.loads(capsys.readouterr().out) == []


def test_prop_set_list_rm(wii, wii_client, capsys):
    _run(wii, wii_client, "add", "Hammer", "--kind", "tool")
    node_id = capsys.readouterr().out.split()[0].lstrip("#")
    _run(
        wii, wii_client,
        "prop", node_id, "set", "weight_g", "600", "--type", "int",
    )
    capsys.readouterr()
    _run(wii, wii_client, "--json", "prop", node_id, "list")
    props = json.loads(capsys.readouterr().out)
    assert props == [{"key": "weight_g", "value": "600", "value_type": "int"}]
    _run(wii, wii_client, "prop", node_id, "rm", "weight_g")
    capsys.readouterr()
    _run(wii, wii_client, "--json", "prop", node_id, "list")
    assert json.loads(capsys.readouterr().out) == []


def test_rm_with_cascade(wii, wii_client, capsys):
    _run(wii, wii_client, "add", "Garage", "--kind", "room", "--container")
    gid = capsys.readouterr().out.split()[0].lstrip("#")
    _run(wii, wii_client, "add", "Hammer", "--kind", "tool", "--parent", gid)
    capsys.readouterr()
    # rm without cascade should fail because the room has a child
    with pytest.raises(SystemExit):
        _run(wii, wii_client, "rm", gid)
    capsys.readouterr()
    _run(wii, wii_client, "rm", gid, "--cascade")
    out = capsys.readouterr().out
    assert "deleted" in out
    _run(wii, wii_client, "tree")
    assert capsys.readouterr().out.strip() == "(no nodes)"


def test_json_flag_emits_valid_json(wii, wii_client, capsys):
    _run(
        wii, wii_client,
        "--json", "add", "Item", "--kind", "item",
    )
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["name"] == "Item"
    assert parsed["kind"]["slug"] == "item"
