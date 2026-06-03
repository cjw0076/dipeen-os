"""RunnerAdapter (W0) — omo / hermes / claude-code를 동일 인터페이스로 통일.

study-guide §7.4: Node는 RunnerAdapter로 러너 하나를 실행해 **동일한 RunReport**를 낸다.
HQ는 RunReport(+artifacts)만 본다 — 러너가 무엇이든. 어댑터 *안*의 루프(Ralph 등)는 자유,
경계·판정·truth는 HQ가 소유한다(`docs/dipeen-wrap-principle.md`).

여긴 agent-client(Node)다 → api의 pydantic을 import하지 않는다. RunReport는
`api/app/schemas/runner.py`의 **필드명에 맞춘 dict**로 만들고, HQ가 pydantic으로 검증한다.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable

RUNNER_NAMES = ("claude-code", "omo-opencode", "omo-codex-light", "hermes")


@dataclass
class RunContext:
    """어댑터 실행 컨텍스트. claude-code 어댑터는 runtime의 기존 subprocess 경로를 재사용한다."""
    workspace: Path
    runtime: Any = None                       # AgentRuntime (duck-typed; 순환 import 회피)
    config: dict = field(default_factory=dict)
    agent_id: str = "unknown"


@dataclass
class RunnerHealth:
    """`dipeen-node doctor`가 보는 러너 상태."""
    name: str
    available: bool
    detail: str = ""
    version: Optional[str] = None

    def line(self) -> str:
        mark = "OK" if self.available else "--"
        v = f" ({self.version})" if self.version else ""
        return f"[{mark}] {self.name}{v}: {self.detail}"


@runtime_checkable
class RunnerAdapter(Protocol):
    """모든 러너가 따르는 계약. execute는 RunReport dict를 낸다(자기보고 — HQ가 판정)."""
    name: str

    async def execute(self, task: dict, ctx: RunContext) -> dict: ...
    async def health(self) -> RunnerHealth: ...


@dataclass
class RunHandle:
    """AgentContract.run이 반환하는 실행 핸들 — status/artifacts/cancel이 참조."""
    task_id: str
    state: str = "PENDING"                 # NAT AgentState: PENDING|RUNNING|BLOCKED|DONE|FAILED
    result: Optional[dict] = None          # 완료 시 RunReport dict
    inner: Any = None                      # 러너별 내부 핸들(asyncio.Task / omo session id 등)


@runtime_checkable
class AgentContract(Protocol):
    """5-메서드 lifecycle 계약 (NAT / docs/nat-layer-design.md §1) — RunnerAdapter(execute/health)의 진화.

    내부 세계관(Claude 직선 / OMO Agent→SubAgent→Loop→Review / Hermes Reflection)은 자유,
    경계·판정·truth는 HQ. run은 비차단(handle 반환). 반환 타입은 dict/str(API pydantic 미import — 디커플).
    Stage1 ClaudeAdapter는 _execute_subprocess를 이 계약 뒤로, Stage2 OmoAdapter는 omo 세션을 *독립* 번역.
    """
    name: str

    async def run(self, task: dict, ctx: RunContext) -> RunHandle: ...
    async def status(self, handle: RunHandle) -> str: ...        # NAT AgentState
    async def artifacts(self, handle: RunHandle) -> list[dict]: ...  # nat.Artifact 필드 dict[]
    async def pause(self, handle: RunHandle) -> None: ...         # 미지원 러너는 no-op
    async def cancel(self, handle: RunHandle) -> None: ...
    async def health(self) -> RunnerHealth: ...


def which(binary: str) -> Optional[str]:
    return shutil.which(binary)


def git_changed_files(workspace: Path) -> list[str]:
    """워크스페이스에서 실제로 만진 경로(git diff --name-only HEAD). scope_diff의 근거."""
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(workspace), capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            return [f.strip() for f in r.stdout.splitlines() if f.strip()]
    except Exception:
        pass
    return []


def run_checks(workspace: Path, config: dict | None = None) -> dict:
    """결정론 검증(R4) — 팀이 config로 명령을 줄 때만 실행. 기본은 검증 없음(빈 dict).

    `config["check_commands"]` 예: {"pytest": "pytest -q", "ruff": "ruff check ."}
    반환: {"pytest": "pass"|"fail", ...}. **기계 실행 결과**(러너 자기보고가 아님) = oracle.
    HQ Gatekeeper가 fail을 보면 DETERMINISTIC_FAIL로 reject한다.
    """
    cmds = (config or {}).get("check_commands") or {}
    out: dict[str, str] = {}
    for name, cmd in cmds.items():
        try:
            r = subprocess.run(
                cmd, cwd=str(workspace), shell=True,
                capture_output=True, text=True, timeout=300,
            )
            out[name] = "pass" if r.returncode == 0 else "fail"
        except Exception:
            out[name] = "fail"
    return out


def _err_result(runner: str, summary: str, blockers: list[str]) -> dict:
    return {
        "status": "error", "summary": summary, "tests_passed": False,
        "artifacts": {"changed_files": [], "completion_promise": None, "blockers": blockers},
        "subtasks": [],
    }


async def run_cli_and_report(cmd: list[str], *, task: dict, ctx: "RunContext",
                             runner: str, timeout: int = 900) -> dict:
    """미니멀 shell-out 실행기 — 신규 어댑터(omo-codex-light/hermes)용.

    claude-code/omo-opencode 어댑터는 runtime의 풍부한 경로(_execute_subprocess: cancel·question·
    PR·promise)를 재사용하므로 이 헬퍼를 쓰지 않는다. 여긴 '명령 실행 → artifacts 추출 → result' 최소본.
    완료 판정은 .dipeen-result.json promise 우선(없으면 rc==0). status/summary/artifacts/subtasks 반환.
    """
    import asyncio
    workspace = ctx.workspace
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=str(workspace),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        try:
            await asyncio.wait_for(proc.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return _err_result(runner, f"{runner} 타임아웃({timeout}s)", [f"{runner} timeout"])
        rc = proc.returncode
    except FileNotFoundError:
        return _err_result(runner, f"{runner} 실행 불가(바이너리 없음)", [f"{runner} 미설치"])
    except Exception as e:  # noqa: BLE001
        return _err_result(runner, f"{runner} 실행 오류: {e}", [str(e)])

    try:
        from dipeen_agent.runtime import extract_artifacts
        artifacts = extract_artifacts(workspace)
    except Exception:
        artifacts = {"changed_files": git_changed_files(workspace), "completion_promise": None}
    promise_done = artifacts.get("completion_promise") == "DONE"
    status = "done" if (rc == 0 or promise_done) else "error"
    return {
        "status": status,
        "summary": f"{task.get('subject', '')} ({runner})",
        "tests_passed": promise_done,
        "artifacts": artifacts,
        "subtasks": artifacts.get("subtasks", []),
    }


def build_run_report(*, task_id: str, agent_id: str, runner: str, status: str,
                     completion_promise: Optional[str] = None,
                     changed_files: Optional[list] = None,
                     scope_diff: Optional[list] = None,
                     key_decisions: Optional[list] = None,
                     blockers: Optional[list] = None,
                     tests_run: Optional[str] = None,
                     duration_ms: Optional[int] = None,
                     trace_id: Optional[str] = None) -> dict:
    """`api/app/schemas/runner.py` RunReport 필드명에 맞춘 dict. HQ가 pydantic으로 검증."""
    changed = list(changed_files or [])
    return {
        "v": 1,
        "task_id": task_id,
        "agent_id": agent_id,
        "runner": runner,
        "status": status,                       # done | error | cancelled
        "completion_promise": completion_promise,  # 자기보고 — 조작 금지, HQ가 판정
        "changed_files": changed,
        "scope_diff": list(scope_diff) if scope_diff is not None else changed,
        "key_decisions": list(key_decisions or []),
        "blockers": list(blockers or []),
        "tests_run": tests_run,
        "duration_ms": duration_ms,
        "trace_id": trace_id,
    }


def finalize_artifacts(artifacts: dict, workspace: Path, *, runner: str,
                       agent_id: str, task: dict, status: str,
                       config: dict | None = None) -> dict:
    """실행 결과 artifacts를 HQ 계약(RunReport)에 맞게 **보강**한다 (W1 솔기 닫기).

    - scope_diff: 없으면 changed_files(실제 만진 경로)로 채움.
    - checks: run_checks 결과(R4) — HQ가 DETERMINISTIC_FAIL 강제에 사용.
    - runner: 어느 러너가 실행했나.
    - run_report: 첫째가는 RunReport dict — HQ가 재구성 없이 소비.
    **completion_promise는 건드리지 않는다** — runtime/llm이 정직하게 채운 값을 그대로(조작 금지).
    """
    artifacts = dict(artifacts or {})
    changed = artifacts.get("changed_files") or git_changed_files(workspace)
    artifacts["changed_files"] = changed
    artifacts.setdefault("scope_diff", list(changed))
    if "checks" not in artifacts:
        artifacts["checks"] = run_checks(workspace, config)
    artifacts["runner"] = runner
    artifacts["run_report"] = build_run_report(
        task_id=task.get("task_id", ""), agent_id=agent_id, runner=runner, status=status,
        completion_promise=artifacts.get("completion_promise"),
        changed_files=changed, scope_diff=artifacts.get("scope_diff"),
        key_decisions=artifacts.get("key_decisions"), blockers=artifacts.get("blockers"),
        trace_id=task.get("trace_id"),
    )
    return artifacts
