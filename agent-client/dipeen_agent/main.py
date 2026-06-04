"""dipeen Agent Client — 메인 진입점.

사용법:
  python -m dipeen_agent              # start (기본)
  python -m dipeen_agent start        # 등록 + 폴링 루프 시작
  python -m dipeen_agent status       # 현재 연결 상태 확인

환경변수:
  DIPEEN_API_URL=http://10.0.0.1:8000  (VPN 내부 API)
  DIPEEN_AGENT_ID=fe-agent
  DIPEEN_WORKSPACE=D:/path/to/dipeen-workspace
"""

import argparse
import asyncio
import subprocess
import sys

# Windows 콘솔(cp949)에서 이모지/유니코드 print가 UnicodeEncodeError로 죽지 않게 stdout/stderr를
# utf-8(errors=replace)로 재구성. 에이전트 실행 중 ✅ 같은 문자 출력이 보고 전에 크래시시키던 버그 방지.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

import httpx

from dipeen_agent.client import AgentClient
from dipeen_agent.config import API_URL, AGENT_ID, AGENT_ROLE, WORKSPACE, AGENT_EXECUTOR
from dipeen_agent.runtime import AgentRuntime, provision_workspace_files
from dipeen_agent.personas import DEFAULT_PERSONA


def _provision_workspace() -> None:
    """WORKSPACE 폴더가 없거나 git repo가 아니면 자동 초기화."""
    WORKSPACE.mkdir(parents=True, exist_ok=True)

    git_dir = WORKSPACE / ".git"
    if not git_dir.exists():
        print(f"[agent] workspace git 초기화: {WORKSPACE}", flush=True)
        subprocess.run(["git", "init"], cwd=WORKSPACE, capture_output=True)
        subprocess.run(["git", "checkout", "-b", "main"], cwd=WORKSPACE, capture_output=True)

    readme = WORKSPACE / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Project Workspace\n\n"
            "이 폴더는 dipeen 에이전트가 작업하는 프로젝트 공간입니다.\n"
            "에이전트가 태스크를 받으면 여기에 파일을 생성/수정합니다.\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "add", "README.md"], cwd=WORKSPACE, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init: workspace initialized by dipeen agent"],
            cwd=WORKSPACE, capture_output=True,
        )
        print(f"[agent] workspace 초기 커밋 완료", flush=True)

    print(f"[agent] Workspace: {WORKSPACE}", flush=True)


def _nat_capabilities(raw: str | None = None) -> list[str]:
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    provider = "codex" if AGENT_EXECUTOR == "codex" else "claude"
    return [f"provider.{provider}", "workspace.write", "git.diff"]


def _command_to_legacy_task(command: dict) -> dict:
    task = command.get("task") or {}
    return {
        "task_id": task.get("task_id") or command.get("task_id"),
        "subject": task.get("title") or command.get("task_id") or "NAT command",
        "prompt": task.get("intent") or "",
        "status": "in_progress",
        "branch": command.get("workspace_root") or "",
        "required_role": AGENT_ROLE,
        "metadata_json": {
            "run_id": command.get("run_id"),
            "command_id": command.get("command_id"),
            "provider": command.get("provider"),
            "nat": True,
        },
    }


def _format_unmatched(unmatched: list[dict]) -> str:
    """A None poll explained: capability mismatch (with the missing tokens) vs an empty queue."""
    if not unmatched:
        return "대기 중인 작업 없음 (큐 비어있음)."
    missing = sorted({m for u in unmatched for m in (u.get("missing") or [])})
    repos = [m.split(".", 1)[1] for m in missing if m.startswith("repo.")]
    hint = f"  (예: --repo {repos[0]})" if repos else ""
    return (f"대기 작업 {len(unmatched)}건이 capability 불일치로 안 잡힘 — 필요: "
            f"{', '.join(missing)}. 이 토큰을 워커 capability에 추가하세요{hint}")


