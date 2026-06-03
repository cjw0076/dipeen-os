"""Wave 의존성(blocked_by) dispatch 해석 + unblock 통합 테스트.

배경(라이브 버그): PM이 LLM proposed_plan을 태스크로 변환할 때, blocked_by에
실제 task_id가 아닌 로컬 참조/placeholder("T-{wave1_task_id_placeholder}")가
들어온다. 서버 task_id는 생성 시점에야 만들어지므로 LLM은 알 수 없다.
dispatch가 이 로컬 참조를 *실제 생성된 task_id*로 치환하지 않으면, 의존 태스크는
존재하지 않는 id에 blocked → 영원히 unblock되지 않는다.
"""

import pytest

import pm_loop

pytestmark = pytest.mark.asyncio


# ── 순수 함수: 로컬 의존성 위상정렬 (_plan_dependency_order) ──────────────

async def test_plan_order_resolves_local_id_blocker():
    tasks = [
        {"subject": "wave1", "id": "t1"},
        {"subject": "wave2", "id": "t2", "blocked_by": "t1"},
    ]
    steps = pm_loop._plan_dependency_order(tasks)
    by_local = {s["local_id"]: s for s in steps}

    assert by_local["t1"]["depends_on"] is None
    assert by_local["t1"]["held_reason"] is None
    assert by_local["t2"]["depends_on"] == "t1"
    assert by_local["t2"]["held_reason"] is None
    # 선행 태스크가 의존 태스크보다 먼저 생성되어야 한다 (위상순서)
    order = [s["local_id"] for s in steps]
    assert order.index("t1") < order.index("t2")


async def test_plan_order_topologically_sorts_out_of_order_input():
    # 의존 태스크가 선행 태스크보다 앞에 나열돼도 올바르게 정렬돼야 한다
    tasks = [
        {"subject": "wave2", "id": "t2", "blocked_by": "t1"},
        {"subject": "wave1", "id": "t1"},
    ]
    steps = pm_loop._plan_dependency_order(tasks)
    order = [s["local_id"] for s in steps if s["held_reason"] is None]
    assert order.index("t1") < order.index("t2")
    t2 = next(s for s in steps if s["local_id"] == "t2")
    assert t2["depends_on"] == "t1"
    assert t2["held_reason"] is None


async def test_plan_order_holds_literal_placeholder_reference():
    # 정확히 라이브 버그의 입력: "T-"로 시작하는 리터럴 placeholder
    tasks = [
        {"subject": "wave1"},
        {"subject": "wave2", "blocked_by": "T-{wave1_task_id_placeholder}"},
    ]
    steps = pm_loop._plan_dependency_order(tasks)
    wave2 = next(s for s in steps if s["index"] == 1)
    # 실제 의존성으로 취급하지 않는다 (dangling)
    assert wave2["depends_on"] is None
    # 조용히 버리지 않고 사유를 남긴다 (fail-visible)
    assert wave2["held_reason"] is not None


async def test_plan_order_no_dependency_is_not_held():
    tasks = [{"subject": "a"}, {"subject": "b"}]
    steps = pm_loop._plan_dependency_order(tasks)
    assert all(s["depends_on"] is None and s["held_reason"] is None for s in steps)


async def test_plan_order_holds_cycle_and_self_reference():
    cycle = [
        {"subject": "a", "id": "a", "blocked_by": "b"},
        {"subject": "b", "id": "b", "blocked_by": "a"},
    ]
    steps = pm_loop._plan_dependency_order(cycle)
    # 사이클은 둘 다 surfaced (dangling block으로 생성하지 않는다)
    assert all(s["held_reason"] is not None for s in steps)

    selfref = [{"subject": "x", "id": "t1", "blocked_by": "t1"}]
    steps = pm_loop._plan_dependency_order(selfref)
    assert steps[0]["held_reason"] is not None


# ── 통합: _dispatch_plan → 실제 task_id 치환 → unblock ────────────────────

@pytest.fixture
def dispatch_env(monkeypatch, tmp_path):
    """_dispatch_plan의 POST를 테스트 ASGI 앱으로 보내고, chat/phase/workspace
    부수효과를 격리한다. 반환값은 _send_chat으로 보낸 메시지 캡처 리스트."""
    monkeypatch.setattr(pm_loop, "API_URL", "http://test")
    monkeypatch.setattr(pm_loop, "SHARED_DIR", str(tmp_path))
    monkeypatch.setenv("DIPEEN_PM_PROPOSAL_ONLY", "0")

    chat_msgs: list[str] = []

    async def _capture_chat(room_id, text, *args, **kwargs):
        chat_msgs.append(text)

    async def _noop_phase(*args, **kwargs):
        return None

    monkeypatch.setattr(pm_loop, "_send_chat", _capture_chat)
    monkeypatch.setattr(pm_loop, "_set_phase", _noop_phase)
    pm_loop.TASK_BATCH.clear()
    pm_loop.BATCH_STATE.clear()
    return chat_msgs


