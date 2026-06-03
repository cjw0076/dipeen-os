"""
E2E Smoke Test — dipeen Web Platform 전체 검증 (LLM 불필요)

실행 전: uvicorn app.main:app  (api/ 디렉토리에서)
실행:    python scripts/e2e_smoke.py
"""

import asyncio
import json
import sys

import httpx
import websockets

BASE     = "http://localhost:8000"
WS_URL   = "ws://localhost:8000/ws/events"

AGENT_ID   = "e2e-test-fe"
AGENT_ID_2 = "e2e-test-be"

_pass = 0
_fail = 0
_skip = 0


def ok(msg: str) -> None:
    global _pass
    _pass += 1
    print(f"    [OK] {msg}")


def fail(msg: str) -> None:
    global _fail
    _fail += 1
    print(f"    [FAIL] {msg}")


def skip(msg: str) -> None:
    global _skip
    _skip += 1
    print(f"    [SKIP] {msg}")


# ══════════════════════════════════════════════════════════
# 1. API Health
# ══════════════════════════════════════════════════════════
async def test_health(c: httpx.AsyncClient) -> None:
    print("\n[1] API Health")
    r = await c.get(f"{BASE}/health")
    assert r.status_code == 200 and r.json().get("status") == "ok"
    ok(f"GET /health → {r.json()}")


# ══════════════════════════════════════════════════════════
# 2. WebSocket ping/pong
# ══════════════════════════════════════════════════════════
async def test_ws(c: httpx.AsyncClient) -> None:
    print("\n[2] WebSocket")
    async with websockets.connect(WS_URL, open_timeout=3) as ws:
        await ws.send("ping")
        pong = await asyncio.wait_for(ws.recv(), timeout=3)
        assert pong == "pong"
    ok("WS ping/pong")


# ══════════════════════════════════════════════════════════
# 3. Meeting API
# ══════════════════════════════════════════════════════════
async def test_meeting(c: httpx.AsyncClient) -> None:
    print("\n[3] Meeting API")
    r = await c.get(f"{BASE}/api/meeting/state?room_id=e2e-room")
    assert r.status_code == 200
    s = r.json()
    assert s["phase"] in ("DISCUSSING", "SOLICITING", "BRIEF_READY", "EXECUTING", "DONE")
    ok(f"GET /meeting/state phase={s['phase']}")

    for mode in ("plan", "brainstorm", "review", "debate"):
        r = await c.post(f"{BASE}/api/meeting/mode",
                         json={"room_id": "e2e-room", "mode": mode})
        assert r.status_code == 200, f"mode={mode} failed: {r.text}"
    ok("mode 전환 plan/brainstorm/review/debate")

    r = await c.post(f"{BASE}/api/meeting/mode",
                     json={"room_id": "e2e-room", "mode": "invalid_mode"})
    assert r.status_code == 400
    ok("잘못된 mode → 400")


# ══════════════════════════════════════════════════════════
# 4. Chat 영속성 + 멀티룸 격리
# ══════════════════════════════════════════════════════════
async def test_chat(c: httpx.AsyncClient) -> None:
    print("\n[4] Chat 영속성 + 멀티룸 격리")
    # room-A 메시지
    r = await c.post(f"{BASE}/api/chat/messages", json={
        "room_id": "e2e-room-a", "text": "hello room-a",
        "sender": "user", "sender_type": "user",
    })
    assert r.status_code == 200
    msg_id = r.json()["id"]
    ok(f"POST /chat/messages room-a id={msg_id[:8]}")

    # room-B 메시지
    r = await c.post(f"{BASE}/api/chat/messages", json={
        "room_id": "e2e-room-b", "text": "hello room-b",
        "sender": "user", "sender_type": "user",
    })
    assert r.status_code == 200
    ok("POST /chat/messages room-b")

    # room-A 히스토리 — room-b 메시지가 없어야 함
    r = await c.get(f"{BASE}/api/chat/history?room_id=e2e-room-a")
    assert r.status_code == 200
    msgs = r.json()
    texts = [m["text"] for m in msgs]
    assert any("room-a" in t for t in texts), "room-a 메시지 없음"
    assert not any("room-b" in t for t in texts), "room-b 메시지가 room-a에 노출됨!"
    ok("멀티룸 격리 확인 (room-b 메시지 room-a에서 보이지 않음)")


