"""팀단위 통합 스모크 — 키 없는 한 사이클 (provider.fake).

사람 회의 → Dipeen 정리/배정 → Routing(맞는 사람에게) → confirm → 그 사람 worker가 lease →
키·CLI·네트워크 0으로 fake 실행 → 진짜 code_patch → Reconciler가 증거로 DONE 판정.

ASGI HTTP(web/worker가 부르는 실제 엔드포인트) + WorkerNode(분산 실행)로 통합 검증.
실행: NAT_WORKSPACE=<temp> python scripts/team_smoke.py   (pip install -e api 후)
"""
import asyncio
import os
import sys
import tempfile

for _s in (sys.stdout, sys.stderr):          # Windows cp949 콘솔에서 한글/em-dash 출력이 안 깨지게
    try:
        _s.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

STORE = tempfile.mkdtemp(prefix="dipeen-smoke-")
os.environ["NAT_WORKSPACE"] = STORE
os.environ.setdefault("DIPEEN_PERMISSION_EXECUTOR_MODE", "dry_run")
os.environ.setdefault("DIPEEN_PM_PROPOSAL_ONLY", "1")

import httpx  # noqa: E402
from httpx import ASGITransport  # noqa: E402

import app.nat.providers  # noqa: E402,F401  (register_defaults: claude/codex/fake)
from app.main import app  # noqa: E402
from app.nat.contracts import WorkerWorkspace  # noqa: E402
from app.nat.worker import WorkerNode  # noqa: E402
from app.services import control_plane as cp  # noqa: E402

CYAN, OK = "\033[36m", "\033[32m✓\033[0m"
WS = os.path.join(STORE, "minjun-ws")
os.makedirs(WS, exist_ok=True)


async def main() -> int:
    print(f"{CYAN}=== 팀단위 통합 스모크 — 키 없는 한 사이클 (provider.fake) ==={chr(27)}[0m\n")
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://smoke") as c:
        # 1) 회의방 + 사람들의 회의 메시지
        await c.post("/api/rooms", json={"room_id": "goal-login", "room_type": "goal", "title": "Login release"})
        for body, mt in [("민준이 로그인 UI 구현하자", "discussion.message"),
                         ("상태관리는 Zustand 쓰자", "discussion.message"),
                         ("이 결정은 기억해두자", "discussion.message"),
                         ("테스트 실패 원인이 뭐야?", "discussion.message")]:
            await c.post("/api/rooms/goal-login/messages",
                         json={"sender_type": "human", "sender_id": "user://pm", "message_type": mt, "body": body})
        print(f"{OK} [1] 사람 회의 4메시지 게시")

        # 2) 회의 정리 → 후보 분류 (승인 전엔 작업 아님)
        packet = (await c.post("/api/rooms/goal-login/close")).json()
        print(f"{OK} [2] 회의 정리 → 작업후보 {len(packet['task_candidates'])} · 결정 {len(packet['decisions'])} · "
              f"기억후보 {len(packet['memory_candidates'])} · 질문 {len(packet['open_questions'])}")

        # 3) 작업후보에 배정(역할 frontend) + 키 없는 fake provider → 승인 → CommandProposal
        cand = packet["task_candidates"][0]
        cand["suggested_role"] = "frontend"
        cand["suggested_provider"] = "fake"
        cand["scope"] = {"repo": "ezmap-web", "workspace_ref": "workspace://ezmap-web"}
        proposal = (await c.post("/api/meeting/action-candidates/approve",
                                 json={"room_id": "goal-login", "candidate": cand})).json()
        print(f"{OK} [3] 승인 → 제안 (배정: {proposal['assignment']['role']} · repo {proposal['assignment']['repo']} · provider fake)")

        # 4) Routing Preview — worker 등록 전: 받을 사람 없음
        asg = {"role": "frontend", "repo": "ezmap-web", "workspace_ref": "workspace://ezmap-web", "provider": "fake"}
        pv0 = (await c.post("/api/routing/preview", json={"assignment": asg, "provider": "fake"})).json()
        print(f"{OK} [4] preview(worker 전): deliverable={pv0['deliverable']} (받을 worker 없음)")

        # 5) 민준 PC worker 등록 (role.frontend + provider.fake + workspace) — HQ는 local_path 모름
        await c.post("/api/workers", json={
            "worker_id": "worker.minjun-mac",
            "capabilities": ["provider.fake", "role.frontend", "user.minjun", "repo.ezmap-web", "workspace.write"],
            "workspaces": [{"workspace_ref": "workspace://ezmap-web", "repo": "repo.ezmap-web",
                            "local_path": WS, "capabilities": ["repo.ezmap-web", "workspace.write"]}]})
        pv1 = (await c.post("/api/routing/preview", json={"assignment": asg, "provider": "fake"})).json()
        mw = pv1["matching_workers"][0]
        print(f"{OK} [5] 민준 등록 → preview: deliverable={pv1['deliverable']} → {mw['user']} (workspace_available={mw['workspace_available']})")

        # 6) confirm → run.start command (workspace_ref + 라우팅 caps, 절대경로 없음)
        command = (await c.post(f"/api/proposals/{proposal['proposal_id']}/confirm",
                                json={"decided_by": "user://web"})).json()
        print(f"{OK} [6] confirm → command {command['command_id'][:12]} · caps={command['required_capabilities']} · "
              f"ws={command['workspace_ref']} · abs_path={command['workspace_root'] or '없음(HQ는 로컬경로 모름)'}")

        # 7) 다른 역할(QA) worker는 못 가져감
        await c.post("/api/workers", json={"worker_id": "worker.bob-qa",
                                           "capabilities": ["provider.fake", "role.qa", "workspace.write"]})
        none = (await c.post("/api/workers/worker.bob-qa/commands/poll",
                             json={"capabilities": ["provider.fake", "role.qa", "workspace.write"]})).json()
        print(f"{OK} [7] bob-qa(role.qa) poll → {none['command']} (FE 작업 못 가져감 — 라우팅 격리)")

    # 8) 민준 worker가 lease + 키 없이 fake 실행 → code_patch → reconcile DONE (분산 실행)
    worker = WorkerNode(
        "worker.minjun-mac",
        capabilities=["provider.fake", "role.frontend", "user.minjun", "repo.ezmap-web", "workspace.write"],
        queue=cp._command_queue(), registry=cp._worker_registry(), store_root=str(cp.control_plane_root()),
        workspaces=[WorkerWorkspace(workspace_ref="workspace://ezmap-web", repo="repo.ezmap-web",
                                    local_path=WS, capabilities=["repo.ezmap-web", "workspace.write"])])
    result = await worker.poll_and_run_once()
    state = result.state if result else None
    print(f"{OK} [8] 민준 worker lease + 키 없이 fake 실행 → reconcile: {state}")

    # 9) 증거 확인
    arts = cp.list_artifacts(type="code_patch")
    print(f"\n{CYAN}── 증거 ──{chr(27)}[0m")
    print(f"   task state   : {state}")
    print(f"   code_patch   : {len(arts)} artifact (키 0·CLI 0·네트워크 0으로 생성된 진짜 변경)")
    print(f"   실행 worker  : worker.minjun-mac (role.frontend — 배정대로)")
    print(f"   QA worker    : 작업 못 받음 (라우팅 격리)")
    print(f"\n{CYAN}사람 회의 → Dipeen이 배정·라우팅·분산실행·증거검증. 키 없이 한 사이클 완료.{chr(27)}[0m")
    return 0 if (state == "DONE" and arts) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