async def cmd_worker(once: bool = False, capabilities: str | None = None, idle_sleep: float = 5.0,
                     workspace_ref: str | None = None, repo: str | None = None,
                     workspace: str | None = None) -> None:
    """NAT Product Alpha worker loop. HQ가 enqueue한 command만 pull해 실행한다.
    --workspace-ref/--repo/--workspace로 작업공간 등록 시 HQ는 workspace_ref만 알고 로컬 경로엔 의존 안 함."""
    client = AgentClient()
    runtime = AgentRuntime(client)
    caps = _nat_capabilities(capabilities)
    if repo:    # repo로 라우팅된 command를 lease하려면 poll capability에도 repo.<slug> 필요
        repo_ns = repo if repo.startswith("repo.") else f"repo.{repo}"
        if repo_ns not in caps:
            caps = list(caps) + [repo_ns]
    workspaces = _worker_workspaces(workspace_ref, repo, workspace)

    print("[worker] dipeen NAT worker 시작", flush=True)
    print(f"[worker] API: {client.api_url}", flush=True)
    print(f"[worker] Worker ID: {client.agent_id}", flush=True)
    print(f"[worker] Capabilities: {', '.join(caps)}", flush=True)
    _provision_workspace()
    from .onboarding import build_register_probe
    probe = build_register_probe(caps)                 # Keystone C: 실제 runnable(설치+auth)만 광고
    for prov, info in probe.items():
        mark = "OK" if info.get("runnable") else f"-- ({info.get('blocker') or 'not runnable/auth'})"
        print(f"[worker] probe provider.{prov}: {mark}", flush=True)
    await client.register_worker(caps, workspaces=workspaces, probe=probe)
    provision_workspace_files(WORKSPACE, AGENT_ROLE, DEFAULT_PERSONA)

    last_idle_msg = None
    while True:
        await client.worker_heartbeat()
        command = await client.poll_worker_command(caps)
        if not command:
            idle_msg = _format_unmatched(getattr(client, "last_unmatched", []))
            if once:
                print(f"[worker] {idle_msg}", flush=True)
                return
            if idle_msg != last_idle_msg:           # throttle: only print when the reason changes
                print(f"[worker] {idle_msg}", flush=True)
                last_idle_msg = idle_msg
            await asyncio.sleep(idle_sleep)
            continue

        command_id = command["command_id"]
        task = _command_to_legacy_task(command)
        print(f"[worker] command pull: {command_id} → {task['task_id']}", flush=True)
        result = await runtime.execute_task(task)

        from .runners.base import finalize_artifacts
        runner_name = "omo-opencode" if AGENT_EXECUTOR == "omo" else "claude-code"
        artifacts = finalize_artifacts(
            result.get("artifacts") or {}, WORKSPACE,
            runner=runner_name, agent_id=client.agent_id,
            task=task, status=result["status"], config=runtime.config,
        )
        response = await client.submit_worker_result(command_id, result, artifacts)
        print(f"[worker] result uploaded: {command_id} → {response.get('state')}", flush=True)
        if once:
            return


async def cmd_start() -> None:
    """DEPRECATED — 레거시 roster/presence 경로. 합류해서 일하는 정식 경로는
    `dipeen-agent join <code> --api-url <url>` (내부적으로 worker). `start`는 NAT 큐 작업을
    안 잡아 "합류했는데 작업이 안 옴" 혼란의 원인이었다. 호환을 위해 경고 후 worker로 위임한다.
    (실시간 presence는 후속(T7)에서 worker에 합류 예정 — _cmd_start_legacy 참조.)"""
    import sys as _sys
    print("[deprecated] `dipeen-agent start`는 곧 제거됩니다 — "
          "`dipeen-agent join <code> --api-url <url>` 또는 `dipeen-agent worker --capabilities ...`를 쓰세요. "
          "지금은 worker로 위임합니다(큐 작업을 실제로 잡도록).", file=_sys.stderr, flush=True)
    await cmd_worker()


