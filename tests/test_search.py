import pytest

# MySQL InnoDB FULLTEXT only sees committed rows. The conftest fixture sees
# this marker and TRUNCATEs between tests instead of using transaction rollback.
pytestmark = pytest.mark.committed_writes


def _make(client, name, kind="item", description=None, parent_id=None, can_contain=False):
    body = {"name": name, "kind": kind, "can_contain": can_contain}
    if description is not None:
        body["description"] = description
    if parent_id is not None:
        body["parent_id"] = parent_id
    response = client.post("/nodes", json=body)
    assert response.status_code == 201, response.text
    return response.json()


# ---------- keyword search ----------


def test_keyword_finds_by_name(client):
    _make(client, "Claw hammer", kind="tool")
    _make(client, "Screwdriver", kind="tool")
    response = client.get("/search", params={"q": "hammer"})
    assert response.status_code == 200
    names = [r["name"] for r in response.json()]
    assert names == ["Claw hammer"]


def test_keyword_prefix_wildcard(client):
    _make(client, "Hammerhead", kind="tool")
    _make(client, "Drill", kind="tool")
    response = client.get("/search", params={"q": "hamm"})
    names = [r["name"] for r in response.json()]
    assert names == ["Hammerhead"]


def test_keyword_finds_by_description(client):
    _make(
        client,
        "Mystery box",
        kind="box",
        can_contain=True,
        description="Contains assorted brass fittings and copper pipes.",
    )
    _make(client, "Empty box", kind="box", can_contain=True)
    response = client.get("/search", params={"q": "brass"})
    names = [r["name"] for r in response.json()]
    assert names == ["Mystery box"]


def test_keyword_requires_all_words(client):
    _make(client, "Claw hammer", kind="tool")
    _make(client, "Big hammer", kind="tool")
    response = client.get("/search", params={"q": "claw hammer"})
    names = [r["name"] for r in response.json()]
    assert names == ["Claw hammer"]


def test_keyword_no_match_returns_empty(client):
    _make(client, "Claw hammer", kind="tool")
    response = client.get("/search", params={"q": "xyznothingmatches"})
    assert response.status_code == 200
    assert response.json() == []


def test_score_populated_when_keyword(client):
    _make(client, "Claw hammer", kind="tool")
    response = client.get("/search", params={"q": "hammer"})
    body = response.json()
    assert len(body) == 1
    assert isinstance(body[0]["score"], float)
    assert body[0]["score"] > 0
    assert body[0]["match_reason"] == "fulltext name+description match"


def test_score_null_when_no_query(client):
    _make(client, "Anything", kind="item")
    response = client.get("/search")
    body = response.json()
    assert len(body) == 1
    assert body[0]["score"] is None
    assert body[0]["match_reason"] is None


def test_special_chars_in_query_are_stripped(client):
    _make(client, "Hammer", kind="tool")
    response = client.get("/search", params={"q": "+hammer*"})
    # Operators get stripped, then re-applied internally — should still find it
    assert response.status_code == 200
    assert [r["name"] for r in response.json()] == ["Hammer"]


def test_empty_query_after_stripping_returns_empty(client):
    _make(client, "Hammer", kind="tool")
    response = client.get("/search", params={"q": "+++"})
    assert response.status_code == 200
    assert response.json() == []


# ---------- no-q listing (filters only) ----------


def test_no_q_returns_all(client):
    _make(client, "A")
    _make(client, "B")
    response = client.get("/search")
    assert len(response.json()) == 2


def test_filter_by_kind(client):
    _make(client, "Hammer", kind="tool")
    _make(client, "Screwdriver", kind="tool")
    _make(client, "Nails box", kind="consumable")
    response = client.get("/search", params={"kind": "tool"})
    assert {r["name"] for r in response.json()} == {"Hammer", "Screwdriver"}


def test_filter_by_parent_subtree(client):
    garage = _make(client, "Garage", kind="room", can_contain=True)
    _make(client, "Hammer", kind="tool", parent_id=garage["id"])
    _make(client, "Wrench", kind="tool", parent_id=garage["id"])
    _make(client, "Toaster", kind="item")  # different root
    response = client.get("/search", params={"parent": str(garage["id"])})
    assert {r["name"] for r in response.json()} == {"Hammer", "Wrench"}


def test_filter_parent_root(client):
    _make(client, "TopLevel")
    parent = _make(client, "Container", kind="cupboard", can_contain=True)
    _make(client, "Inside", kind="item", parent_id=parent["id"])
    response = client.get("/search", params={"parent": "root"})
    names = {r["name"] for r in response.json()}
    assert "TopLevel" in names and "Container" in names
    assert "Inside" not in names


def test_filter_by_tag(client):
    a = _make(client, "Hammer 1", kind="tool")
    b = _make(client, "Hammer 2", kind="tool")
    _make(client, "Saw", kind="tool")
    client.post(f"/nodes/{a['id']}/tags", json={"name": "metal"})
    client.post(f"/nodes/{b['id']}/tags", json={"name": "metal"})
    response = client.get("/search", params={"tag": "metal"})
    assert {r["name"] for r in response.json()} == {"Hammer 1", "Hammer 2"}


def test_combined_q_and_kind(client):
    _make(client, "Claw hammer", kind="tool")
    _make(client, "Hammer drill", kind="consumable")
    response = client.get(
        "/search", params={"q": "hammer", "kind": "tool"}
    )
    assert [r["name"] for r in response.json()] == ["Claw hammer"]


# ---------- path enrichment ----------


def test_path_includes_ancestors(client):
    a = _make(client, "Garage", kind="room", can_contain=True)
    b = _make(client, "Cupboard", kind="cupboard", parent_id=a["id"], can_contain=True)
    c = _make(client, "Drawer", kind="drawer", parent_id=b["id"], can_contain=True)
    _make(client, "Claw hammer", kind="tool", parent_id=c["id"])
    response = client.get("/search", params={"q": "hammer"})
    assert response.status_code == 200
    result = response.json()[0]
    path_names = [n["name"] for n in result["path"]]
    assert path_names == ["Garage", "Cupboard", "Drawer", "Claw hammer"]


def test_path_for_root_is_just_self(client):
    _make(client, "Hammer", kind="tool")
    response = client.get("/search", params={"q": "hammer"})
    result = response.json()[0]
    assert [n["name"] for n in result["path"]] == ["Hammer"]


# ---------- pagination ----------


def test_pagination(client):
    for i in range(5):
        _make(client, f"Hammer {i}", kind="tool")
    page1 = client.get("/search", params={"q": "hammer", "limit": 2, "offset": 0}).json()
    page2 = client.get("/search", params={"q": "hammer", "limit": 2, "offset": 2}).json()
    assert len(page1) == 2 and len(page2) == 2
    assert {r["id"] for r in page1}.isdisjoint({r["id"] for r in page2})


# ---------- mode validation ----------


def test_unknown_mode_rejected(client):
    response = client.get("/search", params={"mode": "semantic"})
    assert response.status_code == 400
    assert "mode" in response.text


def test_keyword_mode_explicit(client):
    _make(client, "Hammer", kind="tool")
    response = client.get(
        "/search", params={"q": "hammer", "mode": "keyword"}
    )
    assert response.status_code == 200
    assert len(response.json()) == 1


# ---------- limit bounds ----------


def test_limit_max_enforced(client):
    response = client.get("/search", params={"limit": 500})
    assert response.status_code == 422


def test_limit_min_enforced(client):
    response = client.get("/search", params={"limit": 0})
    assert response.status_code == 422
