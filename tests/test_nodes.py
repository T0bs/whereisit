import pytest


# ---------- helpers ----------


def _create(client, **kwargs):
    body = {"name": "x", "kind": "item"}
    body.update(kwargs)
    response = client.post("/nodes", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def _create_root_container(client, name="Garage", kind="room"):
    return _create(client, name=name, kind=kind, can_contain=True)


# ---------- create ----------


def test_create_root_node(client):
    body = _create_root_container(client, name="Garage", kind="room")
    assert body["id"] > 0
    assert body["name"] == "Garage"
    assert body["kind"]["slug"] == "room"
    assert body["kind"]["label"] == "Room"
    assert body["parent_id"] is None
    assert body["can_contain"] is True
    assert body["quantity"] == 1
    assert body["tags"] == []
    assert body["properties"] == []


def test_create_child_node(client):
    parent = _create_root_container(client)
    child = _create(client, name="Hammer", kind="tool", parent_id=parent["id"])
    assert child["parent_id"] == parent["id"]
    assert child["kind"]["slug"] == "tool"


def test_create_child_into_leaf_rejected(client):
    leaf = _create(client, name="Hammer", kind="tool", can_contain=False)
    response = client.post(
        "/nodes",
        json={"name": "weird", "kind": "item", "parent_id": leaf["id"]},
    )
    assert response.status_code == 400
    assert "can_contain" in response.text or "does not accept" in response.text


def test_create_with_unknown_kind(client):
    response = client.post("/nodes", json={"name": "x", "kind": "nope"})
    assert response.status_code == 404
    assert "unknown kind" in response.text.lower()


def test_create_with_missing_parent(client):
    response = client.post(
        "/nodes", json={"name": "x", "kind": "item", "parent_id": 99999}
    )
    assert response.status_code == 404


def test_create_blank_name_rejected(client):
    response = client.post("/nodes", json={"name": "", "kind": "item"})
    assert response.status_code == 422


# ---------- list / filter ----------


def test_list_returns_all(client):
    a = _create(client, name="A")
    b = _create(client, name="B")
    response = client.get("/nodes")
    assert response.status_code == 200
    ids = [n["id"] for n in response.json()]
    assert a["id"] in ids and b["id"] in ids


def test_list_filter_parent_root(client):
    root1 = _create_root_container(client, name="Garage")
    root2 = _create_root_container(client, name="House")
    _create(client, name="Hammer", kind="tool", parent_id=root1["id"])
    response = client.get("/nodes", params={"parent": "root"})
    assert response.status_code == 200
    ids = {n["id"] for n in response.json()}
    assert ids == {root1["id"], root2["id"]}


def test_list_filter_parent_id(client):
    root = _create_root_container(client)
    h = _create(client, name="Hammer", kind="tool", parent_id=root["id"])
    s = _create(client, name="Screwdriver", kind="tool", parent_id=root["id"])
    response = client.get("/nodes", params={"parent": str(root["id"])})
    assert response.status_code == 200
    ids = {n["id"] for n in response.json()}
    assert ids == {h["id"], s["id"]}


def test_list_filter_parent_bad_value(client):
    response = client.get("/nodes", params={"parent": "abc"})
    assert response.status_code == 400


def test_list_filter_kind(client):
    _create(client, name="A", kind="tool")
    _create(client, name="B", kind="tool")
    _create(client, name="C", kind="consumable")
    response = client.get("/nodes", params={"kind": "tool"})
    assert response.status_code == 200
    assert len(response.json()) == 2


def test_list_filter_q(client):
    _create(client, name="Claw hammer")
    _create(client, name="Ball-peen hammer")
    _create(client, name="Screwdriver")
    response = client.get("/nodes", params={"q": "hammer"})
    assert response.status_code == 200
    names = [n["name"] for n in response.json()]
    assert "Claw hammer" in names and "Ball-peen hammer" in names
    assert "Screwdriver" not in names


def test_list_pagination(client):
    for i in range(5):
        _create(client, name=f"N{i}")
    page1 = client.get("/nodes", params={"limit": 2, "offset": 0}).json()
    page2 = client.get("/nodes", params={"limit": 2, "offset": 2}).json()
    assert len(page1) == 2 and len(page2) == 2
    assert {n["id"] for n in page1}.isdisjoint({n["id"] for n in page2})


# ---------- get one ----------


def test_get_one(client):
    n = _create(client, name="Hammer", kind="tool")
    response = client.get(f"/nodes/{n['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == n["id"]
    assert body["kind"]["slug"] == "tool"
    assert body["tags"] == []
    assert body["properties"] == []


def test_get_one_not_found(client):
    response = client.get("/nodes/99999")
    assert response.status_code == 404


# ---------- patch ----------


def test_patch_rename(client):
    n = _create(client, name="Old")
    response = client.patch(f"/nodes/{n['id']}", json={"name": "New"})
    assert response.status_code == 200
    assert response.json()["name"] == "New"


def test_patch_change_kind(client):
    n = _create(client, name="X", kind="item")
    response = client.patch(f"/nodes/{n['id']}", json={"kind": "tool"})
    assert response.status_code == 200
    assert response.json()["kind"]["slug"] == "tool"


def test_patch_reparent(client):
    a = _create_root_container(client, name="A")
    b = _create_root_container(client, name="B")
    leaf = _create(client, name="L", kind="tool", parent_id=a["id"])
    response = client.patch(f"/nodes/{leaf['id']}", json={"parent_id": b["id"]})
    assert response.status_code == 200
    assert response.json()["parent_id"] == b["id"]


def test_patch_reparent_to_root(client):
    parent = _create_root_container(client)
    child = _create(client, name="C", kind="item", parent_id=parent["id"])
    response = client.patch(f"/nodes/{child['id']}", json={"parent_id": None})
    assert response.status_code == 200
    assert response.json()["parent_id"] is None


def test_patch_reparent_to_self_rejected(client):
    n = _create_root_container(client)
    response = client.patch(f"/nodes/{n['id']}", json={"parent_id": n["id"]})
    assert response.status_code == 400


def test_patch_reparent_to_descendant_rejected(client):
    a = _create_root_container(client, name="A")
    b = _create(client, name="B", kind="cupboard", parent_id=a["id"], can_contain=True)
    response = client.patch(f"/nodes/{a['id']}", json={"parent_id": b["id"]})
    assert response.status_code == 400


def test_patch_reparent_to_leaf_rejected(client):
    parent = _create_root_container(client)
    leaf = _create(client, name="Leaf", kind="tool", can_contain=False)
    child = _create(client, name="Child", kind="item", parent_id=parent["id"])
    response = client.patch(f"/nodes/{child['id']}", json={"parent_id": leaf["id"]})
    assert response.status_code == 400


def test_patch_not_found(client):
    response = client.patch("/nodes/99999", json={"name": "x"})
    assert response.status_code == 404


def test_patch_extra_field_rejected(client):
    n = _create(client)
    response = client.patch(f"/nodes/{n['id']}", json={"bogus": "x"})
    assert response.status_code == 422


# ---------- delete ----------


def test_delete_leaf(client):
    n = _create(client)
    response = client.delete(f"/nodes/{n['id']}")
    assert response.status_code == 204
    assert client.get(f"/nodes/{n['id']}").status_code == 404


def test_delete_with_children_no_cascade(client):
    parent = _create_root_container(client)
    _create(client, name="C", kind="item", parent_id=parent["id"])
    response = client.delete(f"/nodes/{parent['id']}")
    assert response.status_code == 409


def test_delete_with_cascade(client):
    a = _create_root_container(client, name="A")
    b = _create(client, name="B", kind="cupboard", parent_id=a["id"], can_contain=True)
    c = _create(client, name="C", kind="item", parent_id=b["id"])
    response = client.delete(f"/nodes/{a['id']}", params={"cascade": "true"})
    assert response.status_code == 204
    for nid in (a["id"], b["id"], c["id"]):
        assert client.get(f"/nodes/{nid}").status_code == 404


def test_delete_not_found(client):
    response = client.delete("/nodes/99999")
    assert response.status_code == 404


# ---------- children / path / tree ----------


def test_get_children(client):
    parent = _create_root_container(client)
    a = _create(client, name="A", parent_id=parent["id"])
    b = _create(client, name="B", parent_id=parent["id"])
    response = client.get(f"/nodes/{parent['id']}/children")
    assert response.status_code == 200
    ids = {n["id"] for n in response.json()}
    assert ids == {a["id"], b["id"]}


def test_get_children_not_found(client):
    response = client.get("/nodes/99999/children")
    assert response.status_code == 404


def test_get_path(client):
    a = _create_root_container(client, name="A")
    b = _create(client, name="B", kind="cupboard", parent_id=a["id"], can_contain=True)
    c = _create(client, name="C", kind="item", parent_id=b["id"])
    response = client.get(f"/nodes/{c['id']}/path")
    assert response.status_code == 200
    names = [n["name"] for n in response.json()]
    assert names == ["A", "B", "C"]


def test_get_path_root_is_just_self(client):
    a = _create_root_container(client, name="Solo")
    response = client.get(f"/nodes/{a['id']}/path")
    assert response.status_code == 200
    assert [n["name"] for n in response.json()] == ["Solo"]


def test_get_tree(client):
    a = _create_root_container(client, name="A")
    b = _create(client, name="B", kind="cupboard", parent_id=a["id"], can_contain=True)
    c = _create(client, name="C", kind="item", parent_id=b["id"])
    response = client.get(f"/nodes/{a['id']}/tree")
    assert response.status_code == 200
    tree = response.json()
    assert tree["name"] == "A"
    assert len(tree["children"]) == 1
    assert tree["children"][0]["name"] == "B"
    assert tree["children"][0]["children"][0]["name"] == "C"


def test_get_tree_depth_zero(client):
    parent = _create_root_container(client)
    _create(client, name="C", kind="item", parent_id=parent["id"])
    response = client.get(f"/nodes/{parent['id']}/tree", params={"depth": 0})
    assert response.status_code == 200
    assert response.json()["children"] == []


def test_get_tree_depth_one(client):
    a = _create_root_container(client, name="A")
    b = _create(client, name="B", kind="cupboard", parent_id=a["id"], can_contain=True)
    _create(client, name="C", kind="item", parent_id=b["id"])
    response = client.get(f"/nodes/{a['id']}/tree", params={"depth": 1})
    assert response.status_code == 200
    tree = response.json()
    assert len(tree["children"]) == 1
    # depth=1 stops at B; C is not expanded
    assert tree["children"][0]["children"] == []