async def _cmd_start_legacy() -> None:
    """등록 + 폴링 루프 시작 (레거시 roster + hermes presence). T7에서 presence를 worker로 이식 후 제거."""
    client = AgentClient()
    runtime = AgentRuntime(client)

    async def on_hermes_message(env: dict):
        if env.get("type") == "A2A_MSG":
            payload = env.get("payload", {})
            sender = env.get("agent_id")
            print(f"[hermes] A2A 수신 from {sender}: {payload.get('content')}", flush=True)
            # 향후 여기서 특정 인텐트(작업 요청, 상태 확인 등) 처리 로직 추가

    print(f"[agent] dipeen agent-client 시작", flush=True)
    print(f"[agent] API: {client.api_url}", flush=True)
    print(f"[agent] Agent ID: {client.agent_id}", flush=True)

    # K-2: workspace 자동 프로비저닝 (없으면 생성 + git init)
    _provision_workspace()

    # Hermes WSS 연결 시작 (백그라운드)
    hermes_task = asyncio.create_task(client.connect_hermes(on_message=on_hermes_message))

    # K-6-3: 초기 등록 재시도 루프
    while True:
        try:
            info = await client.register()
            print(f"[agent] 등록 완료: {info['agent_id']} ({info['role']})", flush=True)
            await client.register_capability()
            # N-1: workspace에 IDENTITY.md / SOUL.md / AGENTS.md 프로비저닝
            provision_workspace_files(WORKSPACE, AGENT_ROLE, DEFAULT_PERSONA)
            break
        except Exception as e:
            print(f"[agent] 등록 실패, 30초 후 재시도: {e}", flush=True)
            await asyncio.sleep(30)

    try:
        while True:
            try:
                await client.heartbeat("idle")
                print(f"[agent] 대기 중... (polling)", flush=True)

                task = await client.poll_task()
                if not task:
                    continue

                task_id = task["task_id"]
                await client.heartbeat("working", task_id)

                result = await runtime.execute_task(task)

                # W1 솔기: artifacts를 HQ 계약(RunReport)에 맞게 보강 — scope_diff/checks/runner/run_report.
                # 이전엔 HQ가 artifacts에서 재구성했고 completion_promise/checks가 드롭됐다.
                from .runners.base import finalize_artifacts
                runner_name = "omo-opencode" if AGENT_EXECUTOR == "omo" else "claude-code"
                artifacts = finalize_artifacts(
                    result.get("artifacts") or {}, WORKSPACE,
                    runner=runner_name, agent_id=client.agent_id,
                    task=task, status=result["status"], config=runtime.config,
                )
                await client.report(
                    task_id=task_id,
                    status=result["status"],
                    pr_url=artifacts.get("pr_url"),  # K-5
                    tests_passed=result.get("tests_passed", False),
                    summary=result.get("summary", ""),
                    artifacts=artifacts,
                )
                print(f"[agent] 보고 완료: {task_id} → {result['status']}", flush=True)

                # K-8: 서브태스크 자동 생성
                for sub in result.get("subtasks", []):
                    try:
                        created = await client.create_subtask(
                            subject=sub.get("subject", ""),
                            prompt=sub.get("prompt", ""),
                            parent_task_id=task_id,
                            blocked_by=sub.get("blocked_by"),
                        )
                        print(
                            f"[agent] 서브태스크 생성: {created.get('task_id')} → {sub.get('subject')}",
                            flush=True,
                        )
                    except (httpx.ConnectError, httpx.TimeoutException):
                        raise  # K-6 재연결 핸들러로 위임
                    except Exception as e:
                        print(f"[agent] 서브태스크 생성 실패: {e}", flush=True)

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                # K-6-3: 서버 연결 끊김 → 대기 후 재등록
                print(f"[agent] 서버 연결 끊김: {e}", flush=True)
                print(f"[agent] 30초 후 재연결 시도...", flush=True)
                await asyncio.sleep(30)
                try:
                    await client.register()
                    print(f"[agent] 재등록 완료", flush=True)
                except Exception:
                    pass  # 다음 루프에서 재시도

    except KeyboardInterrupt:
        print("\n[agent] 종료.", flush=True)
        await client.heartbeat("offline")
    finally:
        await client.close()