# ══════════════════════════════════════════════════════════
# 5. 온보딩
# ══════════════════════════════════════════════════════════
async def test_onboarding(c: httpx.AsyncClient) -> None:
    print("\n[5] 온보딩")
    r = await c.get(f"{BASE}/api/onboarding/check?room_id=e2e-fresh-room")
    assert r.status_code == 200
    d = r.json()
    assert "is_fresh" in d and "task_count" in d
    ok(f"GET /onboarding/check is_fresh={d['is_fresh']} tasks={d['task_count']}")

    # 이미 태스크가 있으면 seed는 skip
    r = await c.post(f"{BASE}/api/onboarding/seed",
                     json={"room_id": "e2e-fresh-room"})
    assert r.status_code == 200
    s = r.json()
    assert s["ok"]
    ok(f"POST /onboarding/seed seeded={s['seeded']} skipped={s.get('skipped', False)}")


# ══════════════════════════════════════════════════════════
# 6. 에이전트 등록 + heartbeat + roster
# ══════════════════════════════════════════════════════════
async def test_agents(c: httpx.AsyncClient) -> dict:
    print("\n[6] 에이전트 등록 + heartbeat + roster")
    # 등록 (혹은 재등록)
    r = await c.post(f"{BASE}/api/agents", json={
        "agent_id": AGENT_ID,
        "role": "FE",
        "metadata": {"skills": ["React", "TypeScript"], "model": "test-model"},
    })
    assert r.status_code in (200, 201), r.text
    agent = r.json()
    ok(f"에이전트 등록: {agent['agent_id']} db_id={agent['id'][:8]}")

    # heartbeat
    r = await c.post(f"{BASE}/api/agents/{AGENT_ID}/heartbeat",
                     json={"status": "idle", "current_task_id": None})
    assert r.status_code == 200
    ok("heartbeat idle")

    # roster
    r = await c.get(f"{BASE}/api/agents/roster")
    assert r.status_code == 200
    roster = r.json()["agents"]
    assert any(a["agent_id"] == AGENT_ID for a in roster)
    ok(f"roster {len(roster)}명 확인")

    return agent


# ══════════════════════════════════════════════════════════
# 7. 태스크 생명 주기 (poll → in_progress → done)
# ══════════════════════════════════════════════════════════
async def test_task_lifecycle(c: httpx.AsyncClient) -> str:
    print("\n[7] 태스크 생명 주기")

    # 이전 pending 정리
    r = await c.get(f"{BASE}/api/tasks?status=pending")
    for t in r.json():
        if t.get("required_role") == "FE":
            await c.post(f"{BASE}/api/tasks/{t['task_id']}/cancel")

    # 생성
    r = await c.post(f"{BASE}/api/tasks", json={
        "subject": "[E2E] Hello World 컴포넌트",
        "prompt":  "src/Hello.tsx 작성",
        "required_role": "FE",
    })
    assert r.status_code in (200, 201), r.text
    task_id = r.json()["task_id"]
    ok(f"태스크 생성 {task_id}")

    # heartbeat idle → poll
    await c.post(f"{BASE}/api/agents/{AGENT_ID}/heartbeat",
                 json={"status": "idle", "current_task_id": None})
    print("    [wait] polling...", end="", flush=True)
    r = await c.get(f"{BASE}/api/agents/{AGENT_ID}/poll", timeout=40)
    assert r.status_code == 200
    polled_id = r.json()["task_id"]
    ok(f" poll 수령 {polled_id}")

    # in_progress 확인
    r = await c.get(f"{BASE}/api/tasks/{polled_id}")
    assert r.json()["status"] == "in_progress"
    ok("status=in_progress")

    # 완료 보고
    r = await c.post(f"{BASE}/api/agents/{AGENT_ID}/report", json={
        "task_id": polled_id, "status": "done",
        "tests_passed": True, "summary": "E2E OK",
        "usage": {"input_tokens": 100, "output_tokens": 50, "model": "test"},
        "artifacts": {"changed_files": ["src/Hello.tsx"],
                      "key_decisions": [], "blockers": [], "references": {}},
    })
    assert r.status_code == 200
    ok("완료 보고")

    # done 확인
    r = await c.get(f"{BASE}/api/tasks/{polled_id}")
    assert r.json()["status"] == "done"
    ok("status=done")

    return polled_id


