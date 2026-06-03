"""프로젝트 노드 라우터 통합 — /api/projects/{id}/nodes 솔기.

node_service 단위 테스트(test_node_service)를 HTTP/라우터 층에서 한 번 더 묶는다. 프론트
(@xyflow ProjectGraph)가 실제로 소비하는 응답 모양({nodes, edges})과 PM 별칭·위치 영속·
삭제 시 cascade reparent를 soft-auth(default-team) 경로로 검증한다.
"""
import pytest

pytestmark = pytest.mark.asyncio


async def test_project_node_lifecycle(client):
    # 프로젝트 생성
    r = await client.post("/api/projects", json={"name": "Graph Demo"})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]

    # GET nodes → seed_pm 멱등 → PM 1개 + 엣지 0, 프론트가 기대하는 {nodes,edges} 모양
    r = await client.get(f"/api/projects/{pid}/nodes")
    assert r.status_code == 200, r.text
    g = r.json()
    assert set(g.keys()) == {"nodes", "edges"}
    assert len(g["nodes"]) == 1 and g["nodes"][0]["node_class"] == "pm"
    assert g["edges"] == []

    # POST agent 노드 (parent="pm" 별칭)
    r = await client.post(
        f"/api/projects/{pid}/nodes",
        json={"name": "FE", "role": "FE", "parent_id": "pm"},
    )
    assert r.status_code == 200, r.text
    node = r.json()
    assert node["node_class"] == "agent"
    assert node["parent_id"] == "pm"          # PM 부모는 별칭으로 반환
    nid = node["id"]

    # GET → 2 nodes, 1 edge(pm→fe)
    g = (await client.get(f"/api/projects/{pid}/nodes")).json()
    assert len(g["nodes"]) == 2
    assert len(g["edges"]) == 1 and g["edges"][0]["to"] == nid

    # 위치 영속 (드래그 종료 → moveNode)
    r = await client.patch(
        f"/api/projects/{pid}/nodes/{nid}/position",
        json={"pos_x": 120.5, "pos_y": -40.0},
    )
    assert r.status_code == 200, r.text
    assert r.json()["pos_x"] == 120.5

    g = (await client.get(f"/api/projects/{pid}/nodes")).json()
    moved = next(n for n in g["nodes"] if n["id"] == nid)
    assert moved["pos_x"] == 120.5 and moved["pos_y"] == -40.0

    # 삭제 → PM만 남음
    r = await client.delete(f"/api/projects/{pid}/nodes/{nid}")
    assert r.status_code == 200 and r.json()["ok"] is True
    g = (await client.get(f"/api/projects/{pid}/nodes")).json()
    assert len(g["nodes"]) == 1


async def test_delete_reparents_children(client):
    """삭제된 노드의 자식이 부모(PM)로 입양 — 고아 방지(라우터 경유)."""
    pid = (await client.post("/api/projects", json={"name": "Reparent"})).json()["id"]
    await client.get(f"/api/projects/{pid}/nodes")     # seed PM

    lead = (await client.post(f"/api/projects/{pid}/nodes",
                              json={"name": "lead", "parent_id": "pm"})).json()
    sub = (await client.post(f"/api/projects/{pid}/nodes",
                             json={"name": "sub", "parent_id": lead["id"]})).json()
    assert sub["parent_id"] == lead["id"]

    await client.delete(f"/api/projects/{pid}/nodes/{lead['id']}")
    g = (await client.get(f"/api/projects/{pid}/nodes")).json()
    ids = {n["id"] for n in g["nodes"]}
    assert lead["id"] not in ids                       # 삭제됨
    sub_after = next(n for n in g["nodes"] if n["id"] == sub["id"])
    assert sub_after["parent_id"] == "pm"              # 조부모(PM)로 입양


async def test_unknown_project_404(client):
    r = await client.get("/api/projects/does-not-exist/nodes")
    assert r.status_code == 404


async def test_member_invite_flow(client):
    """프로젝트 멤버 초대(pending) → active 전환 — Node와 함께 흡수한 ProjectMember 솔기."""
    pid = (await client.post("/api/projects", json={"name": "Members"})).json()["id"]

    r = await client.post(f"/api/projects/{pid}/members",
                          json={"email": "min@team.dev", "role": "editor"})
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["status"] == "pending" and m["role"] == "editor"

    r = await client.patch(f"/api/projects/{pid}/members/{m['id']}",
                           json={"status": "active"})
    assert r.status_code == 200
    assert r.json()["status"] == "active" and r.json()["joined_at"] is not None