async def test_pm_loop_default_dispatch_is_proposal_only(client, monkeypatch, tmp_path):
    monkeypatch.setattr(pm_loop, "API_URL", "http://test")
    monkeypatch.setattr(pm_loop, "SHARED_DIR", str(tmp_path))
    monkeypatch.setenv("NAT_WORKSPACE", str(tmp_path / "nat"))
    monkeypatch.delenv("DIPEEN_PM_PROPOSAL_ONLY", raising=False)

    chat_msgs: list[str] = []

    async def _capture_chat(room_id, text, *args, **kwargs):
        chat_msgs.append(text)

    async def _noop_phase(*args, **kwargs):
        return None

    monkeypatch.setattr(pm_loop, "_send_chat", _capture_chat)
    monkeypatch.setattr(pm_loop, "_set_phase", _noop_phase)
    pm_loop.TASK_BATCH.clear()
    pm_loop.BATCH_STATE.clear()

    await pm_loop._dispatch_plan({
        "title": "proposal-only 계획",
        "tasks": [{"subject": "alpha build", "task": "구현한다", "required_role": "FE"}],
    }, "room-proposal-only", client)

    assert pm_loop.TASK_BATCH == {}
    tasks = (await client.get("/api/tasks")).json()
    assert tasks == []
    proposals = (await client.get("/api/proposals?room_id=room-proposal-only&state=proposed")).json()
    assert len(proposals) == 1
    assert proposals[0]["state"] == "proposed"
    assert (await client.get("/api/commands")).json() == []
    assert any("confirm해야 worker queue" in msg for msg in chat_msgs)


def _created_ids_by_subject() -> dict[str, str]:
    return {info["subject"]: tid for tid, info in pm_loop.TASK_BATCH.items()}


async def test_dispatch_resolves_wave2_to_real_wave1_id_then_unblocks(client, dispatch_env):
    plan = {
        "title": "2-wave 계획",
        "tasks": [
            {"subject": "wave1 build", "task": "빌드한다", "id": "t1"},
            {"subject": "wave2 verify", "task": "검증한다", "id": "t2", "blocked_by": "t1"},
        ],
    }
    await pm_loop._dispatch_plan(plan, "room-2wave", client)

    ids = _created_ids_by_subject()
    assert "wave1 build" in ids and "wave2 verify" in ids
    w1_id, w2_id = ids["wave1 build"], ids["wave2 verify"]

    w2 = (await client.get(f"/api/tasks/{w2_id}")).json()
    # 핵심: wave2가 *실제* wave1 task_id로 blocked (placeholder 아님)
    assert w2["blocked_by"] == w1_id
    assert w2["blocked_by"].startswith("T-")
    assert "placeholder" not in w2["blocked_by"]
    assert w2["status"] == "blocked"

    # wave1 완료(PATCH) → _unblock_dependents → wave2가 pending으로 전환
    r = await client.patch(f"/api/tasks/{w1_id}", json={"status": "done"})
    assert r.status_code == 200
    w2_after = (await client.get(f"/api/tasks/{w2_id}")).json()
    assert w2_after["status"] == "pending"
    assert w2_after["blocked_by"] is None


async def test_dispatch_never_creates_orphan_blocked_from_placeholder(client, dispatch_env):
    plan = {
        "title": "버그 재현 계획",
        "tasks": [
            {"subject": "ph wave1", "task": "빌드"},
            {"subject": "ph wave2", "task": "검증",
             "blocked_by": "T-{wave1_task_id_placeholder}"},
        ],
    }
    await pm_loop._dispatch_plan(plan, "room-ph", client)
    ids = _created_ids_by_subject()

    # wave1은 정상 생성
    assert "ph wave1" in ids
    # placeholder를 가진 wave2는 존재하지 않는 id에 blocked된 채 생성되면 안 된다
    if "ph wave2" in ids:
        w2 = (await client.get(f"/api/tasks/{ids['ph wave2']}")).json()
        assert w2["blocked_by"] != "T-{wave1_task_id_placeholder}"
        assert w2["status"] != "blocked"
    # 해석 실패는 채팅으로 surfaced 되어야 한다 (silent hang 금지)
    assert any("ph wave2" in m for m in dispatch_env)


# ── 통합: 에이전트 보고 경로(/report)의 unblock (Bug #2 회귀) ───────────────

async def test_agent_report_done_unblocks_blocked_dependent(client):
    """실제 에이전트 완료 경로 POST /api/agents/{id}/report 가 blocked 의존
    태스크를 unblock 하는지. (기존 코드는 status=='pending' 으로 필터해 blocked
    태스크를 영원히 놓쳤다.)"""
    await client.post("/api/agents", json={"agent_id": "be-agent", "role": "BE", "metadata": {}})

    w1 = (await client.post("/api/tasks", json={"subject": "rep wave1", "prompt": "do"})).json()
    w1_id = w1["task_id"]
    w2 = (await client.post("/api/tasks", json={
        "subject": "rep wave2", "prompt": "do", "blocked_by": w1_id})).json()
    w2_id = w2["task_id"]
    assert w2["status"] == "blocked"

    r = await client.post("/api/agents/be-agent/report",
                          json={"task_id": w1_id, "status": "done"})
    assert r.status_code == 200

    w2_after = (await client.get(f"/api/tasks/{w2_id}")).json()
    assert w2_after["status"] == "pending"
    assert w2_after["blocked_by"] is None
