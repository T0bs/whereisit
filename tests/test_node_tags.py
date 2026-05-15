def _make_node(client, **kwargs):
    body = {"name": "x", "kind": "item"}
    body.update(kwargs)
    return client.post("/nodes", json=body).json()


def test_add_tag_creates_tag_and_association(client):
    node = _make_node(client)
    response = client.post(f"/nodes/{node['id']}/tags", json={"name": "metal"})
    assert response.status_code == 201
    tag = response.json()
    assert tag["name"] == "metal"
    # GET /nodes/{id} now reflects the tag
    detail = client.get(f"/nodes/{node['id']}").json()
    assert any(t["id"] == tag["id"] for t in detail["tags"])


def test_add_existing_tag_returns_200(client):
    client.post("/tags", json={"name": "metal"})
    node = _make_node(client)
    response = client.post(f"/nodes/{node['id']}/tags", json={"name": "metal"})
    # tag exists, but association is new → still 201
    assert response.status_code == 201


def test_add_same_tag_twice_is_noop(client):
    node = _make_node(client)
    client.post(f"/nodes/{node['id']}/tags", json={"name": "metal"})
    response = client.post(f"/nodes/{node['id']}/tags", json={"name": "metal"})
    assert response.status_code == 200
    detail = client.get(f"/nodes/{node['id']}").json()
    assert len([t for t in detail["tags"] if t["name"] == "metal"]) == 1


def test_remove_tag(client):
    node = _make_node(client)
    tag = client.post(
        f"/nodes/{node['id']}/tags", json={"name": "metal"}
    ).json()
    response = client.delete(f"/nodes/{node['id']}/tags/{tag['id']}")
    assert response.status_code == 204
    detail = client.get(f"/nodes/{node['id']}").json()
    assert detail["tags"] == []


def test_remove_tag_not_assigned(client):
    node = _make_node(client)
    tag = client.post("/tags", json={"name": "metal"}).json()
    response = client.delete(f"/nodes/{node['id']}/tags/{tag['id']}")
    assert response.status_code == 404


def test_remove_tag_from_missing_node(client):
    response = client.delete("/nodes/99999/tags/1")
    assert response.status_code == 404


def test_add_tag_filter_works_end_to_end(client):
    a = _make_node(client, name="Hammer 1")
    b = _make_node(client, name="Hammer 2")
    _make_node(client, name="Screwdriver")
    client.post(f"/nodes/{a['id']}/tags", json={"name": "metal"})
    client.post(f"/nodes/{b['id']}/tags", json={"name": "metal"})
    response = client.get("/nodes", params={"tag": "metal"})
    ids = {n["id"] for n in response.json()}
    assert ids == {a["id"], b["id"]}