# ══════════════════════════════════════════════════════════
# 8. 태스크 의존성 체인 (P5-1)
# ══════════════════════════════════════════════════════════
async def test_dependency_chain(c: httpx.AsyncClient) -> None:
    print("\n[8] 태스크 의존성 체인 (blocked_by)")

    # T1 생성 (선행)
    r = await c.post(f"{BASE}/api/tasks", json={
        "subject": "[E2E] 선행 태스크 T1",
        "prompt":  "선행 작업",
        "required_role": "BE",
    })
    assert r.status_code in (200, 201)
    t1_id = r.json()["task_id"]
    ok(f"선행 태스크 생성: {t1_id}")

    # T2 생성 (T1에 blocked)
    r = await c.post(f"{BASE}/api/tasks", json={
        "subject": "[E2E] 후행 태스크 T2",
        "prompt":  "후행 작업",
        "required_role": "BE",
        "blocked_by": t1_id,
    })
    assert r.status_code in (200, 201)
    t2 = r.json()
    t2_id = t2["task_id"]
    assert t2["status"] == "blocked", f"blocked_by 태스크가 blocked 상태가 아님: {t2['status']}"
    ok(f"후행 태스크 생성 (blocked): {t2_id}")

    # T2가 poll에 잡히지 않아야 함
    r = await c.post(f"{BASE}/api/agents/{AGENT_ID}/heartbeat",
                     json={"status": "idle", "current_task_id": None})
    # T2는 blocked이므로 poll이 다른 태스크를 주거나 null을 반환해야 함
    # (T1을 BE 에이전트에 등록해서 직접 처리하면 복잡해지므로 여기서는 T1을 직접 PATCH로 완료)
    r = await c.patch(f"{BASE}/api/tasks/{t1_id}", json={"status": "done"})
    assert r.status_code == 200
    ok(f"T1 강제 완료")

    # T2 자동 unblock 확인 (약간의 대기)
    await asyncio.sleep(0.3)
    r = await c.get(f"{BASE}/api/tasks/{t2_id}")
    t2_after = r.json()
    assert t2_after["status"] == "pending", \
        f"T1 완료 후 T2가 pending으로 전환되지 않음: {t2_after['status']}"
    assert t2_after["blocked_by"] is None, "blocked_by가 초기화되지 않음"
    ok(f"T2 자동 unblock → pending (blocked_by=None)")

    # 정리
    await c.post(f"{BASE}/api/tasks/{t2_id}/cancel")


# ══════════════════════════════════════════════════════════
# 9. CompetencyScore 진화
# ══════════════════════════════════════════════════════════
async def test_competency(c: httpx.AsyncClient) -> None:
    print("\n[9] CompetencyScore 진화")
    r = await c.get(f"{BASE}/api/agents/roster")
    roster = r.json()["agents"]
    agent = next((a for a in roster if a["agent_id"] == AGENT_ID), None)
    assert agent, "에이전트 roster에 없음"
    score = agent["competency"].get("FE", 0)
    assert score > 0, f"score=0 (진화 실패)"
    ok(f"FE competency={score:.1f}/100")


# ══════════════════════════════════════════════════════════
# 10. Auth 엔드포인트 존재 확인
# ══════════════════════════════════════════════════════════
async def test_auth_endpoints(c: httpx.AsyncClient) -> None:
    print("\n[10] Auth 엔드포인트")
    # BOT_TOKEN 없으므로 503 예상
    r = await c.post(f"{BASE}/api/auth/telegram", json={
        "id": 123, "first_name": "Test", "auth_date": 0, "hash": "fakehash",
    })
    assert r.status_code in (503, 401), f"expected 503/401, got {r.status_code}"
    ok(f"POST /auth/telegram (no bot token) → {r.status_code}")

    # /me without token → 401
    r = await c.get(f"{BASE}/api/auth/me")
    assert r.status_code == 401
    ok("GET /auth/me (no token) → 401")


# ══════════════════════════════════════════════════════════
# Cleanup
# ══════════════════════════════════════════════════════════
async def cleanup(c: httpx.AsyncClient) -> None:
    print("\n[~] 정리...")
    for aid in (AGENT_ID, AGENT_ID_2):
        try:
            await c.delete(f"{BASE}/api/agents/{aid}")
        except Exception:
            pass
    print("    테스트 에이전트 삭제 완료")


# ══════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════
async def main() -> None:
    print("=" * 60)
    print("  dipeen E2E Test Suite")
    print("=" * 60)

    tests = [
        ("API Health",       test_health),
        ("WebSocket",        test_ws),
        ("Meeting API",      test_meeting),
        ("Chat 영속성",       test_chat),
        ("온보딩",            test_onboarding),
        ("에이전트",          test_agents),
        ("태스크 라이프사이클", test_task_lifecycle),
        ("의존성 체인",       test_dependency_chain),
        ("CompetencyScore",  test_competency),
        ("Auth 엔드포인트",   test_auth_endpoints),
    ]

    async with httpx.AsyncClient(base_url=BASE, timeout=45) as c:
        for name, fn in tests:
            try:
                await fn(c)
            except Exception as e:
                global _fail
                _fail += 1
                print(f"\n    [FAIL] {name}: {e}")

        await cleanup(c)

    print("\n" + "=" * 60)
    total = _pass + _fail + _skip
    print(f"  결과: {_pass}/{total} 통과"
          + (f"  ({_fail} 실패)" if _fail else "")
          + (f"  ({_skip} 스킵)" if _skip else ""))
    if _fail:
        sys.exit(1)
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