async def cmd_slash(text: str) -> int:
    """슬래시/자연어 명령 한 줄을 HQ(/api/control/intent)로 보내 *사람 언어* 답을 출력.

    ux-command-layer-v0: 팀원은 team_id/lease_id/JWT를 몰라도 `dipeen-agent slash "/dipeen ask ..."`
    한 줄로 일을 요청·배정·승인한다. 도달 실패도 HTTP 코드가 아닌 사람 문장으로 안내."""
    from dipeen_agent.config import DIPEEN_TOKEN
    headers = {"Authorization": f"Bearer {DIPEEN_TOKEN}"} if DIPEEN_TOKEN else {}
    async with httpx.AsyncClient(timeout=30) as c:
        try:
            r = await c.post(f"{API_URL}/api/control/intent", json={"text": text}, headers=headers)
            data = r.json()
        except (httpx.ConnectError, httpx.TimeoutException):
            print(f"Can't reach Dipeen at {API_URL}. Open the workspace and try again.")
            return 1
    print(data.get("message", "(no response)"))
    return 0 if data.get("ok") else 1


async def cmd_status() -> None:
    """API 연결 상태 + 에이전트 정보 출력."""
    print(f"  API URL  : {API_URL}")
    print(f"  Agent ID : {AGENT_ID}")
    print(f"  Role     : {AGENT_ROLE}")

    async with httpx.AsyncClient(timeout=5) as c:
        # 헬스 체크
        try:
            r = await c.get(f"{API_URL}/health")
            if r.status_code == 200 and r.json().get("status") == "ok":
                print(f"  API      : connected")
            else:
                print(f"  API      : unexpected response {r.status_code}")
        except Exception as e:
            print(f"  API      : UNREACHABLE ({e})")
            return

        # 에이전트 정보
        try:
            r = await c.get(f"{API_URL}/api/agents/{AGENT_ID}")
            if r.status_code == 200:
                a = r.json()
                status = a.get("status", "unknown")
                task_id = a.get("current_task_id") or "—"
                hb = a.get("last_heartbeat") or "never"
                print(f"  Status   : {status}")
                print(f"  Task     : {task_id}")
                print(f"  Heartbeat: {hb}")
            elif r.status_code == 404:
                print(f"  Status   : not registered")
            else:
                print(f"  Status   : error {r.status_code}")
        except Exception as e:
            print(f"  Status   : error ({e})")


async def cmd_run(task_prompt: str, workflow: str, model: str, role: str, spatial: bool, quota: float) -> None:
    """즉시 태스크 실행 (CLI 모드)."""
    client = AgentClient()
    runtime = AgentRuntime(client)

    # 런타임 설정 주입
    runtime.set_config({
        "workflow": workflow,
        "model": model,
        "role": role,
        "spatial": spatial,
        "quota": quota
    })

    _provision_workspace()
    
    # 가상 태스크 생성
    task = {
        "task_id": f"CLI-{import_uuid().hex[:8]}",
        "subject": task_prompt[:50],
        "prompt": task_prompt,
        "required_role": role,
        "llm_provider": model.split(":")[0] if ":" in model else "anthropic",
        "model": model.split(":")[1] if ":" in model else model,
    }

    print(f"[agent] Run: {task_prompt} (workflow={workflow}, model={model})", flush=True)
    result = await runtime.execute_task(task)
    print(f"[agent] Result: {result['status']}", flush=True)


def import_uuid():
    import uuid
    return uuid.uuid4()


def _join_caps(role: str | None) -> str:
    """join --role FE → worker capability CSV. role.<role>이 Assignment Routing의 라우팅 토큰."""
    caps = ["provider.claude", "workspace.write"]
    if role:
        caps.insert(1, f"role.{role.strip().lower()}")
    return ",".join(caps)


