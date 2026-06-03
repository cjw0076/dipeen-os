"""HQ 출구 게이트 — /api/agents/{id}/report가 runner의 자기보고를 HQ가 재판정하는지(라우터 통합).

원칙: truth는 HQ만. runner가 status=done이라 보고해도 completion_promise=DONE이 아니거나(false-done)
범위를 벗어나면 HQ가 done으로 받지 않는다. W1 Gatekeeper를 보고 경계에 꽂은 솔기를 검증한다.
"""
import pytest

pytestmark = pytest.mark.asyncio


async def _register(client, agent_id="fe-agent", role="FE"):
    r = await client.post("/api/agents", json={"agent_id": agent_id, "role": role, "metadata": {"skills": []}})
    assert r.status_code in (200, 201), r.text
    return agent_id


async def _new_task(client, subject="t", prompt="do x", role="FE"):
    r = await client.post("/api/tasks", json={"subject": subject, "prompt": prompt, "required_role": role})
    assert r.status_code in (200, 201), r.text
    return r.json()["task_id"]


async def test_false_done_rejected(client):
    """runner=done이지만 completion_promise 없음 + 빈 scope_diff → HQ가 PROMISE_FALSE로 rejected."""
    aid = await _register(client)
    tid = await _new_task(client)
    r = await client.post(f"/api/agents/{aid}/report", json={
        "task_id": tid, "status": "done", "summary": "claimed done but did nothing",
        "artifacts": {"completion_promise": None, "scope_diff": [], "checks": {}},
    })
    assert r.status_code == 200, r.text
    t = (await client.get(f"/api/tasks/{tid}")).json()
    assert t["status"] == "rejected", t                         # done 아님
    assert t["result"]["gatekeeper"]["failure_code"] == "PROMISE_FALSE"


async def test_real_done_accepted(client):
    """completion_promise=DONE + 실제 변경 → accept → done."""
    aid = await _register(client)
    tid = await _new_task(client)
    r = await client.post(f"/api/agents/{aid}/report", json={
        "task_id": tid, "status": "done", "summary": "created Ping.tsx",
        "artifacts": {"completion_promise": "DONE", "scope_diff": ["src/components/Ping.tsx"], "checks": {}},
    })
    assert r.status_code == 200, r.text
    t = (await client.get(f"/api/tasks/{tid}")).json()
    assert t["status"] == "done", t
    assert t["result"]["gatekeeper"]["verdict"] == "accept"


async def test_secret_touch_needs_human(client):
    """비밀 경로(.env) 편집 → SCOPE_VIOLATION → needs_review(사람 게이트)."""
    aid = await _register(client)
    tid = await _new_task(client)
    r = await client.post(f"/api/agents/{aid}/report", json={
        "task_id": tid, "status": "done", "summary": "touched .env",
        "artifacts": {"completion_promise": "DONE", "scope_diff": [".env"], "checks": {}},
    })
    assert r.status_code == 200, r.text
    t = (await client.get(f"/api/tasks/{tid}")).json()
    assert t["status"] == "needs_review", t
    assert t["result"]["gatekeeper"]["failure_code"] == "SCOPE_VIOLATION"


async def test_failed_check_rejected(client):
    """결정론 검증 실패(pytest fail) → DETERMINISTIC_FAIL → rejected (promise=DONE이어도)."""
    aid = await _register(client)
    tid = await _new_task(client)
    r = await client.post(f"/api/agents/{aid}/report", json={
        "task_id": tid, "status": "done", "summary": "done but tests fail",
        "artifacts": {"completion_promise": "DONE", "scope_diff": ["src/x.ts"], "checks": {"pytest": "fail"}},
    })
    assert r.status_code == 200, r.text
    t = (await client.get(f"/api/tasks/{tid}")).json()
    assert t["status"] == "rejected", t
    assert t["result"]["gatekeeper"]["failure_code"] == "DETERMINISTIC_FAIL"
