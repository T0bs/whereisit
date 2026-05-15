def test_list_returns_seeded_kinds(client):
    response = client.get("/kinds")
    assert response.status_code == 200
    slugs = {k["slug"] for k in response.json()}
    # seeded by migration
    assert {"room", "drawer", "tool", "item"}.issubset(slugs)


def test_create_kind(client):
    response = client.post("/kinds", json={"slug": "workbench", "label": "Workbench"})
    assert response.status_code == 201
    assert response.json()["slug"] == "workbench"
    assert response.json()["label"] == "Workbench"


def test_create_kind_default_label(client):
    response = client.post("/kinds", json={"slug": "tool_chest"})
    assert response.status_code == 201
    assert response.json()["label"] == "Tool Chest"


def test_create_kind_idempotent(client):
    first = client.post("/kinds", json={"slug": "workbench", "label": "Workbench"})
    second = client.post("/kinds", json={"slug": "workbench", "label": "Different"})
    assert first.status_code == 201
    assert second.status_code == 200
    # label of existing row is preserved; second call's label is ignored
    assert second.json()["label"] == "Workbench"
    assert first.json()["id"] == second.json()["id"]


def test_search_q_matches_slug_or_label(client):
    response = client.get("/kinds", params={"q": "drawer"})
    assert response.status_code == 200
    slugs = {k["slug"] for k in response.json()}
    assert "drawer" in slugs


def test_create_blank_slug_rejected(client):
    response = client.post("/kinds", json={"slug": ""})
    assert response.status_code == 422
