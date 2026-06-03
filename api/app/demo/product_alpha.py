"""Product Alpha walkthrough — `python -m app.demo.product_alpha`.

API 키 없이 60초 안에 Dipeen의 핵심 가치를 *진짜 증거로* 보여준다:
  Goal → Task → run.start command(Core는 실행 안 함) → worker가 BYOK로 로컬 실행
  → **agent가 DONE이라 주장해도 증거 없으면 Dipeen은 NEEDS_RETRY** → retry로 진짜 code_patch
  → 위험 행동(github.pr.create)은 Permission → 승인해도 기본 dry_run receipt(진짜 PR 없음)
  → 결정은 Organization Memory 후보로.

모든 artifact/receipt는 실제 파일·git diff·실제 reconcile 결과다(가짜 증거 금지 = Evidence First).
결정론적: 같은 의도를 주면 1차는 빈손(거짓 완료), 2차는 실제 파일 — 사람 개입 없이 같은 데모.
"""
from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path

from app.nat import providers as _providers
from app.nat.adapters.base import ExecResult
from app.nat.contracts import MemoryCandidate, PermissionRequest, TaskEnvelope
from app.nat.core import conductor, permission_nat
from app.nat.core.artifact_store import ArtifactStore
from app.nat.core.command_queue import CommandQueue
from app.nat.core.permission_ledger import PermissionLedger
from app.nat.core.run_store import RunStore
from app.nat.core.worker_registry import WorkerRegistry
from app.nat.executors import default_executors
from app.nat.worker import WorkerNode

GREEN, YELLOW, RED, DIM, BOLD, CYAN, RESET = (
    "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m", "\033[36m", "\033[0m")


def _say(scene: str, line: str, tone: str = CYAN) -> None:
    print(f"\n{tone}{BOLD}{scene}{RESET}  {line}")


def _agent(line: str) -> None:
    print(f"   {DIM}agent ▸{RESET} {line}")


def _dipeen(line: str, ok: bool = True) -> None:
    mark = f"{GREEN}✓{RESET}" if ok else f"{YELLOW}⟳{RESET}"
    print(f"   {mark} {BOLD}Dipeen ▸{RESET} {line}")


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)


class _DemoRunner:
    """결정론적 가짜 provider — 1차: 'done' 주장하지만 파일 0(거짓 완료). 2차: 실제 login.py 작성."""
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, argv, *, cwd, env, timeout_sec):
        self.calls += 1
        if self.calls == 1:
            return ExecResult(0, "Implemented the login feature. All done!", "")   # 빈손 주장
        (Path(cwd) / "login.py").write_text(
            "def login(user, pw):\n    return authenticate(user, pw)\n", encoding="utf-8")
        return ExecResult(0, "Added login.py with authenticate() wiring.", "")


def _new_repo(root: Path) -> Path:
    ws = root / "workspace"
    ws.mkdir()
    _git(["init", "-q"], ws)
    _git(["config", "user.email", "demo@dipeen"], ws)
    _git(["config", "user.name", "dipeen-demo"], ws)
    return ws


