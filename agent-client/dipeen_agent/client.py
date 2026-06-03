"""AgentClient — API 서버와 통신하는 HTTP 클라이언트 (재시도 포함)."""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

import httpx
import websockets

from dipeen_agent.config import API_URL, AGENT_ID, AGENT_ROLE, LLM_PROVIDER, AGENT_PERSONAS, DIPEEN_TOKEN

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

# J-4: HTTP 에러 분류 (claw-code-main/not-claude-code-emulator 패턴)
class _RateLimitError(Exception):
    """429 — 지수 백오프 후 재시도."""

class _RetryableError(Exception):
    """5xx / 503 — 잠시 후 재시도."""

class _NonRetryableError(Exception):
    """4xx (non-429) — 재시도 불가, FALLBACK_CHAIN 다음 provider로 이동."""

CHAT_ROOM_ID = os.environ.get("DIPEEN_CHAT_ROOM", "general")

# K-1: 역할 전체 이름 → 약어 (채팅 색상 결정에 사용)
_ROLE_TO_SHORT: dict[str, str] = {
    "frontend engineer": "FE",
    "fe engineer": "FE",
    "fe": "FE",
    "backend engineer": "BE",
    "be engineer": "BE",
    "be": "BE",
    "qa engineer": "QA",
    "quality assurance": "QA",
    "qa": "QA",
    "project manager": "PM",
    "product manager": "PM",
    "pm": "PM",
}


