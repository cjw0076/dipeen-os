"""
telegram_bot.py — Telegram Bot polling + 슬래시 명령 처리

dipeen API와 Telegram 그룹을 연결하는 브릿지.
환경변수 없으면 자동 종료 (no-op).

지원 명령:
  /status         — 현재 방 칸반 현황 텍스트 보고
  /agents         — 온라인 에이전트 목록
  /assign <설명>  — FE/BE/QA 결정 없이 태스크 즉시 생성
  /cancel T-xxxx  — 실행 중 태스크 취소

사용법:
  python telegram_bot.py               # standalone
  # 또는 pm_loop와 같이 실행:
  asyncio.create_task(telegram_bot_loop())
"""

import asyncio
import json
import os
import sys

import httpx

API_URL  = os.getenv("API_URL", "http://localhost:8000")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")
ROOM_ID   = os.getenv("TELEGRAM_ROOM_ID", "general")

TG_BASE  = f"https://api.telegram.org/bot{BOT_TOKEN}"

_last_update_id = 0


# ── Telegram API helpers ──────────────────────────────────────────

async def _tg_get(client: httpx.AsyncClient, method: str, **params) -> dict:
    r = await client.get(f"{TG_BASE}/{method}", params=params, timeout=15)
    r.raise_for_status()
    return r.json()


async def _tg_post(client: httpx.AsyncClient, method: str, **body) -> dict:
    r = await client.post(f"{TG_BASE}/{method}", json=body, timeout=10)
    r.raise_for_status()
    return r.json()


async def _reply(client: httpx.AsyncClient, chat_id: int | str, text: str) -> None:
    try:
        await _tg_post(client, "sendMessage",
                       chat_id=chat_id, text=text, parse_mode="HTML")
    except Exception as e:
        print(f"[TG] reply error: {e}", flush=True)


# ── dipeen API helpers ────────────────────────────────────────────

async def _api_get(client: httpx.AsyncClient, path: str, **params) -> dict | list:
    r = await client.get(f"{API_URL}{path}", params=params, timeout=10)
    r.raise_for_status()
    return r.json()


async def _api_post(client: httpx.AsyncClient, path: str, body: dict) -> dict:
    r = await client.post(f"{API_URL}{path}", json=body, timeout=10)
    r.raise_for_status()
    return r.json()


# ── 명령 핸들러 ───────────────────────────────────────────────────

async def cmd_status(client: httpx.AsyncClient, chat_id: int | str) -> None:
    """/status — 칸반 현황"""
    tasks = await _api_get(client, "/api/tasks")
    if not isinstance(tasks, list):
        await _reply(client, chat_id, "❌ 태스크 목록 조회 실패")
        return

    groups: dict[str, list] = {
        "pending": [], "in_progress": [], "done": [], "error": []
    }
    for t in tasks:
        s = t.get("status", "pending")
        key = s if s in groups else "error"
        groups[key].append(t)

    lines = ["<b>📋 Board Status</b>"]
    icons = {"pending": "⏳", "in_progress": "🔵", "done": "✅", "error": "❌"}
    for status, icon in icons.items():
        items = groups[status]
        if items:
            lines.append(f"\n{icon} <b>{status.upper()}</b> ({len(items)})")
            for t in items[:5]:
                tid = t.get("task_id", "")[:10]
                subj = t.get("subject", "")[:40]
                lines.append(f"  <code>{tid}</code> {subj}")
            if len(items) > 5:
                lines.append(f"  ... +{len(items)-5}개")

    await _reply(client, chat_id, "\n".join(lines))


async def cmd_agents(client: httpx.AsyncClient, chat_id: int | str) -> None:
    """/agents — 에이전트 목록"""
    agents = await _api_get(client, "/api/agents")
    if not isinstance(agents, list):
        await _reply(client, chat_id, "❌ 에이전트 조회 실패")
        return

    if not agents:
        await _reply(client, chat_id, "등록된 에이전트 없음")
        return

    lines = ["<b>🤖 Agents</b>"]
    for a in agents:
        aid   = a.get("agent_id", "?")
        role  = a.get("role") or "?"
        status = a.get("status", "offline")
        task_id = a.get("current_task_id") or "—"
        icon = "🟢" if status == "working" else "🔵" if status == "idle" else "⚫"
        lines.append(f"{icon} <b>{aid}</b> [{role}] — {status}"
                     + (f"\n  ↳ {task_id}" if status == "working" else ""))

    await _reply(client, chat_id, "\n".join(lines))