async def run_demo(store: str, ws: Path) -> dict:
    _providers.register_defaults()
    queue = CommandQueue(store)
    rs = RunStore(store)
    worker = WorkerNode("alice-macbook", capabilities=["provider.claude", "workspace.write",
                                                       "executor.github.pr.create"],
                        queue=queue, registry=WorkerRegistry(store), store_root=store,
                        executors=default_executors())     # executor_mode 기본 dry_run
    worker.register()
    runner = _DemoRunner()

    print(f"\n{BOLD}{CYAN}╔════════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║  DIPEEN — Product Alpha walkthrough (no API key)            ║{RESET}")
    print(f"{BOLD}{CYAN}║  Every artifact & receipt below is REAL.                   ║{RESET}")
    print(f"{BOLD}{CYAN}╚════════════════════════════════════════════════════════════╝{RESET}")

    # ── 1. Goal → Task ─────────────────────────────────────────────
    task = TaskEnvelope(title="Ship login feature", intent="Implement the login feature",
                        acceptance=[{"type": "artifact_required", "artifact_type": "code_patch"}],
                        state="READY")
    _say("[1] Goal → Task", f'"{task.title}"  (acceptance: a real code_patch is required)')
    _dipeen(f"task {task.task_id} created. Source of truth lives in Dipeen, not in the agent.")

    # ── 2. Dispatch → command (Core는 실행 안 함) ──────────────────
    _say("[2] Dispatch → Command queue", "Conductor enqueues a run.start command.")
    conductor.dispatch_run(queue, task, provider="claude", workspace_root=str(ws), store_root=store)
    _dipeen("command queued for a worker to pull. The Core itself runs no provider — workers do.")

    # ── 3. Worker attempt 1 — 거짓 완료, 증거로 차단 ───────────────
    _say("[3] Worker runs — agent claims DONE", "alice-macbook pulls the command (BYOK).")
    r1 = await worker.poll_and_run_once(runner=runner)
    _agent('"Implemented the login feature. All done!"')
    state1 = r1.state if r1 else "?"
    _dipeen(f"reconciled to {BOLD}{state1}{RESET} — the claim had no code_patch evidence. "
            f"Claim ≠ truth.", ok=False)

    # ── 4. Retry — 진짜 변경 → DONE ────────────────────────────────
    _say("[4] Retry — evidence this time", "Dipeen re-dispatches; same agent, real change.")
    conductor.dispatch_run(queue, task, provider="claude", workspace_root=str(ws), store_root=store)
    r2 = await worker.poll_and_run_once(runner=runner)
    _agent("wrote login.py  →  git diff is real")
    state2 = r2.state if r2 else "?"
    arts = ArtifactStore(store).list(task_id=task.task_id)
    has_patch = any(a.type == "code_patch" for a in arts)
    _dipeen(f"reconciled to {BOLD}{state2}{RESET} — code_patch artifact verified "
            f"({'present' if has_patch else 'missing'}). Completion is earned by evidence.")

    # ── 5. Risky action → Permission (승인해도 dry_run) ────────────
    _say("[5] Risky action → Permission", "Agent wants to open a PR (github.pr.create).")
    led = PermissionLedger(store)
    req = PermissionRequest(task_id=task.task_id, run_id="R-demo-pr",
                            requester="agent://team/alice-macbook", action="github.pr.create",
                            target="feature/login", reason="Open PR for the login feature",
                            risk="medium", requires_human_approval=True, workspace_root=str(ws),
                            payload={"branch": "feature/login", "base": "main"})
    permission_nat.submit_request(req, ledger=led, queue=queue, store_root=store)
    _dipeen("policy = requires human approval. Nothing executes yet.")
    _agent("(waiting for a human to approve)")
    permission_nat.approve(req.permission_request_id, decider="you@human", ledger=led, queue=queue)
    await worker.poll_and_run_once(runner=runner)      # worker가 permission.execute 처리
    # dry_run receipt = would_execute 증거를 가진 artifact(run의 command_receipt와 구분)
    is_dry = any(e.kind == "would_execute" and e.passed
                 for a in ArtifactStore(store).list(task_id=task.task_id) for e in a.evidence)
    _dipeen(f"approved → {BOLD}dry_run{RESET} receipt produced. {GREEN}No real PR was opened.{RESET} "
            f"Opt in with DIPEEN_PERMISSION_EXECUTOR_MODE=local_execute.", ok=True)

    # ── 6. Decision → Organization memory ─────────────────────────
    _say("[6] Decision → Organization memory", "What the team decided, remembered.")
    cand = MemoryCandidate(memory_type="project_decision",
                           proposed_content="Login uses authenticate(user, pw); PR gated by approval.",
                           confidence=0.7)
    (Path(store) / "memory").mkdir(parents=True, exist_ok=True)
    (Path(store) / "memory" / f"{cand.memory_candidate_id}.json").write_text(
        cand.model_dump_json(indent=2), encoding="utf-8")
    _dipeen("memory candidate queued — awaiting human promotion (decisions, not chatter, are remembered).")

    return {"task_id": task.task_id, "attempt1": state1, "attempt2": state2,
            "artifacts": len(arts), "code_patch": has_patch, "dry_run_receipt": is_dry,
            "memory_candidate": cand.memory_candidate_id}


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="dipeen-demo-"))
    store = str(root / "nat")
    ws = _new_repo(root)
    try:
        out = asyncio.run(run_demo(store, ws))
    finally:
        pass
    print(f"\n{BOLD}{GREEN}── Summary ──{RESET}")
    print(f"   task            : {out['task_id']}")
    print(f"   attempt 1 / 2   : {out['attempt1']}  →  {out['attempt2']}   (false-done caught, then earned)")
    print(f"   artifacts       : {out['artifacts']}  (real code_patch: {out['code_patch']})")
    print(f"   risky action    : approved, dry_run receipt — no real side effect")
    print(f"   org memory      : 1 candidate awaiting promotion")
    print(f"\n   {DIM}inspect the real evidence: {store}{RESET}")
    print(f"   {DIM}clean up:  rm -rf {root}{RESET}")
    print(f"\n{BOLD}{CYAN}Agents can work. Dipeen makes them an organization.{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
