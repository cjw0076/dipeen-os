"""AgentRuntime — LLM 페르소나 주입 + multi-provider 실행 + cancel 감시 + Result Distillation."""

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from dipeen_agent.client import AgentClient
from dipeen_agent.config import WORKSPACE, TRIVIAL_KEYWORDS, COMPLEX_KEYWORDS, build_cli_cmd, LLM_PROVIDER, CATEGORY_MODEL_MAP
from dipeen_agent.personas import PERSONAS, DEFAULT_PERSONA, build_workspace_files


def provision_workspace_files(workspace: Path, role: str, persona_key: str) -> None:
    """IDENTITY.md / SOUL.md / AGENTS.md 가 없으면 workspace에 생성한다."""
    try:
        workspace.mkdir(parents=True, exist_ok=True)
        for name, content in build_workspace_files(role, persona_key).items():
            path = workspace / name
            if not path.exists():
                path.write_text(content, encoding="utf-8")
                print(f"[agent] 생성: {path.name}", flush=True)
    except Exception as e:
        print(f"[agent] workspace 파일 프로비저닝 실패: {e}", flush=True)


def detect_complexity(task: dict) -> str:
    if task.get("complexity"):
        return task["complexity"]
    text = (task.get("subject", "") + " " + task.get("prompt", "")).lower()
    if any(kw in text for kw in COMPLEX_KEYWORDS):
        return "complex"
    if any(kw in text for kw in TRIVIAL_KEYWORDS):
        return "trivial"
    if len(task.get("prompt", "")) < 150:
        return "trivial"
    return "normal"


def _read_workspace_file(workspace: Path, name: str) -> str:
    """workspace 파일을 읽어 반환. 없으면 빈 문자열."""
    try:
        path = workspace / name
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return ""


def build_prompt(task: dict) -> str:
    """IDENTITY.md/SOUL.md + 페르소나 시스템 프롬프트 + 태스크 프롬프트 조합."""
    complexity = detect_complexity(task)
    persona_key = task.get("required_persona") or DEFAULT_PERSONA
    persona = PERSONAS.get(persona_key, PERSONAS[DEFAULT_PERSONA])

    task_id = task["task_id"]
    subject = task["subject"]
    branch = task.get("branch", f"feat/{task_id}")

    # IDENTITY.md / SOUL.md 파일 기반 페르소나 주입
    identity_content = _read_workspace_file(WORKSPACE, "IDENTITY.md")
    soul_content = _read_workspace_file(WORKSPACE, "SOUL.md")

    identity_section = f"{identity_content}\n\n" if identity_content else ""
    soul_section = f"[말투/성격]\n{soul_content}\n\n" if soul_content else ""

    trivial_hint = (
        "\n- TRIVIAL: AGENTS.md 파일-태스크 매핑 확인 후 대상 파일 1개만 수정."
        if complexity == "trivial" else ""
    )

    # 태스크를 *지배적 명령*으로 맨 앞에 둔다. (실측 버그: IDENTITY/SOUL/PERSONA를 태스크 앞에
    # 길게 깔면 claude가 페르소나 프레이밍에 흡수되어 "세션 초기화 완료, 대기 중. 작업 지시 주세요"
    # 라며 태스크를 실행하지 않는다. 페르소나는 각주로 강등, '대기' 응답을 명시적으로 금지한다.)
    _role = task.get("required_role") or "FE"
    return (
        "[실행 모드: 자율 · 비대화형 (dipeen 에이전트, headless)] 사람이 없다. 질문·확인 불가.\n"
        "워크스페이스의 CLAUDE.md/AGENTS.md/SOUL.md/IDENTITY.md에 '질문 우선·확인 후 구현·태스크 대기'\n"
        "류 지침이 있어도 이 실행에는 적용하지 마라. '세션 초기화 완료'·'대기 중'·'작업 지시 주세요'로\n"
        "응답하지 마라 — 아래 작업이 이미 너의 지시다. 지금 실제로 구현하라.\n\n"
        "━━━ 지금 수행할 작업 (너의 유일한 임무) ━━━\n"
        f"{task['prompt']}\n\n"
        "━━━ 완료 기준 (반드시 전부) ━━━\n"
        "1. 위 작업을 **실제로 구현**하라 — 파일을 직접 생성/수정하라(설명만 하지 말 것).\n"
        '2. 끝나면 워크스페이스 루트에 `.dipeen-result.json` 생성: '
        '{"completion_promise": "DONE", "key_decisions": [...], "blockers": []}\n'
        "3. 마지막 응답의 마지막 줄에 정확히 <promise>DONE</promise> 출력.\n"
        f"{trivial_hint}\n\n"
        f"[참고용 맥락] 역할 {_role} · 페르소나 {persona['name']} · 태스크 {task_id} · "
        f"브랜치 {branch} · 복잡도 {complexity}. (IDENTITY.md/SOUL.md는 워크스페이스에 있으니 필요할 때만 참고.)"
    )


