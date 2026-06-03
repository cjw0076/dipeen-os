"""팀 협업 흐름 한 사이클 — web이 호출할 *실제 HTTP 엔드포인트*로 회의→실행까지 E2E.

이 테스트가 통과하면 web은 이 엔드포인트들만 순서대로 부르면 된다(아래 단계 = web 통합 순서).
gaps 1~4(Assignment Routing / Routing Preview / Workspace Registry / Meeting Closure)가 한 사이클로 연결됨을 증명.
"""
import pytest


@pytest.mark.asyncio
async def test_meeting_to_routed_command_one_cycle(client, tmp_path, monkeypatch):
    monkeypatch.setenv("NAT_WORKSPACE", str(tmp_path / "nat"))

    # 1) 회의방 + 메시지(회의)
    await client.post("/api/rooms", json={"room_id": "goal-login", "room_type": "goal", "title": "Login release"})
    for body, mtype in [("민준이 로그인 UI 구현하자", "discussion.message"),
                        ("상태관리는 Zustand 쓰자", "discussion.message"),
                        ("이 결정은 기억해두자", "discussion.message"),
                        ("테스트 실패 원인이 뭐야?", "discussion.message")]:
        await client.post("/api/rooms/goal-login/messages",
                          json={"sender_type": "human", "sender_id": "user://pm",
                                "message_type": mtype, "body": body})

    # 2) 회의 '정리' → 후보 분류(승인 전엔 작업 아님)
    packet = (await client.post("/api/rooms/goal-login/close")).json()
    assert len(packet["task_candidates"]) == 1            # "구현하자"만 작업 후보
    assert len(packet["decisions"]) == 1                  # "Zustand 쓰자"
    assert len(packet["memory_candidates"]) == 1 and len(packet["open_questions"]) == 1

    # 3) 후보에 배정(역할/repo/workspace) 추가 후 승인 → CommandProposal(배정 포함)
    cand = packet["task_candidates"][0]
    cand["suggested_role"] = "frontend"
    cand["scope"] = {"repo": "ezmap-web", "workspace_ref": "workspace://ezmap-web"}
    proposal = (await client.post("/api/meeting/action-candidates/approve",
                                  json={"room_id": "goal-login", "candidate": cand})).json()
    assert proposal["assignment"]["role"] == "frontend"
    assert proposal["assignment"]["repo"] == "ezmap-web"

    # 4) Routing Preview — "이 작업은 누구에게?" (worker 등록 전: 아무도 없음)
    pv0 = (await client.post("/api/routing/preview",
                             json={"assignment": {"role": "frontend", "repo": "ezmap-web",
                                                  "workspace_ref": "workspace://ezmap-web"}})).json()
    assert pv0["deliverable"] is False                    # 받을 worker 없음

    # 5) 민준 PC worker 등록(role/repo caps + workspace) — HQ는 local_path 모름
    await client.post("/api/workers", json={
        "worker_id": "worker.minjun-mac",
        "capabilities": ["provider.claude", "role.frontend", "user.minjun", "repo.ezmap-web", "workspace.write"],
        "workspaces": [{"workspace_ref": "workspace://ezmap-web", "repo": "repo.ezmap-web",
                        "local_path": "/Users/minjun/projects/ezmap-web",
                        "capabilities": ["repo.ezmap-web", "workspace.write"]}]})
    pv1 = (await client.post("/api/routing/preview",
                             json={"assignment": {"role": "frontend", "repo": "ezmap-web",
                                                  "workspace_ref": "workspace://ezmap-web"}})).json()
    assert pv1["deliverable"] is True and pv1["matching_workers"][0]["user"] == "minjun"
    assert pv1["matching_workers"][0]["workspace_available"] is True

    # 6) proposal confirm → run.start command(workspace_ref + 라우팅 caps), 절대경로 없음
    command = (await client.post(f"/api/proposals/{proposal['proposal_id']}/confirm",
                                 json={"decided_by": "user://web"})).json()
    assert command["workspace_ref"] == "workspace://ezmap-web"
    assert "role.frontend" in command["required_capabilities"] and "repo.ezmap-web" in command["required_capabilities"]
    assert not command["workspace_root"]                  # HQ는 절대 로컬 경로를 안 싣는다

    # 7) worker poll — *맞는 worker만* lease(라우팅). 다른 역할 worker는 못 가져감.
    await client.post("/api/workers", json={"worker_id": "worker.bob-qa",
                                            "capabilities": ["provider.claude", "role.qa", "workspace.write"]})
    none = (await client.post("/api/workers/worker.bob-qa/commands/poll",
                              json={"capabilities": ["provider.claude", "role.qa", "workspace.write"]})).json()
    assert none["command"] is None                        # QA worker는 FE 작업 못 가져감
    leased = (await client.post("/api/workers/worker.minjun-mac/commands/poll",
                                json={"capabilities": ["provider.claude", "role.frontend", "user.minjun",
                                                       "repo.ezmap-web", "workspace.write"]})).json()
    assert leased["command"]["command_id"] == command["command_id"]
    assert leased["command"]["workspace_ref"] == "workspace://ezmap-web"   # 민준 PC가 자기 경로로 resolve
