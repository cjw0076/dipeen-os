import pytest

pytestmark = pytest.mark.asyncio


async def test_graph_nodes_empty(client):
    r = await client.get("/api/graph/nodes")
    assert r.status_code == 200
    assert r.json() == {"nodes": [], "edges": []}


async def test_graph_nodes_and_virtual_edges(client):
    await client.post("/api/agents", json={
        "agent_id": "pm-agent", "role": "PM",
        "metadata": {"node_class": "pm", "node_type": "ai", "name": "PM"},
    })
    await client.post("/api/agents", json={
        "agent_id": "fe-1", "role": "FE",
        "metadata": {"node_type": "ai", "parent_agent_id": "pm-agent", "name": "FE", "pos_x": 100, "pos_y": 50},
    })
    data = (await client.get("/api/graph/nodes")).json()
    ids = {n["id"]: n for n in data["nodes"]}
    assert ids["fe-1"]["parent_id"] == "pm-agent"
    assert ids["fe-1"]["pos_x"] == 100
    assert any(e["from"] == "pm-agent" and e["to"] == "fe-1" for e in data["edges"])


async def test_patch_position_persists(client):
    await client.post("/api/agents", json={"agent_id": "fe-2", "role": "FE", "metadata": {}})
    r = await client.patch("/api/graph/nodes/fe-2/position", json={"pos_x": 300, "pos_y": 200})
    assert r.status_code == 200
    data = (await client.get("/api/graph/nodes")).json()
    fe2 = next(n for n in data["nodes"] if n["id"] == "fe-2")
    assert fe2["pos_x"] == 300 and fe2["pos_y"] == 200
