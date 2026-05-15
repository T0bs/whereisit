def test_list_empty(client):
    response = client.get("/tags")
    assert response.status_code == 200
    assert response.json() == []


def test_create_tag(client):
    response = client.post("/tags", json={"name": "metal"})
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "metal"
    assert body["id"] > 0


def test_create_tag_is_idempotent(client):
    first = client.post("/tags", json={"name": "metal"})
    second = client.post("/tags", json={"name": "metal"})
    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_list_after_creates(client):
    client.post("/tags", json={"name": "metal"})
    client.post("/tags", json={"name": "wood"})
    response = client.get("/tags")
    names = [t["name"] for t in response.json()]
    assert names == ["metal", "wood"]


def test_search_q(client):
    for n in ("hammer", "mallet", "screwdriver"):
        client.post("/tags", json={"name": n})
    response = client.get("/tags", params={"q": "mer"})
    names = {t["name"] for t in response.json()}
    assert names == {"hammer"}


def test_create_blank_name_rejected(client):
    response = client.post("/tags", json={"name": ""})
    assert response.status_code == 422