async def cmd_assign(
    client: httpx.AsyncClient,
    chat_id: int | str,
    sender: str,
    args: str,
) -> None:
    """/assign <설명> — 태스크 생성"""
    subject = args.strip()
    if not subject:
        await _reply(client, chat_id, "사용법: <code>/assign 태스크 설명</code>")
        return

    task = await _api_post(client, "/api/tasks", {"subject": subject, "prompt": subject})
    task_id = task.get("task_id", "?")

    # 채팅방에도 동기화
    await _api_post(client, "/api/chat/messages", {
        "room_id": ROOM_ID,
        "text": f"[Telegram] {sender}: /assign {subject}",
        "sender": "telegram",
        "sender_type": "user",
    })

    await _reply(client, chat_id,
                 f"✅ 태스크 생성: <code>{task_id}</code>\n{subject}")


async def cmd_cancel(
    client: httpx.AsyncClient,
    chat_id: int | str,
    task_id_arg: str,
) -> None:
    """/cancel T-xxxx — 태스크 취소"""
    task_id = task_id_arg.strip()
    if not task_id.startswith("T-"):
        await _reply(client, chat_id,
                     "사용법: <code>/cancel T-xxxxxxxx</code>")
        return

    try:
        await _api_post(client, f"/api/tasks/{task_id}/cancel", {})
        await _reply(client, chat_id, f"🚫 취소됨: <code>{task_id}</code>")
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            await _reply(client, chat_id, f"❌ 태스크 없음: <code>{task_id}</code>")
        elif e.response.status_code == 400:
            await _reply(client, chat_id,
                         f"❌ 취소 불가 (이미 {e.response.json().get('detail', '종료')})")
        else:
            await _reply(client, chat_id, f"❌ 오류: {e.response.status_code}")


# ── 메시지 라우터 ─────────────────────────────────────────────────

async def handle_message(client: httpx.AsyncClient, msg: dict) -> None:
    chat_id = msg.get("chat", {}).get("id")
    text    = (msg.get("text") or "").strip()
    sender  = msg.get("from", {}).get("username") or msg.get("from", {}).get("first_name", "unknown")

    if not text or not chat_id:
        return

    # 슬래시 명령
    if text.startswith("/"):
        parts = text.split(maxsplit=1)
        cmd   = parts[0].lower().split("@")[0]  # "/cmd@botname" 처리
        args  = parts[1] if len(parts) > 1 else ""

        try:
            if cmd == "/status":
                await cmd_status(client, chat_id)
            elif cmd == "/agents":
                await cmd_agents(client, chat_id)
            elif cmd == "/assign":
                await cmd_assign(client, chat_id, sender, args)
            elif cmd == "/cancel":
                await cmd_cancel(client, chat_id, args)
            elif cmd == "/start" or cmd == "/help":
                await _reply(client, chat_id,
                    "<b>dipeen Telegram Bridge</b>\n\n"
                    "/status — 칸반 현황\n"
                    "/agents — 에이전트 목록\n"
                    "/assign &lt;설명&gt; — 태스크 생성\n"
                    "/cancel T-xxxx — 태스크 취소"
                )
        except Exception as e:
            await _reply(client, chat_id, f"❌ 명령 오류: {e}")
        return

    # 일반 메시지 → 채팅방으로 브릿지
    if CHAT_ID and str(chat_id) == CHAT_ID:
        try:
            await _api_post(client, "/api/chat/messages", {
                "room_id": ROOM_ID,
                "text": f"[Telegram:{sender}] {text}",
                "sender": f"tg:{sender}",
                "sender_type": "user",
            })
        except Exception as e:
            print(f"[TG] bridge error: {e}", flush=True)


# ── 폴링 루프 ─────────────────────────────────────────────────────

async def telegram_bot_loop() -> None:
    """Telegram 폴링 루프. TOKEN/CHAT_ID 없으면 즉시 반환."""
    global _last_update_id
    if not BOT_TOKEN:
        print("[TG Bot] TELEGRAM_BOT_TOKEN not set -- disabled", flush=True)
        return
    if not CHAT_ID:
        print("[TG Bot] TELEGRAM_CHAT_ID not set -- disabled", flush=True)
        return

    print(f"[TG Bot] 폴링 시작 (chat_id={CHAT_ID})", flush=True)

    async with httpx.AsyncClient(timeout=35) as client:
        # 시작 시 offset 초기화 (이전 메시지 스킵)
        try:
            data = await _tg_get(client, "getUpdates", offset=-1, limit=1)
            updates = data.get("result", [])
            if updates:
                _last_update_id = updates[-1]["update_id"] + 1
        except Exception:
            pass

        while True:
            try:
                data = await _tg_get(
                    client, "getUpdates",
                    offset=_last_update_id, timeout=30, allowed_updates='["message"]'
                )
                for update in data.get("result", []):
                    _last_update_id = update["update_id"] + 1
                    msg = update.get("message")
                    if msg:
                        asyncio.create_task(handle_message(client, msg))
            except (httpx.ConnectError, httpx.TimeoutException):
                await asyncio.sleep(5)
            except Exception as e:
                print(f"[TG Bot] 오류: {e}", flush=True)
                await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(telegram_bot_loop())