class AgentClient:
    def __init__(
        self,
        api_url: str = API_URL,
        agent_id: str = AGENT_ID,
        agent_role: str = AGENT_ROLE,
    ):
        self.api_url = api_url.rstrip("/")
        self.agent_id = agent_id
        self.agent_role = agent_role
        headers = {}
        if DIPEEN_TOKEN:
            headers["Authorization"] = f"Bearer {DIPEEN_TOKEN}"
        self._http = httpx.AsyncClient(base_url=self.api_url, timeout=60.0, headers=headers)

    async def _retry(self, coro_fn, retries: int = MAX_RETRIES):
        """J-4: HTTP 에러 분류 기반 재시도 래퍼."""
        for attempt in range(retries):
            try:
                return await coro_fn()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status == 429:
                    # RateLimitError — 지수 백오프
                    wait = RETRY_DELAY * (2 ** attempt)
                    print(f"[agent] 429 rate limit, {wait}s 대기 후 재시도 ({attempt+1}/{retries})", flush=True)
                    if attempt == retries - 1:
                        raise
                    await asyncio.sleep(wait)
                elif status >= 500 or status == 503:
                    # RetryableError
                    if attempt == retries - 1:
                        raise
                    print(f"[agent] {status} 서버 오류, 재시도 ({attempt+1}/{retries})", flush=True)
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                else:
                    # NonRetryableError (4xx non-429) — 즉시 raise
                    raise
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                if attempt == retries - 1:
                    print(f"[agent] API 호출 실패 ({retries}회 시도): {e}", flush=True)
                    raise
                print(f"[agent] API 재시도 ({attempt + 1}/{retries}): {e}", flush=True)
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))

    async def register(self) -> dict:
        """에이전트 등록 (서버 시작 시 1회)."""
        async def _call():
            r = await self._http.post("/api/agents", json={
                "agent_id": self.agent_id,
                "role": self.agent_role,
            })
            r.raise_for_status()
            return r.json()
        return await self._retry(_call)

    async def heartbeat(self, status: str, current_task_id: str | None = None) -> None:
        """heartbeat 갱신. 실패 시 silent (비핵심 경로)."""
        try:
            await self._http.post(f"/api/agents/{self.agent_id}/heartbeat", json={
                "status": status,
                "current_task_id": current_task_id,
            })
        except (httpx.ConnectError, httpx.TimeoutException):
            pass  # heartbeat 실패는 치명적이지 않음

    async def poll_task(self) -> dict | None:
        """다음 태스크 가져오기 (long-polling, 최대 30초 대기)."""
        async def _call():
            r = await self._http.get(
                f"/api/agents/{self.agent_id}/poll",
                params={"room_id": CHAT_ROOM_ID},
                timeout=45.0,
            )
            r.raise_for_status()
            data = r.json()
            if data.get("task_id") is None:
                return None
            return data
        return await self._retry(_call)

    async def register_worker(self, capabilities: list[str], workspaces: list | None = None) -> dict:
        """NAT Product Alpha worker 등록. legacy /api/agents 등록과 별개인 실행 노드 계약.
        workspaces[].local_path는 worker-local — HQ는 workspace_ref만 알고 로컬 경로엔 의존 안 함."""
        async def _call():
            r = await self._http.post("/api/workers", json={
                "worker_id": self.agent_id,
                "capabilities": capabilities,
                "workspaces": workspaces or [],
            })
            r.raise_for_status()
            return r.json()
        return await self._retry(_call)

    async def worker_heartbeat(self) -> dict:
        async def _call():
            r = await self._http.post(f"/api/workers/{self.agent_id}/heartbeat")
            r.raise_for_status()
            return r.json()
        return await self._retry(_call)

    async def poll_worker_command(self, capabilities: list[str]) -> dict | None:
        """NAT command queue에서 실행 command를 pull한다. 없으면 None."""
        async def _call():
            r = await self._http.post(
                f"/api/workers/{self.agent_id}/commands/poll",
                json={"capabilities": capabilities},
                timeout=45.0,
            )
            r.raise_for_status()
            return r.json().get("command")
        return await self._retry(_call)

    async def submit_worker_result(self, command_id: str, result: dict, artifacts: dict | None = None) -> dict:
        """NAT Worker 결과 업로드. Dipeen Core가 ingest/reconcile하고 command를 completed 처리한다."""
        artifacts = artifacts or result.get("artifacts") or {}
        async def _call():
            r = await self._http.post(
                f"/api/workers/{self.agent_id}/commands/{command_id}/result",
                json={
                    "status": result.get("status", "failed"),
                    "summary": result.get("summary", ""),
                    "changed_files": artifacts.get("changed_files") or artifacts.get("scope_diff") or [],
                    "tests_passed": bool(result.get("tests_passed") or artifacts.get("tests_passed")),
                    "pr_url": artifacts.get("pr_url"),
                    "key_decisions": artifacts.get("key_decisions") or [],
                    "runner": artifacts.get("runner"),
                },
            )
            r.raise_for_status()
            return r.json()
        return await self._retry(_call)

    async def send_chat(
        self,
        text: str,
        room_id: str = "general",
        task_id: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """K-1/K-2/W-2: 채팅방에 에이전트 활동 메시지 전송. 실패 시 silent."""
        short_role = _ROLE_TO_SHORT.get(self.agent_role.lower(), self.agent_role)
        label = f"{short_role} Agent"
        sender_type = "question" if (task_id and not metadata) else "agent"
        body: dict = {
            "room_id": room_id,
            "sender": label,
            "sender_type": sender_type,
            "role": short_role,
            "text": text,
        }
        if task_id:
            body["task_id"] = task_id
        if metadata:
            body["metadata_json"] = metadata
        try:
            await self._http.post("/api/chat/messages", json=body, timeout=5.0)
        except Exception:
            pass

    async def check_cancelled(self, task_id: str) -> bool:
        """태스크가 취소됐는지 확인."""
        r = await self._http.get(f"/api/tasks/{task_id}")
        r.raise_for_status()
        return r.json().get("status") == "cancelled"

    async def report(self, task_id: str, status: str, pr_url: str | None = None,
                     tests_passed: bool = False, summary: str = "",
                     usage: dict | None = None,
                     artifacts: dict | None = None) -> None:
        """태스크 완료 보고 (재시도 포함 — 보고 누락 방지)."""
        async def _call():
            r = await self._http.post(f"/api/agents/{self.agent_id}/report", json={
                "task_id": task_id,
                "status": status,
                "pr_url": pr_url,
                "tests_passed": tests_passed,
                "summary": summary,
                "usage": usage or {},
                "artifacts": artifacts,
            })
            r.raise_for_status()
        await self._retry(_call)

    async def register_capability(self) -> dict:
        """C-1 + F-1: 시작 시 로컬 MCP/skills 스캔 + LLM 페르소나 선언 → PATCH /capability 등록."""
        skills = self._scan_skills()
        mcps = self._scan_mcps()
        model = os.environ.get("AGENT_MODEL", "claude-sonnet-4-6")
        async def _call():
            r = await self._http.patch(
                f"/api/agents/{self.agent_id}/capability",
                json={
                    "skills": skills,
                    "mcps": mcps,
                    "model": model,
                    "max_concurrent": 1,
                    "llm_provider": LLM_PROVIDER,
                    "personas": AGENT_PERSONAS,
                },
            )
            r.raise_for_status()
            return r.json()
        result = await self._retry(_call)
        print(
            f"[agent] capability 등록: provider={LLM_PROVIDER}, "
            f"personas={AGENT_PERSONAS}, skills={skills}, mcps={mcps}",
            flush=True,
        )
        return result

    def _scan_skills(self) -> list[str]:
        """AGENT_SKILLS 환경변수 또는 SOUL.md에서 스킬 목록 읽기."""
        env_skills = os.environ.get("AGENT_SKILLS", "")
        if env_skills:
            return [s.strip() for s in env_skills.split(",") if s.strip()]
        # SOUL.md fallback (workspace 루트)
        soul_path = Path(os.environ.get("DIPEEN_WORKSPACE", ".")) / "SOUL.md"
        if soul_path.exists():
            content = soul_path.read_text(encoding="utf-8")
            for line in content.splitlines():
                if line.startswith("skills:") or line.startswith("Skills:"):
                    raw = line.split(":", 1)[1].strip()
                    return [s.strip() for s in raw.split(",") if s.strip()]
        return []

    def _scan_mcps(self) -> list[str]:
        """AGENT_MCPS 환경변수 또는 opencode config에서 MCP 목록 읽기."""
        env_mcps = os.environ.get("AGENT_MCPS", "")
        if env_mcps:
            return [m.strip() for m in env_mcps.split(",") if m.strip()]
        # ~/.config/opencode/config.json fallback
        config_path = Path.home() / ".config" / "opencode" / "config.json"
        if config_path.exists():
            try:
                data = json.loads(config_path.read_text(encoding="utf-8"))
                mcps = data.get("mcp", data.get("mcps", {}))
                if isinstance(mcps, dict):
                    return list(mcps.keys())
                if isinstance(mcps, list):
                    return mcps
            except (json.JSONDecodeError, KeyError):
                pass
        return []

    async def send_message(
        self,
        content: str,
        to_agent_id: str | None = None,
        task_id: str | None = None,
        message_type: str = "message",
        reply_to: str | None = None,
    ) -> dict:
        """C-5: 다른 에이전트에게 메시지 전송 (A2A)."""
        async def _call():
            r = await self._http.post(f"/api/agents/{self.agent_id}/message", json={
                "to_agent_id": to_agent_id,
                "task_id": task_id,
                "message_type": message_type,
                "content": content,
                "reply_to": reply_to,
            })
            r.raise_for_status()
            return r.json()
        return await self._retry(_call)

    async def search_agents(self, role: str | None = None, status: str | None = None) -> list:
        """다른 에이전트 검색 (역할/상태 기반)."""
        params = {}
        if role:
            params["role"] = role
        if status:
            params["status"] = status
        r = await self._http.get("/api/agents/search/by-role", params=params)
        r.raise_for_status()
        return r.json()

    async def create_subtask(self, subject: str, prompt: str,
                             parent_task_id: str, blocked_by: str | None = None) -> dict:
        """서브태스크 생성 (에이전트 간 태스크 위임)."""
        async def _call():
            r = await self._http.post("/api/tasks", json={
                "subject": subject,
                "prompt": prompt,
                "parent_task_id": parent_task_id,
                "blocked_by": blocked_by,
                "created_by_agent": self.agent_id,
            })
            r.raise_for_status()
            return r.json()
        return await self._retry(_call)

    async def close(self) -> None:
        await self._http.aclose()

    async def send_log(self, text: str, level: str = "info", task_id: str | None = None, 
                       changed_files: list[str] | None = None, tests: dict | None = None):
        """Hermes WSS를 통해 구조화된 로그 전송."""
        if hasattr(self, '_hermes_ws') and self._hermes_ws:
            log_frame = {
                "v": 1,
                "type": "LOG_STREAM",
                "team_id": "default-team",
                "agent_id": self.agent_id,
                "task_id": task_id,
                "payload": {
                    "level": level,
                    "text": text,
                    "changed_files": changed_files or [],
                    "tests": tests or {},
                    "ts": datetime.utcnow().isoformat() + "Z"
                }
            }
            try:
                await self._hermes_ws.send(json.dumps(log_frame))
            except Exception:
                pass # 로그 전송 실패는 치명적이지 않음

    async def connect_hermes(self, on_message=None):
        """Hermes WSS 연결 및 메시지 루프 시작."""
        # http -> ws, https -> wss
        ws_url = self.api_url.replace("http", "ws") + "/ws/hermes/agent"
        # TODO: team_id를 동적으로 관리하거나 config에서 가져오기
        team_id = "default-team"
        ws_url += f"?agent_id={self.agent_id}&team_id={team_id}"
        
        print(f"[hermes] WSS 연결 시도: {ws_url}", flush=True)
        
        while True:
            try:
                async with websockets.connect(ws_url) as websocket:
                    self._hermes_ws = websocket
                    print(f"[hermes] 연결 성공", flush=True)
                    # NODE_HELLO 전송
                    hello = {
                        "v": 1,
                        "type": "NODE_HELLO",
                        "team_id": team_id,
                        "agent_id": self.agent_id,
                        "payload": {
                            "role": self.agent_role,
                            "llm_provider": LLM_PROVIDER,
                            "model": os.environ.get("AGENT_MODEL", "claude-sonnet-4-6")
                        }
                    }
                    await websocket.send(json.dumps(hello))
                    
                    async for message in websocket:
                        try:
                            data = json.loads(message)
                            envelope = data # In a real system, validate with Pydantic
                            
                            if on_message:
                                if asyncio.iscoroutinefunction(on_message):
                                    await on_message(envelope)
                                else:
                                    on_message(envelope)
                                    
                        except Exception as e:
                            print(f"[hermes] 메시지 처리 오류: {e}", flush=True)
                            
            except (websockets.ConnectionClosed, Exception) as e:
                self._hermes_ws = None
                print(f"[hermes] 연결 끊김 또는 오류, 10초 후 재시도: {e}", flush=True)
                await asyncio.sleep(10)
