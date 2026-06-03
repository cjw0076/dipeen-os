"""Executors + LocalPermissionGuard (M7 / Worker 측) — 승인된 privileged action을 *로컬*에서 실행.

**Core는 실행하지 않는다.** Worker가 `guard_check`로 정책을 *재확인*(Core 승인을 맹신 안 함)하고,
ExecutorPlugin이 실제 side effect(예: gh pr create)를 일으킨 뒤 Receipt artifact를 남긴다. 미등록 action=Manual Handoff.

두 평면: 실행 주체는 *런타임* worker(로컬 credential 보유) — 개발자(나)도 Dipeen Core도 아닌, 격리된 실행기.
"""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Literal, Optional, Protocol, runtime_checkable

from .core import policy

_ALLOWED_BASE = {"main", "master", "develop"}

# 승인된 action을 worker가 어떻게 처리할지. **기본은 dry_run** — 승인만으로 진짜 side effect를 일으키지 않는다.
# dry_run: would_execute 미리보기(실행 X) / manual_handoff: 사람이 외부 수행 지시 / local_execute: 실제 실행.
ExecutorMode = Literal["dry_run", "manual_handoff", "local_execute"]


def default_executor_mode() -> ExecutorMode:
    """env DIPEEN_PERMISSION_EXECUTOR_MODE. 기본 dry_run(안전) — local_execute는 명시적으로 켜야 함."""
    mode = os.environ.get("DIPEEN_PERMISSION_EXECUTOR_MODE", "dry_run")
    return mode if mode in ("dry_run", "manual_handoff", "local_execute") else "dry_run"


@dataclass
class ExecutorResult:
    success: bool
    uri: str = ""
    message: str = ""


@runtime_checkable
class ExecutorPlugin(Protocol):
    """승인된 action을 로컬에서 실행. 실 구현(GithubPrCreate 등)은 로컬 gh/git 자격증명 사용."""
    def execute(self, action: str, target: Optional[str], payload: dict) -> ExecutorResult: ...


@dataclass
class GitCommitExecutor:
    """git.commit을 워크스페이스에서 *실제* 실행(local_execute). 로컬·가역 side effect — 외부 호출 0.

    staged 변경을 승인된 메시지로 커밋하고 sha를 receipt로 남긴다. local_execute 경로의 안전한 실증 기본.
    """
    def execute(self, action: str, target: Optional[str], payload: dict) -> ExecutorResult:
        cwd = payload.get("workspace_root") or payload.get("cwd") or "."
        message = payload.get("message") or payload.get("commit_message") or "dipeen: approved commit"
        proc = subprocess.run(["git", "commit", "-m", message], cwd=cwd, capture_output=True, text=True)
        if proc.returncode != 0:
            return ExecutorResult(success=False, message=(proc.stderr or proc.stdout or "git commit failed").strip()[:200])
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True).stdout.strip()
        return ExecutorResult(success=True, uri=f"git://{sha}", message=f"committed {sha[:8]}: {message}")


def default_executors() -> dict[str, ExecutorPlugin]:
    """안전한 기본 executor 집합 — **git.commit만**(로컬·가역). 외부 side effect(github.pr.create via gh 등)는
    명시적 opt-in으로 추가(자격증명·네트워크 필요). worker는 executor_mode=local_execute일 때만 이걸 호출한다."""
    return {"git.commit": GitCommitExecutor()}


def guard_check(action: str, payload: dict) -> tuple[bool, str]:
    """LocalPermissionGuard — worker가 실행 직전 정책을 *재확인*. Core 승인만으로 실행하지 않는다."""
    if policy.classify(action) == "deny":
        return False, f"policy deny: {action}"
    branch = (payload or {}).get("branch", "")
    base = (payload or {}).get("base", "")
    if action == "git.push" and branch in ("main", "master"):
        return False, "직접 main/master push 금지"
    if action == "github.pr.create":
        if base and base not in _ALLOWED_BASE:
            return False, f"허용되지 않은 base: {base}"
        if not branch:
            return False, "branch 미지정"
    return True, "ok"


def receipt_type(action: str) -> str:
    """action → receipt artifact 타입."""
    if action == "github.pr.create":
        return "pr_reference"
    if action == "github.issue.create":
        return "issue_reference"
    return "command_receipt"


def compute_permission_receipt(cmd, *, executor_mode: ExecutorMode,
                               executors: Optional[dict], worker_id: str):
    """승인된 permission.execute를 worker가 executor_mode대로 처리해 Receipt artifact를 만든다.
    WorkerNode(로컬 ingest)와 WorkerHttpClient(원격 POST)가 공유. 반환 (Artifact, executed)."""
    from .contracts import Artifact, ArtifactLocation, ArtifactProducer, Evidence
    action = cmd.payload.get("action", "")
    target = cmd.payload.get("target")
    ok, reason = guard_check(action, cmd.payload)            # 로컬 정책 재확인(Core 승인 맹신 X)
    art_type = receipt_type(action)
    uri = ""
    executed = False
    if not ok:                                              # guard 거부 → 모드 무관 rejected
        evidence = [Evidence(kind="manual_approval", passed=True),
                    Evidence(kind="executor_success", passed=False)]
        summary = f"guard rejected: {reason}"
    elif executor_mode == "dry_run":                        # 미리보기 — 실행 안 함
        art_type = "document"
        evidence = [Evidence(kind="manual_approval", passed=True),
                    Evidence(kind="would_execute", passed=True)]
        summary = f"DRY RUN — would execute {action} on {target}"
    elif executor_mode == "manual_handoff":
        art_type = "document"
        evidence = [Evidence(kind="manual_approval", passed=True),
                    Evidence(kind="manual_action_required", passed=True)]
        summary = f"MANUAL HANDOFF — 사람이 직접 {action} on {target} 수행"
    else:                                                   # local_execute
        executor = (executors or {}).get(action)
        if executor is None:
            art_type = "document"
            evidence = [Evidence(kind="manual_approval", passed=True)]
            summary = "no executor — manual handoff required"
        else:
            # executor는 payload만 보므로 cmd.workspace_root를 합쳐 전달(워크스페이스 인지)
            res = executor.execute(action, target, {**cmd.payload, "workspace_root": cmd.workspace_root})
            uri, summary, executed = res.uri, res.message, res.success
            evidence = [Evidence(kind="manual_approval", passed=True),
                        Evidence(kind="executor_success", passed=res.success)]
    receipt = Artifact(
        type=art_type, task_id=cmd.task_id, run_id=cmd.run_id,
        producer=ArtifactProducer(identity=f"dipeen://worker/{worker_id}", adapter="permission_executor"),
        title=f"{action} receipt", summary=summary,
        locations=[ArtifactLocation(uri=uri)] if uri else [], evidence=evidence)
    return receipt, executed
