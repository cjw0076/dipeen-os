"""Conductor (M6 / Core 측, deterministic FSM — LLM 아님) — task를 run.start command로 dispatch.

Run 생성/영속 후 CommandQueue에 enqueue → Worker가 pull로 가져간다. agent output을 해석하지 않는다
(그건 Verifier/Reconciler). provider 선택은 인자(quality_history 기반 라우팅은 추후).
"""
from __future__ import annotations

from typing import Optional

from ..contracts import Command, Run, TaskEnvelope
from .command_queue import CommandQueue
from .run_store import RunStore


def dispatch_run(queue: CommandQueue, task: TaskEnvelope, *, provider: str, workspace_root: str,
                 store_root: str, required_capabilities: Optional[list[str]] = None,
                 workspace_ref: Optional[str] = None, repo: Optional[str] = None) -> Command:
    """task → Run 생성/영속 → run.start command enqueue. Worker가 capability 맞으면 pull한다.
    workspace_ref(있으면)를 싣어 worker가 자기 local_path로 resolve — HQ는 로컬 경로를 모른다."""
    rs = RunStore(store_root)
    rs.save_task(task)
    run = Run(task_id=task.task_id, identity_id=f"agent://team/{provider}",
              attempt=rs.next_attempt(task.task_id))
    rs.save_run(run)
    caps = required_capabilities or [f"provider.{provider}", "workspace.write"]
    return queue.enqueue(Command(
        command_type="run.start", task_id=task.task_id, run_id=run.run_id, provider=provider,
        task=task, workspace_root=workspace_root, workspace_ref=workspace_ref, repo=repo,
        required_capabilities=caps))


def dispatch_probe(queue: CommandQueue, *, provider: str, argv: list[str]) -> Command:
    """provider read-only probe(doctor/status)를 *task-less* command로 enqueue.

    task/run을 만들지 않는다(probe는 task 라이프사이클 밖). worker는 provider를 모르고 payload의
    argv만 generic 실행한다(Core/worker의 provider 불가지론 유지)."""
    return queue.enqueue(Command(
        command_type="provider.probe", provider=provider,
        required_capabilities=[f"provider.{provider}"],
        payload={"argv": list(argv)}))
