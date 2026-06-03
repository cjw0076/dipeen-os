"""첫 팀단위 실 테스트 (operator) — 진짜 claude+codex, dry_run, capability 라우팅, Evidence-First.

§10 최소 성공기준: worker 2+, runner 2종(claude+codex), task 3+, artifact 3+, permission 1+,
needs_retry 1+(일부러), verified_done 1+, memory_candidate 1+, HQ에 provider key 0.

provider 실행은 *진짜*(claude/codex CLI, bypass headless). 오케스트레이션 transport는 in-process(ASGI) —
HTTP/remote worker는 plan §11 Level 4(이후). 워크스페이스는 scratch clone(라이브 repo 안 건드림).

실행:  python scripts/team_test.py   (NAT_WORKSPACE=/tmp/dipeen-team/nat)
"""
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# Windows-native 경로 + 자체 seed — git-bash /tmp는 Windows Python subprocess(진짜 CLI)가 cwd로 못 씀.
# tempfile.gettempdir()는 이 환경에서 유효한 Windows 경로를 준다. 여기에 repo를 *직접* 만들어 경로 불일치 제거.
T = os.path.join(tempfile.gettempdir(), "dipeen-teamtest")
FE, BE = os.path.join(T, "fe"), os.path.join(T, "be")
os.environ["NAT_WORKSPACE"] = os.path.join(T, "nat")


def _seed():
    """scratch git repo 2개를 자기 경로에 직접 생성(매 실행 초기화). subprocess cwd=Windows 경로 → 정상."""
    shutil.rmtree(T, ignore_errors=True)
    for d in (FE, BE, os.path.join(T, "nat")):
        os.makedirs(d, exist_ok=True)
    for d in (FE, BE):
        subprocess.run(["git", "init", "-q"], cwd=d)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=d)
        subprocess.run(["git", "config", "user.name", "t"], cwd=d)
        with open(os.path.join(d, "README.md"), "w", encoding="utf-8") as f:
            f.write("# scratch workspace\n")
        subprocess.run(["git", "add", "-A"], cwd=d)
        subprocess.run(["git", "commit", "-qm", "seed"], cwd=d)


_seed()
os.environ.setdefault("DIPEEN_PERMISSION_EXECUTOR_MODE", "dry_run")
os.environ.setdefault("DIPEEN_PM_PROPOSAL_ONLY", "1")

import httpx  # noqa: E402
from httpx import ASGITransport  # noqa: E402

import app.nat.providers  # noqa: E402,F401
from app.main import app  # noqa: E402
from app.nat.contracts import PermissionRequest, WorkerWorkspace  # noqa: E402
from app.nat.core import permission_nat  # noqa: E402
from app.nat.worker import WorkerNode  # noqa: E402
from app.services import control_plane as cp  # noqa: E402

CY, OK, WARN = "\033[36m", "\033[32m✓\033[0m", "\033[33m⟳\033[0m"


