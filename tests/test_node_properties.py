def _make_node(client, **kwargs):
    body = {"name": "x", "kind": "item"}
    body.update(kwargs)
    return client.post("/nodes", json=body).json()


def test_set_string_property(client):
    node = _make_node(client)
    response = client.put(
        f"/nodes/{node['id']}/properties/color",
        json={"value": "red"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body == {"key": "color", "value": "red", "value_type": "string"}


def test_set_int_property(client):
    node = _make_node(client)
    response = client.put(
        f"/nodes/{node['id']}/properties/weight_g",
        json={"value": 600, "value_type": "int"},
    )
    assert response.status_code == 201
    assert response.json() == {
        "key": "weight_g",
        "value": "600",
        "value_type": "int",
    }


def test_set_float_property(client):
    node = _make_node(client)
    response = client.put(
        f"/nodes/{node['id']}/properties/length_m",
        json={"value": 1.25, "value_type": "float"},
    )
    assert response.status_code == 201
    assert response.json()["value"] == "1.25"


def test_set_bool_property(client):
    node = _make_node(client)
    response = client.put(
        f"/nodes/{node['id']}/properties/fragile",
        json={"value": True, "value_type": "bool"},
    )
    assert response.status_code == 201
    assert response.json()["value"] == "true"


def test_set_int_rejects_non_int(client):
    node = _make_node(client)
    response = client.put(
        f"/nodes/{node['id']}/properties/weight_g",
        json={"value": "heavy", "value_type": "int"},
    )
    assert response.status_code == 400


def test_set_bool_rejects_garbage(client):
    node = _make_node(client)
    response = client.put(
        f"/nodes/{node['id']}/properties/fragile",
        json={"value": "kinda", "value_type": "bool"},
    )
    assert response.status_code == 400


def test_update_existing_property(client):
    node = _make_node(client)
    client.put(f"/nodes/{node['id']}/properties/color", json={"value": "red"})
    response = client.put(
        f"/nodes/{node['id']}/properties/color", json={"value": "blue"}
    )
    assert response.status_code == 200
    assert response.json()["value"] == "blue"


def test_property_key_type_is_sticky(client):
    """Once a property key exists, its value_type ignores subsequent overrides."""
    a = _make_node(client, name="A")
    b = _make_node(client, name="B")
    client.put(
        f"/nodes/{a['id']}/properties/weight_g",
        json={"value": 600, "value_type": "int"},
    )
    # Try to declare it as float on a different node — should be treated as int
    response = client.put(
        f"/nodes/{b['id']}/properties/weight_g",
        json={"value": 750, "value_type": "float"},
    )
    assert response.status_code == 201
    assert response.json()["value_type"] == "int"


def test_invalid_value_type_on_create_rejected(client):
    node = _make_node(client)
    response = client.put(
        f"/nodes/{node['id']}/properties/x",
        json={"value": "y", "value_type": "wibble"},
    )
    assert response.status_code == 400


def test_list_properties(client):
    node = _make_node(client)
    client.put(f"/nodes/{node['id']}/properties/color", json={"value": "red"})
    client.put(
        f"/nodes/{node['id']}/properties/weight_g",
        json={"value": 600, "value_type": "int"},
    )
    response = client.get(f"/nodes/{node['id']}/properties")
    assert response.status_code == 200
    by_key = {p["key"]: p for p in response.json()}
    assert by_key["color"]["value"] == "red"
    assert by_key["weight_g"] == {
        "key": "weight_g",
        "value": "600",
        "value_type": "int",
    }


def test_delete_property(client):
    node = _make_node(client)
    client.put(f"/nodes/{node['id']}/properties/color", json={"value": "red"})
    response = client.delete(f"/nodes/{node['id']}/properties/color")
    assert response.status_code == 204
    assert client.get(f"/nodes/{node['id']}/properties").json() == []


def test_delete_property_not_set(client):
    node = _make_node(client)
    response = client.delete(f"/nodes/{node['id']}/properties/color")
    assert response.status_code == 404


def test_get_node_includes_properties(client):
    node = _make_node(client)
    client.put(f"/nodes/{node['id']}/properties/color", json={"value": "red"})
    detail = client.get(f"/nodes/{node['id']}").json()
    assert detail["properties"] == [
        {"key": "color", "value": "red", "value_type": "string"}
    ]