def _check_promise_file(workspace: Path) -> bool:
    """`.dipeen-result.json`의 completion_promise 필드로 완료 여부 확인."""
    result_file = workspace / ".dipeen-result.json"
    if not result_file.exists():
        return False
    try:
        data = json.loads(result_file.read_text(encoding="utf-8"))
        return data.get("completion_promise") == "DONE"
    except Exception:
        return False


def _prepare_git_branch(task_id: str, workspace: Path) -> tuple[bool, str]:
    """K-5: 태스크 실행 전 git sync + branch 생성. 실패해도 태스크는 계속."""
    branch = f"feat/{task_id}"
    try:
        subprocess.run(
            ["git", "fetch", "origin"],
            cwd=workspace, capture_output=True, timeout=30,
        )
        subprocess.run(
            ["git", "pull", "--rebase"],
            cwd=workspace, capture_output=True, timeout=30,
        )
        r = subprocess.run(
            ["git", "checkout", branch],
            cwd=workspace, capture_output=True, timeout=10,
        )
        if r.returncode != 0:
            subprocess.run(
                ["git", "checkout", "-b", branch],
                cwd=workspace, capture_output=True, timeout=10,
            )
        return True, branch
    except Exception:
        return False, branch


def _push_and_create_pr(task_id: str, subject: str, workspace: Path) -> str | None:
    """K-5: 완료 후 branch push + gh pr create. pr_url 반환, 실패 시 None."""
    if os.environ.get("DIPEEN_ALLOW_AUTO_PR", "").lower() not in ("1", "true", "yes"):
        return None
    branch = f"feat/{task_id}"
    try:
        subprocess.run(
            ["git", "push", "origin", branch],
            cwd=workspace, capture_output=True, timeout=30,
        )
        r = subprocess.run(
            ["gh", "pr", "create",
             "--title", subject,
             "--body", f"Auto-created by dipeen agent\n\nTask: {task_id}",
             "--head", branch],
            cwd=workspace, capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0:
            return r.stdout.strip()
    except Exception:
        pass
    return None


def extract_artifacts(workspace: Path) -> dict:
    """Result Distillation: 실행 후 git diff + .dipeen-result.json으로 최소 핵심 추출.

    전체 실행 로그 대신 PM이 follow-up에 필요한 것만 distill.
    - changed_files: git diff --name-only HEAD (파일 포인터)
    - key_decisions: .dipeen-result.json에 에이전트가 직접 기록
    - blockers: 완료 못한 것 / 다음 에이전트가 알아야 할 것
    - references: { "이름": "파일:라인" } 형태 포인터
    """
    artifacts: dict = {
        "changed_files": [],
        "key_decisions": [],
        "blockers": [],
        "references": {},
    }

    # 1. git diff로 변경 파일 추출
    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=workspace, capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            artifacts["changed_files"] = [f.strip() for f in r.stdout.splitlines() if f.strip()]
    except Exception:
        pass

    # 2. .dipeen-result.json: 에이전트가 선택적으로 남기는 structured 결과
    result_file = workspace / ".dipeen-result.json"
    if result_file.exists():
        try:
            data = json.loads(result_file.read_text(encoding="utf-8"))
            for key in ("key_decisions", "blockers", "references", "completion_promise", "subtasks"):
                if key in data:
                    artifacts[key] = data[key]
            result_file.unlink()  # 소비 후 삭제
        except Exception:
            pass

    return artifacts


async def _question_monitor(
    task_id: str,
    workspace: Path,
    client: AgentClient,
    room_id: str,
    stop_event: asyncio.Event,
) -> None:
    """K-2: subprocess 실행 중 .dipeen-question.json 감지 → 채팅 전달 → 답변 대기."""
    sent_questions: set[str] = set()

    while not stop_event.is_set():
        await asyncio.sleep(5)
        q_file = workspace / ".dipeen-question.json"
        if not q_file.exists():
            continue

        try:
            q_data = json.loads(q_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        question = q_data.get("question", "")
        q_key = question[:50]
        if q_key in sent_questions:
            continue
        sent_questions.add(q_key)

        # 1. 채팅방에 질문 전달 (sender_type="question")
        context = q_data.get("context", "")
        options = q_data.get("options", [])
        chat_text = f"❓ **질문 (Task `{task_id}`)**: {question}"
        if context:
            chat_text += f"\n> 맥락: {context}"
        if options:
            for i, opt in enumerate(options):
                chat_text += f"\n> {i + 1}. {opt}"
        await client.send_chat(chat_text, room_id=room_id, task_id=task_id)

        # 2. API에 질문 등록
        try:
            await client._http.post(
                f"/api/tasks/{task_id}/question",
                json={"question": question, "context": context, "options": options},
            )
        except Exception:
            pass

        # 3. 답변 폴링 (최대 10분 = 20 * 30초)
        answer = None
        for _ in range(20):
            if stop_event.is_set():
                break
            try:
                r = await client._http.get(
                    f"/api/tasks/{task_id}/answer",
                    params={"timeout": 30},
                    timeout=35.0,
                )
                if r.status_code == 200:
                    answer = r.json().get("answer")
                    if answer:
                        break
            except Exception:
                await asyncio.sleep(5)

        # 4. 답변 파일 기록 → subprocess가 읽음
        answer_file = workspace / ".dipeen-answer.json"
        if answer:
            answer_file.write_text(
                json.dumps({"answer": answer}, ensure_ascii=False),
                encoding="utf-8",
            )
            await client.send_chat(
                f"💬 답변 전달 완료 (Task `{task_id}`): {answer[:100]}",
                room_id=room_id,
            )
        else:
            answer_file.write_text(
                json.dumps({"answer": "10분 내 답변 없음 — 최선의 판단으로 진행", "timeout": True}),
                encoding="utf-8",
            )

        # 5. 처리된 질문 파일 삭제
        try:
            q_file.unlink()
        except Exception:
            pass


class AgentRuntime:
    def __init__(self, client: AgentClient):
        self.client = client
        self.config = {
            "workflow": "default",
            "model": "anthropic",
            "role": "coder",
            "spatial": False,
            "quota": 1.0
        }

    def set_config(self, config: dict) -> None:
        """CLI 인자 등 외부 설정을 주입."""
        self.config.update(config)

    async def execute_task(self, task: dict) -> dict:
        """태스크 실행. 워크플로우 엔진을 통해 분기 처리."""
        workflow = self.config.get("workflow", "default")
        
        # 모델 강제 주입 (CLI 인자가 있으면 우선)
        if self.config.get("model"):
            task["llm_provider"] = self.config["model"].split(":")[0] if ":" in self.config["model"] else self.config["model"]
            if ":" in self.config["model"]:
                task["model"] = self.config["model"].split(":")[1]

        print(f"[agent] Workflow: {workflow} | Provider: {task.get('llm_provider')}", flush=True)

        if workflow == "review":
            return await self._workflow_review(task)
        elif workflow == "full-stack":
            return await self._workflow_full_stack(task)
        
        # 기본 워크플로우
        provider = (task.get("llm_provider") or LLM_PROVIDER).lower()
        if provider != "anthropic":
            return await self._execute_sdk(task, provider)
        # anthropic provider → RunnerAdapter 라우팅 (W0).
        # claude-code/omo-opencode는 _execute_subprocess 재사용(동작 불변),
        # omo-codex-light/hermes는 전용 어댑터. truth·판정은 HQ(어댑터는 실행만).
        from .runners import get_adapter, resolve_runner_name
        from .runners.base import RunContext
        runner_name = resolve_runner_name(task, self.config)
        adapter = get_adapter(runner_name)
        ctx = RunContext(workspace=WORKSPACE, runtime=self, config=self.config,
                         agent_id=getattr(self.client, "agent_id", "unknown"))
        return await adapter.execute(task, ctx)

    async def _workflow_review(self, task: dict) -> dict:
        """리뷰 워크플로우: 분석 -> 제안 -> 수정 루프."""
        print(f"[agent] Running Code Review Workflow...", flush=True)
        task["prompt"] = f"[REVIEW MODE]\n{task['prompt']}\n\n결과물에 반드시 보안/품질 체크리스트를 포함하세요."
        return await self._execute_subprocess(task)

    async def _workflow_full_stack(self, task: dict) -> dict:
        """풀스택 워크플로우: 기획 -> 구현 루프."""
        print(f"[agent] Running Full-stack Workflow...", flush=True)
        # 여기서 계층적 플래닝 로직(depth 처리 등)을 구현 가능
        return await self._execute_subprocess(task)

    async def _execute_sdk(self, task: dict, provider: str) -> dict:
        """P-2: 비-Anthropic 프로바이더 — openai tool_calls 루프 (claw-code 패턴)."""
        from dipeen_agent.llm import run_agent_loop as call_llm_for_task

        task_id = task["task_id"]
        room_id = task.get("room_id", "general")

        print(f"[agent] ▶ {task_id} [SDK/{provider}]", flush=True)
        print(f"[agent]   Subject: {task['subject']}", flush=True)

        await self.client.send_chat(
            f"▶ `{task_id}` 시작 [{provider.upper()}]: {task['subject']}",
            room_id=room_id,
        )

        # K-5: git branch 준비
        git_ok, _branch = _prepare_git_branch(task_id, WORKSPACE)
        if not git_ok:
            print(f"[agent] ⚠ git branch 준비 실패 (계속 진행): {task_id}", flush=True)

        # W-2: 도구 사용을 채팅방에 구조화된 메타데이터로 보고
        async def _chat_cb(text: str, metadata: dict | None = None) -> None:
            await self.client.send_chat(text, room_id=room_id, metadata=metadata)

        result = await call_llm_for_task(task, WORKSPACE, provider, chat_callback=_chat_cb)

        # K-5: PR 생성
        if result["status"] == "done":
            pr_url = _push_and_create_pr(task_id, task["subject"], WORKSPACE)
            if pr_url:
                result["artifacts"]["pr_url"] = pr_url

        status = result["status"]
        icon = "✅" if status == "done" else "❌"
        summary = result.get("summary", "")

        if status == "done":
            changed = len(result["artifacts"].get("changed_files", []))
            pr_note = f"\n> PR: {result['artifacts'].get('pr_url', '')}" if result["artifacts"].get("pr_url") else ""
            await self.client.send_chat(
                f"{icon} `{task_id}` 완료 [{provider.upper()}]: {task['subject']} (변경 {changed}개){pr_note}",
                room_id=room_id,
            )
        else:
            blockers = result["artifacts"].get("blockers", [])
            blocker_note = f"\n> {blockers[0]}" if blockers else ""
            await self.client.send_chat(
                f"{icon} `{task_id}` 오류 [{provider.upper()}]: {summary}{blocker_note}",
                room_id=room_id,
            )

        return result

    async def _execute_subprocess(self, task: dict) -> dict:
        """Anthropic(Claude Code) 경로 — subprocess 실행."""
        task_id = task["task_id"]
        complexity = detect_complexity(task)
        persona_key = task.get("required_persona") or DEFAULT_PERSONA
        provider = task.get("llm_provider") or LLM_PROVIDER
        prompt = build_prompt(task)

        room_id = task.get("room_id", "general")

        # J-3: 복잡도별 모델 분기 (Claude Code CLI는 ANTHROPIC_MODEL 참조)
        model_for_complexity = CATEGORY_MODEL_MAP.get(complexity, CATEGORY_MODEL_MAP.get("normal", ""))

        print(f"[agent] ▶ {task_id}", flush=True)
        print(f"[agent]   Subject:    {task['subject']}", flush=True)
        print(f"[agent]   Complexity: {complexity.upper()}", flush=True)
        print(f"[agent]   Persona:    {persona_key} / Provider: {provider}", flush=True)

        # K-1/W-2: 시작 보고 → 채팅방 (구조화)
        await self.client.send_chat(
            f"▶ `{task_id}` 시작: {task['subject']} [{complexity.upper()}]",
            room_id=room_id,
            metadata={
                "kind": "started",
                "task_id": task_id,
                "subject": task["subject"],
                "complexity": complexity,
                "model": model_for_complexity,
            },
        )

        # K-5: git sync + branch 생성
        git_ok, _branch = _prepare_git_branch(task_id, WORKSPACE)
        if not git_ok:
            print(f"[agent] ⚠ git branch 준비 실패 (계속 진행): {task_id}", flush=True)
        if model_for_complexity:
            os.environ["ANTHROPIC_MODEL"] = model_for_complexity
            print(f"[agent]   Model:      {model_for_complexity} (complexity={complexity})", flush=True)

        cmd = build_cli_cmd(provider, prompt)
        _cflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        # 구독(claude login) 모드: ANTHROPIC_API_KEY 제거 → claude가 구독 사용 (API 크레딧 0).
        # 키 BYOK를 쓰려면 AGENT_USE_SUBSCRIPTION 미설정(기존 동작 유지).
        _sub_env = dict(os.environ)
        if os.getenv("AGENT_USE_SUBSCRIPTION"):
            _sub_env.pop("ANTHROPIC_API_KEY", None)
        # 실시간 디버그: subprocess stdout을 캡처해 LOG_STREAM으로 흘린다(중앙 Dipeen UI에서
        # "에이전트가 지금 무엇을 하는지" 추적 — 이게 없으면 실패 원인이 UI에서 안 보인다).
        proc = subprocess.Popen(
            cmd, cwd=WORKSPACE, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=_cflags, env=_sub_env,
        )
        # 드레이너 스레드 — 파이프가 차서 subprocess가 멈추지 않도록 계속 읽어 버퍼에 쌓는다.
        from collections import deque
        out_buf: deque[str] = deque(maxlen=400)
        def _drain_stdout():
            try:
                assert proc.stdout is not None
                for line in proc.stdout:
                    out_buf.append(line.rstrip("\n"))
            except Exception:
                pass
        out_thread = threading.Thread(target=_drain_stdout, daemon=True)
        out_thread.start()

        # cancel 감시 스레드
        cancelled_flag: list[bool] = []
        cancel_thread = threading.Thread(
            target=self._watch_cancel,
            args=(task_id, proc, cancelled_flag),
            daemon=True,
        )
        cancel_thread.start()

        # K-2: 질문 감시 asyncio 태스크
        stop_event = asyncio.Event()
        monitor_task = asyncio.create_task(
            _question_monitor(task_id, WORKSPACE, self.client, room_id, stop_event)
        )

        # 프로세스 완료 대기 (타임아웃 + 주기적 진행 보고)
        max_duration = task.get("max_duration_sec", 600) or 600
        _PROGRESS_INTERVAL = 15  # 초마다 진행 보고
        elapsed = 0
        last_report = 0
        returncode = None

        while elapsed < max_duration:
            rc = proc.poll()
            if rc is not None:
                returncode = rc
                break
            await asyncio.sleep(1)
            elapsed += 1

            # W-2: 주기적 진행 보고 (구조화된 메타데이터 + Hermes LOG_STREAM)
            if elapsed - last_report >= _PROGRESS_INTERVAL:
                last_report = elapsed
                await self.client.heartbeat("working", task_id)
                # git diff --name-only로 변경 파일 목록 추출
                files_changed: list[str] = []
                changed_count = 0
                _IGNORE_PATTERNS = (".pyc", "__pycache__", ".db", ".sqlite", ".log")
                try:
                    diff_r = subprocess.run(
                        ["git", "diff", "--name-only"],
                        cwd=WORKSPACE, capture_output=True, text=True, timeout=5,
                    )
                    raw_files = [f.strip() for f in diff_r.stdout.strip().splitlines() if f.strip()]
                    files_changed = [f for f in raw_files if not any(p in f for p in _IGNORE_PATTERNS)]
                    changed_count = len(files_changed)
                except Exception:
                    pass
                status_msg = f"⏳ `{task_id}` 진행 중... ({elapsed}s, {changed_count} files)"
                
                # HTTP Chat 보고
                await self.client.send_chat(
                    status_msg, room_id=room_id,
                    metadata={
                        "kind": "progress",
                        "task_id": task_id,
                        "elapsed_sec": elapsed,
                        "files_changed": files_changed[:20],
                        "changed_count": changed_count,
                        "model": model_for_complexity,
                    },
                )
                
                # Hermes WSS 로그 스트림 — 상태 + 실제 실행 출력 tail(지금 무엇을 하는지)
                _tail = "\n".join(list(out_buf)[-8:])
                await self.client.send_log(
                    text=(f"{status_msg}\n{_tail}" if _tail else status_msg),
                    task_id=task_id,
                    changed_files=files_changed,
                    tests={"running": True},
                )

        if returncode is None:
            # 타임아웃
            print(f"[agent] ⏰ 타임아웃 ({max_duration}s): {task_id}", flush=True)
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            returncode = -1
            cancelled_flag.append(True)
        cancel_thread.join(timeout=3)

        # K-2: 프로세스 종료 → 질문 감시 중단
        stop_event.set()
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass

        was_cancelled = bool(cancelled_flag)

        # Result Distillation: promise 판정 전에 먼저 추출 (completion_promise 필드 필요)
        artifacts = extract_artifacts(WORKSPACE) if not was_cancelled else {}
        promise_done = (artifacts.get("completion_promise") == "DONE") if not was_cancelled else False
        success = (returncode == 0 or promise_done) and not was_cancelled

        if was_cancelled:
            status, icon = "cancelled", "🛑"
        elif success:
            status, icon = "done", "✅"
        else:
            status, icon = "error", "❌"

        if promise_done and returncode != 0:
            print(f"[agent] {icon} {task_id} → {status} (rc={returncode}, promise=DONE)", flush=True)
        else:
            print(f"[agent] {icon} {task_id} → {status} (rc={returncode})", flush=True)

        # 최종 실행 출력 tail을 LOG_STREAM으로 — 15초 미만 짧은 태스크도 UI에서 무엇을 했는지 보이게.
        try:
            out_thread.join(timeout=2)
        except Exception:
            pass
        _final_tail = "\n".join(list(out_buf)[-20:])
        if _final_tail:
            try:
                await self.client.send_log(
                    text=f"[{status} rc={returncode}] {task_id}\n{_final_tail}",
                    task_id=task_id, changed_files=[], tests={"final": status},
                )
            except Exception:
                pass

        # K-1: 완료/실패/취소 보고 → 채팅방
        if was_cancelled:
            await self.client.send_chat(
                f"🛑 `{task_id}` 취소됨: {task['subject']}",
                room_id=room_id,
            )
        elif success:
            # K-5: PR 생성
            pr_url = _push_and_create_pr(task_id, task["subject"], WORKSPACE)
            if pr_url:
                artifacts["pr_url"] = pr_url

            changed = len(artifacts.get("changed_files", []))
            files_note = f" (변경 {changed}개)" if changed else ""
            pr_note = f"\n> PR: {pr_url}" if pr_url else ""
            await self.client.send_chat(
                f"✅ `{task_id}` 완료: {task['subject']}{files_note}{pr_note}",
                room_id=room_id,
            )
        else:
            blockers = artifacts.get("blockers", [])
            blocker_note = f"\n> {blockers[0]}" if blockers else ""
            await self.client.send_chat(
                f"❌ `{task_id}` 오류: {task['subject']}{blocker_note}",
                room_id=room_id,
            )

        return {
            "status": status,
            "summary": f"{task['subject']} {'취소됨' if was_cancelled else '처리 완료'}",
            "tests_passed": success,
            "artifacts": artifacts,
            "subtasks": artifacts.get("subtasks", []),  # K-8
        }

    def _watch_cancel(self, task_id: str, proc: subprocess.Popen,
                      cancelled_flag: list) -> None:
        """별도 스레드: API를 폴링하여 cancel 감지 → proc 종료."""
        import httpx

        url = f"{self.client.api_url}/api/tasks/{task_id}"
        while proc.poll() is None:
            try:
                r = httpx.get(url, timeout=5.0)
                if r.status_code == 200 and r.json().get("status") == "cancelled":
                    print(f"[agent] 🛑 취소 감지: {task_id}", flush=True)
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    cancelled_flag.append(True)
                    return
            except Exception:
                pass
            time.sleep(2)
