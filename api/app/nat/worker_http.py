"""WorkerHttpClient (M10a / Worker 측) — control_plane HTTP 엔드포인트로 붙는 *원격* worker.

M6 WorkerNode는 파일 store를 직접 본다(로컬). 이건 Core를 네트워크 너머에서 쓰는 worker:
register → poll → (로컬 provider 실행) → result POST. Core(control_plane router)가 reconcile.
**Core는 실행하지 않는다** — worker가 자기 PC에서 provider를 돌리고 결과만 올린다(BYOK, 방화벽 뒤 OK).

http(httpx.AsyncClient)는 주입 — 테스트는 ASGI client, 실제는 base_url 가진 client. runner 주입으로 hermetic.
"""
from __future__ import annotations

from typing import Any, Optional

from .adapters.base import CommandRunner
from .contracts import AgentBinding, AgentIdentity, Command, WorkerWorkspace
from .core import outbound
from .core.pipeline import _adapter_for
from .core.routing import resolve_workspace
from .executors import (ExecutorMode, ExecutorPlugin, compute_permission_receipt,
                        default_executor_mode)


class WorkerHttpClient:
    def __init__(self, worker_id: str, capabilities: list[str], *, http: Any,
                 runner: Optional[CommandRunner] = None, bypass: bool = False,
                 timeout_sec: Optional[int] = None,
                 executor_mode: Optional[ExecutorMode] = None,
                 executors: Optional[dict[str, ExecutorPlugin]] = None,
                 workspaces: Optional[list[WorkerWorkspace]] = None):
        self.worker_id = worker_id
        self.capabilities = list(capabilities)
        self.http = http                              # httpx.AsyncClient (주입)
        self.runner = runner
        self.bypass = bypass
        self.timeout_sec = timeout_sec
        # 기본 dry_run(안전): 승인된 permission.execute도 진짜 side effect 안 일으킴. local_execute만 실제.
        self.executor_mode: ExecutorMode = executor_mode or default_executor_mode()
        self.executors: dict[str, ExecutorPlugin] = executors or {}
        self.workspaces: list[WorkerWorkspace] = workspaces or []   # workspace_ref → 내 local_path
        self.worker_token: Optional[str] = None      # register가 받은 worker-scoped JWT
        self._lease_id: Optional[str] = None          # 최근 poll lease (result에 전달)

    async def register(self) -> dict:
        r = await self.http.post("/api/workers",
                                 json={"worker_id": self.worker_id, "capabilities": self.capabilities,
                                       "workspaces": [w.model_dump(mode="json") for w in self.workspaces]})
        r.raise_for_status()
        data = r.json()
        # 서버가 canonical worker_id + worker_token 발급 → 이후 path/auth에 사용
        self.worker_id = data.get("worker_id") or self.worker_id
        token = data.get("worker_token")
        if token:
            self.worker_token = token
            try:
                self.http.headers["Authorization"] = f"Bearer {token}"
            except Exception:  # noqa: BLE001 — 주입 client가 headers 미지원이어도 무해
                pass
        return data

    async def heartbeat(self) -> None:
        await self.http.post(f"/api/workers/{self.worker_id}/heartbeat")

    async def poll_once(self) -> bool:
        """command 1개를 poll → 로컬 실행 → result POST. 처리했으면 True, 없으면 False."""
        r = await self.http.post(f"/api/workers/{self.worker_id}/commands/poll",
                                 json={"capabilities": self.capabilities})
        r.raise_for_status()
        payload = r.json()
        data = payload.get("command")
        if not data:
            return False
        self._lease_id = payload.get("lease_id")
        cmd = Command.model_validate(data)
        await self.http.post(f"/api/workers/{self.worker_id}/commands/{cmd.command_id}/ack")
        if cmd.command_type == "provider.probe":          # read-only 진단(M11b) — run 아님
            return await self._execute_probe(cmd)
        if cmd.command_type == "permission.execute":      # 승인된 privileged action — run 아님
            return await self._execute_permission(cmd)
        try:
            status, changed, summary = await self._execute_local(cmd)
        except Exception as exc:                      # 실패도 정직하게 보고(완료 조작 금지)
            await self.http.post(f"/api/workers/{self.worker_id}/commands/{cmd.command_id}/fail")
            await self.http.post(
                f"/api/workers/{self.worker_id}/commands/{cmd.command_id}/result",
                json={"status": "error", "summary": str(exc)[:200], "changed_files": []})
            return True
        await self.http.post(
            f"/api/workers/{self.worker_id}/commands/{cmd.command_id}/result",
            json={"status": status, "summary": summary, "changed_files": changed, "runner": cmd.provider,
                  "lease_id": self._lease_id})
        return True

    async def _execute_permission(self, cmd: Command) -> bool:
        """승인된 permission.execute를 *로컬* executor_mode대로 처리(기본 dry_run) → receipt를 Core에 POST.
        **Core는 실행하지 않는다** — worker가 자기 PC에서 결정·실행하고 receipt(증거)만 올린다."""
        receipt, executed = compute_permission_receipt(
            cmd, executor_mode=self.executor_mode, executors=self.executors, worker_id=self.worker_id)
        await self.http.post(
            f"/api/workers/{self.worker_id}/commands/{cmd.command_id}/permission-result",
            json={"artifact": receipt.model_dump(mode="json"),
                  "permission_id": cmd.permission_id, "executed": executed})
        return True

    async def _execute_probe(self, cmd: Command) -> bool:
        """provider read-only probe(M11b) — payload argv를 generic 실행 → 결과를 Core에 POST.
        **Core는 실행하지 않는다** — worker가 자기 PC에서 read-only로 돌리고 결과(증거)만 올린다."""
        import shutil
        import subprocess
        argv = list(cmd.payload.get("argv", []))
        if argv and shutil.which(argv[0]):               # Windows: 'omo'→omo.CMD full path resolve
            argv = [shutil.which(argv[0])] + argv[1:]
        try:
            proc = subprocess.run(argv, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", timeout=self.timeout_sec or 15)
            rc, out, err = proc.returncode, proc.stdout or "", proc.stderr or ""
        except subprocess.TimeoutExpired:
            rc, out, err = -1, "", "probe timeout"
        except OSError as e:                              # 바이너리 없음 등도 정직하게
            rc, out, err = -1, "", f"probe exec error: {e}"
        await self.http.post(
            f"/api/workers/{self.worker_id}/commands/{cmd.command_id}/probe-result",
            json={"provider": cmd.provider, "exit": rc, "stdout": out[:4000], "stderr": err[:2000]})
        return True

    async def _execute_local(self, cmd: Command) -> tuple[str, list[str], str]:
        """provider를 *로컬*에서 실행(Core 아님). raw output에서 status/changed_files/summary 추출."""
        identity = AgentIdentity(identity_id=f"agent://team/{cmd.provider}", role=cmd.provider,
                                 binding=AgentBinding(adapter=cmd.provider))
        inv = outbound.build_invocation(cmd.task, identity, run_id=cmd.run_id,
                                        workspace_root=resolve_workspace(cmd, self.workspaces))
        if self.timeout_sec:
            inv = inv.model_copy(update={"timeout_sec": self.timeout_sec})
        adapter = _adapter_for(cmd.provider, self.runner, bypass=self.bypass)
        raw = await adapter.run(inv)
        status = "done" if raw.exit_code == 0 else "error"
        return status, list(raw.changed_files), (raw.stdout or "")[:200]
