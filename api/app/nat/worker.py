"""WorkerNode (M6+M7 / Worker 측 — 현장 노드) — register/poll/lease/실행/업로드.

run.start: Core가 enqueue한 command를 *pull*해 worker_execute(provider 실행 + 로컬 NAT 번역)로 처리,
결과를 ingest로 업로드. **Worker도 최종 TaskState를 결정하지 않는다**(complete ≠ task done).
permission.execute(M7): 승인된 privileged action을 LocalPermissionGuard 재확인 후 ExecutorPlugin으로 *로컬* 실행,
Receipt artifact를 ingest. **Core는 절대 실행하지 않는다.**

두 평면: 이 코드는 *빌드타임* 구현물. 런타임엔 각 PC의 dipeen worker 프로세스가 provider CLI/로컬 credential을
*격리* 사용한다 — 그 실행기는 개발자(나)도 Dipeen Core도 아닌, 신뢰하지 않는 격리 대상이다.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from .adapters.base import CommandRunner
from .contracts import (
    AgentBinding, AgentIdentity, Command, Event, NormalizedAgentResult, WorkerInfo, WorkerWorkspace,
)
from .core.command_queue import CommandQueue
from .core.ingest import ingest_result
from .core.permission_ledger import PermissionLedger
from .core.pipeline import worker_execute
from .core.reconciler import ReconcileResult
from .core.routing import resolve_workspace
from .core.run_store import RunStore
from .core.worker_registry import WorkerRegistry
from .executors import ExecutorMode, ExecutorPlugin, compute_permission_receipt, default_executor_mode


class WorkerNode:
    def __init__(self, worker_id: str, *, capabilities: list[str], queue: CommandQueue,
                 registry: WorkerRegistry, store_root: str, timeout_sec: Optional[int] = None,
                 executors: Optional[dict[str, ExecutorPlugin]] = None,
                 executor_mode: Optional[ExecutorMode] = None,
                 workspaces: Optional[list[WorkerWorkspace]] = None):
        self.worker_id = worker_id
        self.capabilities = list(capabilities)
        self.queue = queue
        self.registry = registry
        self.store_root = store_root
        self.timeout_sec = timeout_sec               # provider 실행 타임아웃(실측 행 방지)
        self.executors: dict[str, ExecutorPlugin] = executors or {}   # action → 로컬 executor
        # 기본 dry_run(안전): 승인만으로 진짜 side effect 금지. local_execute는 명시적으로 켜야.
        self.executor_mode: ExecutorMode = executor_mode or default_executor_mode()
        self.workspaces: list[WorkerWorkspace] = workspaces or []   # workspace_ref → 내 local_path

    def register(self) -> WorkerInfo:
        return self.registry.register(WorkerInfo(worker_id=self.worker_id, capabilities=self.capabilities,
                                                 workspaces=self.workspaces))

    def heartbeat(self) -> Optional[WorkerInfo]:
        return self.registry.heartbeat(self.worker_id)

    def apply_probe_capability(self, provider: str, stdout: str, stderr: str, exit_code: int) -> bool:
        """Provider Lifecycle: probe healthy일 때만 provider.X capability를 advertise(registry 재등록).

        probe 실패(예: omo bun ENOENT)면 worker는 online 유지하되 provider.X를 광고하지 않는다 →
        해당 provider task가 이 worker로 라우팅되지 않음. 설치/탐지만으론 광고 안 함(Evidence First) —
        live probe 결과만 capability를 켠다. 반환=healthy 여부."""
        from .providers.lifecycle import advertised_capability, is_probe_healthy
        healthy = is_probe_healthy(provider, stdout, stderr, exit_code)
        cap = advertised_capability(provider, healthy=healthy)
        if cap and cap not in self.capabilities:
            self.capabilities.append(cap)
            self.register()                          # 새 capability로 재등록 = 광고
        return healthy

    async def poll_and_run_once(self, *, runner: Optional[CommandRunner] = None,
                                bypass: bool = False) -> Optional[ReconcileResult]:
        """queued command 1개를 lease해 type별 처리. 할 일 없으면 None."""
        cmd = self.queue.poll(self.worker_id, self.capabilities)
        if cmd is None:
            return None
        if cmd.command_type == "provider.probe":
            return self._execute_probe(cmd)
        if cmd.command_type == "permission.execute":
            return self._execute_permission(cmd)
        return await self._execute_run(cmd, runner=runner, bypass=bypass)

    async def drain(self, *, runner: Optional[CommandRunner] = None, bypass: bool = False,
                    max_commands: int = 100) -> list[ReconcileResult]:
        """처리 가능한 command가 없을 때까지 연속 처리(한 사이클). 반환=결과 리스트."""
        out: list[ReconcileResult] = []
        for _ in range(max_commands):
            r = await self.poll_and_run_once(runner=runner, bypass=bypass)
            if r is None:
                break
            out.append(r)
        return out

    async def run_loop(self, *, runner: Optional[CommandRunner] = None, bypass: bool = False,
                       idle_sleep: float = 2.0, max_iterations: Optional[int] = None) -> None:
        """장기 실행(CLI `dipeen worker`) — heartbeat + drain + idle sleep 반복. agent-client 후신.
        max_iterations=None이면 무한(실제 worker). 테스트는 유한 반복."""
        i = 0
        while max_iterations is None or i < max_iterations:
            self.heartbeat()
            if not await self.drain(runner=runner, bypass=bypass):
                await asyncio.sleep(idle_sleep)
            i += 1

    async def _execute_run(self, cmd: Command, *, runner, bypass) -> Optional[ReconcileResult]:
        self.queue.ack(cmd.command_id, self.worker_id)
        if cmd.task is None:
            self.queue.fail(cmd.command_id)
            return None
        identity = AgentIdentity(identity_id=f"agent://team/{cmd.provider}", role=cmd.provider,
                                 binding=AgentBinding(adapter=cmd.provider))
        try:
            _, _, normalized = await worker_execute(
                cmd.task, identity, run_id=cmd.run_id, workspace_root=resolve_workspace(cmd, self.workspaces),
                runner=runner, bypass=bypass, timeout_sec=self.timeout_sec, worker_id=self.worker_id)
        except Exception:
            self.queue.fail(cmd.command_id)
            raise
        result = ingest_result(cmd.task, run_id=cmd.run_id, normalized=normalized, store_root=self.store_root)
        self.queue.complete(cmd.command_id)
        return result

    def _execute_permission(self, cmd: Command) -> Optional[ReconcileResult]:
        """승인된 privileged action을 로컬 guard 재확인 후 executor_mode대로 처리 → Receipt artifact ingest.
        **기본 dry_run**: 승인만으로 진짜 side effect 안 일으킴(would_execute 미리보기). local_execute만 실제 실행.
        receipt 계산은 WorkerHttpClient와 공유(compute_permission_receipt) — 로컬/원격 동일 의미."""
        self.queue.ack(cmd.command_id, self.worker_id)
        action = cmd.payload.get("action", "")
        receipt, executed = compute_permission_receipt(
            cmd, executor_mode=self.executor_mode, executors=self.executors, worker_id=self.worker_id)
        events = [Event(event_type="permission.executed", task_id=cmd.task_id, run_id=cmd.run_id,
                        producer=f"dipeen://worker/{self.worker_id}", message=f"{action} ({self.executor_mode})",
                        payload={"permission_id": cmd.permission_id, "mode": self.executor_mode, "executed": executed})]
        task = RunStore(self.store_root).load_task(cmd.task_id)
        result = (ingest_result(task, run_id=cmd.run_id,
                                normalized=NormalizedAgentResult(artifacts=[receipt], events=events),
                                store_root=self.store_root) if task else None)
        if cmd.permission_id:                                    # ledger 갱신
            led = PermissionLedger(self.store_root)
            req = led.get(cmd.permission_id)
            if req:
                req.state = "executed" if executed else "approved"
                led.save(req)
        self.queue.complete(cmd.command_id)
        return result

    def _execute_probe(self, cmd: Command) -> None:
        """provider read-only probe(M11b) — payload의 argv를 generic 실행 → task-less provider.probed Event.
        worker는 provider를 모르고 argv만 실행한다(불가지론). 실패(bun ENOENT 등)도 정직하게 event로 기록."""
        import shutil
        import subprocess
        from .core.eventlog import EventLog
        self.queue.ack(cmd.command_id, self.worker_id)
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
        # Provider Lifecycle: healthy면 provider.X advertise(이미 보유 시 no-op). 실패면 미광고·online 유지.
        healthy = self.apply_probe_capability(cmd.provider, out, err, rc)
        ev = Event(event_type="provider.probed", task_id=None, run_id=None,
                   producer=f"dipeen://worker/{self.worker_id}",
                   message=f"probe {cmd.provider} (exit={rc})",
                   payload={"provider": cmd.provider, "argv": argv, "exit": rc,
                            "stdout": out[:4000], "stderr": err[:2000],
                            "healthy": healthy,
                            "capability_advertised": f"provider.{cmd.provider}" in self.capabilities})
        EventLog(self.store_root).append(ev)
        self.queue.complete(cmd.command_id)
        return None