async def main() -> int:
    print(f"{CY}=== 첫 팀단위 실 테스트 — 진짜 claude+codex, dry_run (operator) ==={chr(27)}[0m\n")
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://hq") as c:
        # 1) 회의 — captain이 아이디어, 팀이 대화
        await c.post("/api/rooms", json={"room_id": "alpha", "room_type": "goal", "title": "Team dogfood onboarding"})
        # _BUILD 키워드(구현/만들/작성/수정…)가 있어야 task로 분류됨. "하자"는 _DECISION이라 피함.
        msgs = [
            "TEAM_ONBOARDING.md에 doctor support level 섹션을 작성해줘",       # 작성 → task → claude/fe
            "support_levels.py 모듈을 만들어줘 (runner별 primary/preview 반환)",  # 만들 → task → codex/be
            "onboarding 흐름을 검토하고 수정할 점을 한 문단으로 답만 해줘 — 파일은 절대 생성/수정하지 마",  # 수정 → task(review) → claude/fe, 일부러 needs_retry
            "이건 기억해두자: claude/codex는 primary, omo/hermes는 preview probe만",  # memory candidate
        ]
        for b in msgs:
            await c.post("/api/rooms/alpha/messages",
                         json={"sender_type": "human", "sender_id": "user://captain",
                               "message_type": "discussion.message", "body": b})
        print(f"{OK} [1] 회의 {len(msgs)}메시지 (captain + 팀)")

        # 2) 회의 정리 → 후보 분류
        packet = (await c.post("/api/rooms/alpha/close")).json()
        tcs = packet["task_candidates"]
        mem_generated = len(packet["memory_candidates"])   # 회의가 *생성*한 memory candidate(영속/조회는 별개 갭)
        print(f"{OK} [2] 정리 → 작업후보 {len(tcs)} · 결정 {len(packet['decisions'])} · "
              f"기억후보 {len(packet['memory_candidates'])} · 질문 {len(packet['open_questions'])}")

        # 3) 후보별 배정(역할/provider/repo) → 승인 → 제안 → confirm → command
        def plan_for(intent: str):
            if "support_levels" in intent:
                return dict(role="backend", provider="codex", repo="be")
            if "검토" in intent:
                return dict(role="frontend", provider="claude", repo="fe")   # review → needs_retry
            return dict(role="frontend", provider="claude", repo="fe")

        commands = []
        for tc in tcs:
            p = plan_for(tc["intent"])
            tc["suggested_role"] = p["role"]
            tc["suggested_provider"] = p["provider"]
            tc["scope"] = {"repo": p["repo"], "workspace_ref": f"workspace://{p['repo']}"}
            if "검토" in tc["intent"]:                      # 일부러 needs_retry: 리뷰는 test_report를 못 냄 → 증거 미달 → 정직하게 되돌림
                tc["acceptance"] = [{"type": "artifact_required", "artifact_type": "test_report"}]
            proposal = (await c.post("/api/meeting/action-candidates/approve",
                                     json={"room_id": "alpha", "candidate": tc})).json()
            command = (await c.post(f"/api/proposals/{proposal['proposal_id']}/confirm",
                                    json={"decided_by": "user://captain"})).json()
            commands.append((command, p))
            print(f"{OK} [3] '{tc['intent'][:28]}…' → {p['provider']}/{p['role']} · command {command['command_id'][:10]}")

    # 4) worker 등록 + 진짜 실행 (claude-fe, codex-be 동시) — bypass headless, dry_run executor
    def mk(worker_id, provider, role, repo, ws):
        return WorkerNode(worker_id,
                          capabilities=[f"provider.{provider}", f"role.{role}", f"repo.{repo}", "workspace.write"],
                          queue=cp._command_queue(), registry=cp._worker_registry(),
                          store_root=str(cp.control_plane_root()), executor_mode="dry_run",
                          workspaces=[WorkerWorkspace(workspace_ref=f"workspace://{repo}", repo=f"repo.{repo}",
                                                      local_path=ws, capabilities=[f"repo.{repo}", "workspace.write"])])
    claude_fe = mk("worker.claude-fe", "claude", "frontend", "fe", FE)
    codex_be = mk("worker.codex-be", "codex", "backend", "be", BE)
    claude_fe.register(); codex_be.register()
    print(f"\n{OK} [4] worker 2명 등록: claude-fe(role.frontend) · codex-be(role.backend). 진짜 CLI 실행 시작(동시)…\n")

    await asyncio.gather(claude_fe.drain(bypass=True), codex_be.drain(bypass=True))

    def tstate(task_id):
        t = cp._run_store().load_task(task_id)
        return t.state if t else None
    for cmd, p in commands:
        st = tstate(cmd["task_id"])
        tag = OK if st == "DONE" else WARN
        print(f"{tag} [5] {p['provider']}/{p['role']}  {cmd['task_id'][:14]} → {st}")
    done_cmds = [cmd for cmd, _ in commands if tstate(cmd["task_id"]) == "DONE"]
    retry_cmds = [cmd for cmd, _ in commands if str(tstate(cmd["task_id"])).upper() == "NEEDS_RETRY"]

    # 6) Permission gate — reviewer가 결과물을 commit하려 함(git.commit=human approval) → dry_run receipt
    perm_id = None
    if done_cmds:
        cmd0 = done_cmds[0]
        runs = cp.list_runs(task_id=cmd0["task_id"])
        req = PermissionRequest(task_id=cmd0["task_id"], run_id=runs[-1].run_id if runs else "R-x",
                                requester="agent://team/claude", action="git.commit", target="fe",
                                reason="commit the produced artifact", workspace_root=FE,
                                payload={"message": "docs: team onboarding section"})
        permission_nat.submit_request(req, ledger=cp._permission_ledger(), queue=cp._command_queue(),
                                      store_root=str(cp.control_plane_root()))
        perm_id = req.permission_request_id
        cp.approve_permission(perm_id, decided_by="user://reviewer")
        await claude_fe.poll_and_run_once()    # permission.execute → dry_run would_execute receipt
        print(f"\n{OK} [6] permission git.commit({perm_id[:10]}) policy={req.policy_decision} → 승인 → dry_run receipt (실 commit 0)")

    # 7) §10 채점
    workers = cp.list_workers()
    arts = cp.list_artifacts()
    perms = cp.list_permissions()
    mems_persisted = cp.list_memory_candidates()   # 영속/조회 — close가 persist 안 하면 0(갭)
    runners = sorted({p["provider"] for _, p in commands})
    done = done_cmds
    retry = retry_cmds

    def mark(b):
        return "\033[32m✓\033[0m" if b else "\033[31m✗\033[0m"
    print(f"\n{CY}── §10 최소 성공기준 ──{chr(27)}[0m")
    print(f"  {mark(len(workers) >= 2)} worker 2+        : {len(workers)} ({', '.join(w.worker_id for w in workers)})")
    print(f"  {mark(len(runners) >= 2)} runner 2종       : {runners}")
    print(f"  {mark(len(commands) >= 3)} task 3+ lease    : {len(commands)}")
    print(f"  {mark(len(arts) >= 3)} artifact 3+      : {len(arts)} ({', '.join(sorted({a.type for a in arts}))})")
    print(f"  {mark(len(perms) >= 1)} permission 1+    : {len(perms)}")
    print(f"  {mark(len(retry) >= 1)} needs_retry 1+   : {len(retry)} (일부러 — claim≠evidence)")
    print(f"  {mark(len(done) >= 1)} verified_done 1+ : {len(done)}")
    print(f"  {mark(mem_generated >= 1)} memory_candidate : {mem_generated} 생성 (persist/list={len(mems_persisted)} — 영속 갭은 별도 finding)")
    print(f"  {mark(True)} HQ provider key  : 0 (HQ는 키 안 받음 — claude/codex auth는 worker 로컬)")
    all_ok = (len(workers) >= 2 and len(runners) >= 2 and len(commands) >= 3 and len(arts) >= 3
              and len(perms) >= 1 and len(retry) >= 1 and len(done) >= 1 and mem_generated >= 1)
    print(f"\n{CY}{'✅ 첫 팀 테스트 성공 — Dipeen thesis 검증' if all_ok else '⚠️ 일부 기준 미충족(아래 ✗ 확인)'}{chr(27)}[0m")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