def _worker_workspaces(workspace_ref: str | None, repo: str | None, workspace: str | None) -> list[dict]:
    """--workspace-ref/--repo/--workspace → WorkerWorkspace dict[]. local_path는 worker-local(HQ 비의존)."""
    if not workspace_ref:
        return []
    repo_ns = repo if (repo and repo.startswith("repo.")) else (f"repo.{repo}" if repo else None)
    caps = [c for c in (repo_ns, "workspace.write") if c]
    return [{"workspace_ref": workspace_ref, "repo": repo_ns,
             "local_path": workspace or "", "capabilities": caps}]


def run() -> None:
    parser = argparse.ArgumentParser(prog="dipeen-agent", description="dipeen agent client")
    subparsers = parser.add_subparsers(dest="command", help="명령어")

    # start
    start_parser = subparsers.add_parser("start", help="(deprecated) join/worker로 대체 — worker로 위임")
    
    # status
    subparsers.add_parser("status", help="연결 상태 확인")

    slash_parser = subparsers.add_parser("slash", help='슬래시/자연어 명령 한 줄 실행 (예: dipeen-agent slash "/dipeen status")')
    slash_parser.add_argument("text", help='명령 텍스트 (예: "/dipeen ask fix the README")')

    task_parser = subparsers.add_parser("task", help="Handoff Runner: 배정된 command를 받아 로컬 agent로 처리(semi-auto)")
    task_sub = task_parser.add_subparsers(dest="task_command", required=True)
    tn = task_sub.add_parser("next", help="배정된 다음 command를 lease해 보여준다")
    tn.add_argument("--capabilities", help="worker capability CSV(기본: provider.claude,provider.codex,workspace.write)")
    tp = task_sub.add_parser("prompt", help="lease한 command 프롬프트를 .dipeen/prompts/<runner>/<id>.md로 생성")
    tp.add_argument("command_id")
    tp.add_argument("--runner", default="claude", help="claude|codex|omo|gemini")
    tsub = task_sub.add_parser("submit", help="result.md + git diff를 증거로 제출")
    tsub.add_argument("command_id")
    tsub.add_argument("--from-file", dest="from_file", required=True, help="결과 요약 파일(예: result.md)")
    tsub.add_argument("--workspace", help="git diff 캡처 경로(기본: command workspace 또는 현재 디렉토리)")

    # worker (NAT Product Alpha)
    worker_parser = subparsers.add_parser("worker", help="NAT Worker 시작(command pull + 실행 + result upload)")
    worker_parser.add_argument("--once", action="store_true", help="command를 한 번만 처리")
    worker_parser.add_argument("--capabilities", help="worker capability CSV")
    worker_parser.add_argument("--idle-sleep", type=float, default=5.0, help="idle polling interval seconds")
    worker_parser.add_argument("--workspace-ref", dest="workspace_ref", help="workspace://<slug> (HQ가 아는 추상 참조)")
    worker_parser.add_argument("--repo", help="repo slug(예: ezmap-web) → repo.<slug> capability")
    worker_parser.add_argument("--workspace", help="이 workspace_ref의 로컬 경로(worker-local, HQ 비의존)")

    # run (New: CLI direct run)
    run_parser = subparsers.add_parser("run", help="즉시 태스크 실행")
    run_parser.add_argument("task", help="실행할 태스크 프롬프트")
    run_parser.add_argument("--workflow", default="default", help="워크플로우 ID (default, full-stack, review)")
    run_parser.add_argument("--model", default="anthropic", help="모델 엔진 (anthropic, gemma, gpt-4o)")
    run_parser.add_argument("--role", default=AGENT_ROLE, help="에이전트 역할")
    run_parser.add_argument("--spatial", action="store_true", help="공간 인지 활성화")
    run_parser.add_argument("--quota", type=float, default=1.0, help="최대 예산($)")
    run_parser.add_argument("--depth", type=int, default=1, help="계층적 플래닝 깊이")

    # 통합 온보딩 (Track C, study-guide §10.5) — 손으로 하던 설치/auth를 한 명령으로
    doctor_parser = subparsers.add_parser("doctor", help="시스템·러너 상태 점검(한 화면)")
    doctor_parser.add_argument("--fix", action="store_true", help="자동 수정(omo-bun BUN_BINARY 링크)")
    doctor_parser.add_argument("--runner", help="한 러너만 harmless live probe 심층 진단(installed≠runnable): claude-code|omo-opencode|omo-codex-light|hermes")
    setup_parser = subparsers.add_parser("setup", help="통합 온보딩: 러너 자동설치 + auth 안내")
    setup_parser.add_argument("--no-install", action="store_true", help="자동 설치 끄고 안내만")
    setup_parser.add_argument("--dry-run", action="store_true", help="설치 명령만 출력")
    runner_parser = subparsers.add_parser("runner", help="러너 관리(install/list)")
    runner_sub = runner_parser.add_subparsers(dest="runner_command")
    ri = runner_sub.add_parser("install", help="러너 설치")
    ri.add_argument("name", help="claude-code | omo-opencode | omo-codex-light | hermes")
    runner_sub.add_parser("list", help="러너 health 목록")

    # connect — 초대코드로 팀 합류(+자동 온보딩). "cli 다운 → 자동 온보딩 → 완료"의 마지막 고리
    connect_parser = subparsers.add_parser("connect", help="초대코드로 팀 합류(+자동 온보딩)")
    connect_parser.add_argument("url", nargs="?", help="전체 join URL (선택)")
    connect_parser.add_argument("--code", help="초대코드")
    connect_parser.add_argument("--api-url", dest="api_url", help="HQ 주소 (예: https://demo.dipeen.app)")
    connect_parser.add_argument("--no-setup", action="store_true", help="합류만, 러너 setup 생략")

    # join — 초대 URL 한 번으로 합류 + (선택)worker 시작. 새 디바이스 "원터치".
    join_parser = subparsers.add_parser("join", help="초대 URL 한 번으로 합류 + worker 시작(새 디바이스 원터치)")
    join_parser.add_argument("url", help="초대 join URL(예: https://hq/onboarding?code=ABC) 또는 코드")
    join_parser.add_argument("--api-url", dest="api_url", help="HQ 주소(url이 코드만일 때)")
    join_parser.add_argument("--role", help="역할(FE/BE/QA…) — capability role.<role>로 라우팅(Assignment Routing)")
    join_parser.add_argument("--capabilities", help="worker capability CSV(미지정 시 role로 자동 구성)")
    join_parser.add_argument("--workspace-ref", dest="workspace_ref", help="workspace://<slug> (HQ가 아는 추상 참조)")
    join_parser.add_argument("--repo", help="repo slug(예: ezmap-web) → repo.<slug> 라우팅")
    join_parser.add_argument("--workspace", help="이 workspace_ref의 로컬 경로(worker-local)")
    join_parser.add_argument("--start-worker", action="store_true", help="합류 후 바로 worker 시작")
    join_parser.add_argument("--no-setup", action="store_true", help="러너 setup 생략")

    def add_bootstrap_args(p):
        p.add_argument("--role", default="FE", help="에이전트 역할 축약명(FE/BE/QA/PM 등)")
        p.add_argument("--workspace", help="이 에이전트가 작업할 로컬 프로젝트 경로")
        p.add_argument("--network", default="cloudflare", choices=["cloudflare", "vps"], help="팀 연결 네트워크 모드")
        p.add_argument("--legacy-vps-url", help="Cloudflare 실패 시 사용할 기존 VPS HQ 주소")
        p.add_argument("--runners", help="설치/안내할 러너 CSV(기본: claude-code,omo-codex-light,omo-opencode,hermes)")
        p.add_argument("--no-install", action="store_true", help="자동 설치 끄고 매니페스트만 출력")
        p.add_argument("--dry-run", action="store_true", help="설치/.env 기록 없이 실행 계획만 출력")
        p.add_argument("--json", action="store_true", help="launcher manifest를 JSON으로 출력")

    bootstrap_parser = subparsers.add_parser("bootstrap", help="원터치 launcher 온보딩: 도구/러너/네트워크 준비")
    add_bootstrap_args(bootstrap_parser)

    launcher_parser = subparsers.add_parser("launcher", help="launcher 관리")
    launcher_sub = launcher_parser.add_subparsers(dest="launcher_command")
    launcher_bootstrap = launcher_sub.add_parser("bootstrap", help="원터치 launcher 온보딩 실행")
    add_bootstrap_args(launcher_bootstrap)

    args = parser.parse_args()

    # 통합 온보딩 명령(동기, HQ 폴링 루프 전에 처리)
    if args.command in ("doctor", "setup", "runner", "connect", "join", "bootstrap", "launcher"):
        import sys
        from . import onboarding

        def _runner_list(raw: str | None) -> list[str] | None:
            if not raw:
                return None
            return [item.strip() for item in raw.split(",") if item.strip()]

        if args.command == "doctor":
            sys.exit(onboarding.doctor(fix=args.fix, runner=args.runner))
        if args.command == "setup":
            sys.exit(onboarding.setup(auto_install=not args.no_install, dry_run=args.dry_run))
        if args.command == "connect":
            sys.exit(onboarding.connect(args.code or args.url or "", args.api_url,
                                        run_setup=not args.no_setup))
        if args.command == "join":
            # 새 디바이스 원터치: 합류(URL 파싱+.env 기록+setup) → (선택)worker 시작.
            rc = onboarding.connect(args.url, args.api_url, run_setup=not args.no_setup)
            if rc != 0:
                sys.exit(rc)
            caps = args.capabilities or _join_caps(args.role)
            wargv = ["worker", "--capabilities", caps]
            if args.workspace_ref:
                wargv += ["--workspace-ref", args.workspace_ref]
            if args.repo:
                wargv += ["--repo", args.repo]
            if args.workspace:
                wargv += ["--workspace", args.workspace]
            if args.start_worker:
                import subprocess  # connect가 .env에 쓴 DIPEEN_API_URL을 새 프로세스가 읽도록 subprocess
                print(f"\n[join] worker 시작 — capabilities={caps} (Ctrl+C로 중지)")
                sys.exit(subprocess.run([sys.executable, "-m", "dipeen_agent", *wargv]).returncode)
            print(f"\n[join] 합류 완료. 이제 실행:\n  dipeen-agent {' '.join(wargv)}")
            sys.exit(0)
        if args.command == "bootstrap" or (
            args.command == "launcher" and getattr(args, "launcher_command", None) in (None, "bootstrap")
        ):
            sys.exit(onboarding.bootstrap(
                role=getattr(args, "role", "FE"),
                workspace=getattr(args, "workspace", None),
                network=getattr(args, "network", "cloudflare"),
                legacy_vps_url=getattr(args, "legacy_vps_url", None),
                include_runners=_runner_list(getattr(args, "runners", None)),
                auto_install=not getattr(args, "no_install", False),
                dry_run=getattr(args, "dry_run", False),
                json_output=getattr(args, "json", False),
            ))
        # runner
        if getattr(args, "runner_command", None) == "install":
            sys.exit(onboarding.install_runner(args.name))
        sys.exit(onboarding.doctor())

    if args.command == "status":
        asyncio.run(cmd_status())
    elif args.command == "slash":
        import sys as _sys
        _sys.exit(asyncio.run(cmd_slash(args.text)))
    elif args.command == "task":
        import sys as _sys
        from . import handoff
        _sys.exit(asyncio.run(handoff.run(args)))
    elif args.command == "worker":
        asyncio.run(cmd_worker(args.once, args.capabilities, args.idle_sleep,
                               getattr(args, "workspace_ref", None), getattr(args, "repo", None),
                               getattr(args, "workspace", None)))
    elif args.command == "run":
        asyncio.run(cmd_run(args.task, args.workflow, args.model, args.role, args.spatial, args.quota))
    else:
        asyncio.run(cmd_start())


if __name__ == "__main__":
    run()
