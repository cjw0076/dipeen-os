"""
Demo Pre-flight Check — 3명 데모 전 E2E 파이프라인 검증

실행: python scripts/demo_check.py [api_url]
기본: http://localhost:8000
"""

import asyncio
import json
import os
import sys
import time

# Windows cp949 인코딩 문제 해결
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
    except Exception:
        pass

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"

_pass = 0
_fail = 0


def ok(msg: str) -> None:
    global _pass
    _pass += 1
    print(f"  ✅ {msg}")


def fail(msg: str) -> None:
    global _fail
    _fail += 1
    print(f"  ❌ {msg}")


async def check(name: str, coro) -> None:
    print(f"\n🔍 {name}")
    try:
        await coro
    except Exception as e:
        fail(f"Exception: {e}")


async def main() -> None:
    print(f"═══ dipeen Demo Pre-flight Check ═══")
    print(f"API: {BASE}\n")

    async with httpx.AsyncClient(base_url=BASE, timeout=10) as c:

        # 1. Health check
        async def health():
            # /api/health (nginx proxy) or /health (direct) 둘 다 시도
            for path in ["/api/health", "/health"]:
                r = await c.get(path)
                if r.status_code == 200:
                    ok(f"API 서버 응답 ({path})")
                    return
            fail(f"API 서버 응답 실패 (/api/health, /health 모두 실패)")

        await check("API 서버 헬스체크", health())

        # 2. Agent list
        async def agents():
            r = await c.get("/api/agents")
            if r.status_code == 200:
                data = r.json()
                ok(f"에이전트 목록 조회 ({len(data)}개)")
                online = [a for a in data if a.get("status") != "offline"]
                if online:
                    ok(f"온라인 에이전트: {', '.join(a['agent_id'] for a in online)}")
                else:
                    fail("온라인 에이전트 없음 — agent-client 실행 필요")
            else:
                fail(f"에이전트 목록 실패: {r.status_code}")

        await check("에이전트 상태", agents())

        # 3. Task list
        async def tasks():
            r = await c.get("/api/tasks")
            if r.status_code == 200:
                data = r.json()
                ok(f"태스크 목록 조회 ({len(data)}개)")
                stuck = [t for t in data if t.get("status") == "in_progress"]
                if stuck:
                    fail(f"in_progress 태스크 {len(stuck)}개 — stuck 가능성 확인")
                    for t in stuck[:3]:
                        print(f"      ⚠ {t['task_id']}: {t['subject'][:40]}")
                else:
                    ok("stuck 태스크 없음")
            else:
                fail(f"태스크 목록 실패: {r.status_code}")

        await check("태스크 상태", tasks())

        # 4. Chat endpoint
        async def chat():
            r = await c.post("/api/chat/messages", json={
                "room_id": "general",
                "sender": "demo-check",
                "sender_type": "user",
                "text": "demo check ping",
            })
            if r.status_code in (200, 201):
                ok("채팅 메시지 전송")
            else:
                fail(f"채팅 전송 실패: {r.status_code} {r.text[:100]}")

        await check("채팅 API", chat())

        # 5. WebSocket
        async def websocket():
            try:
                import websockets
                ws_url = BASE.replace("http", "ws") + "/ws/events"
                async with websockets.connect(ws_url, open_timeout=5) as ws:
                    ok(f"WebSocket 연결 성공: {ws_url}")
                    # 수신 테스트 (1초 대기)
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=2)
                        data = json.loads(msg)
                        ok(f"WS 이벤트 수신: {data.get('type', 'unknown')}")
                    except asyncio.TimeoutError:
                        ok("WS 연결됨 (대기 이벤트 없음 — 정상)")
            except ImportError:
                fail("websockets 패키지 미설치")
            except Exception as e:
                fail(f"WebSocket 연결 실패: {e}")

        await check("WebSocket 연결", websocket())

        # 6. Chat history
        async def chat_history():
            r = await c.get("/api/chat/history", params={"room_id": "general", "limit": 5})
            if r.status_code == 200:
                data = r.json()
                ok(f"채팅 히스토리 조회 ({len(data)}건)")
            else:
                fail(f"채팅 히스토리 실패: {r.status_code}")

        await check("채팅 히스토리", chat_history())

        # 7. Usage summary
        async def usage():
            r = await c.get("/api/usage/summary")
            if r.status_code == 200:
                data = r.json()
                ok(f"사용량: {data.get('total_tokens', 0):,} tokens")
            else:
                fail(f"사용량 API 실패: {r.status_code}")

        await check("사용량 API", usage())

    # Summary
    print(f"\n{'═' * 40}")
    total = _pass + _fail
    if _fail == 0:
        print(f"🎉 ALL PASSED ({_pass}/{total})")
        print(f"\n데모 준비 완료! 3명 접속 후 채팅에서 '@pm 작업지시' 입력하세요.")
    else:
        print(f"⚠️  {_fail} FAILED / {_pass} passed ({total} total)")
        print(f"\n실패 항목을 수정한 후 다시 실행하세요.")
    print()


if __name__ == "__main__":
    asyncio.run(main())
