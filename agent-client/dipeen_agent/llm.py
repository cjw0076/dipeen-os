"""
P-2: claw-code 패턴 — openai tool_calls 루프 기반 에이전트 실행.

참조:
  - claw-code-main/src/query_engine.py: max_turns, stop_reason, compact
  - not-claude-code-emulator-master/src/routes/messages.ts: tool_use 루프
  - claw-code-main/src/tools.py: 6개 도구 정의

흐름:
  1. LLM 호출 (system + task + TOOLS)
  2. tool_calls 있으면 execute_tool() → tool 결과 메시지 추가 → 재호출
  3. stop_reason == stop 또는 MAX_ITERATIONS 도달 시 종료
  4. .dipeen-result.json 기록 (completion_promise: "DONE")
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from dipeen_agent.config import AGENT_MODEL, PROVIDER_CONFIGS
from dipeen_agent.tools import TOOLS, execute_tool

MAX_ITERATIONS = 15
_ITERATION_BY_COMPLEXITY = {"quick": 5, "trivial": 5, "normal": 10, "deep": 15}  # OPT-5

# OPT-3: 도구별 차등 truncation
_TOOL_OUTPUT_LIMITS: dict[str, int] = {
    "bash_execute":  3000,
    "file_read":     6000,
    "file_write":     500,
    "file_patch":     500,
    "list_dir":      2000,
    "search_files":  3000,
}
_MAX_TOOL_OUTPUT = 4000  # fallback

_SYSTEM_PROMPT_BASE = """\
You are a coding agent integrated into a team development workflow.
You have access to tools: bash_execute, file_read, file_write, file_patch, list_dir, search_files.

Workflow:
1. Read the task description carefully
2. Use list_dir / file_read / search_files to understand the codebase
3. Make changes using file_write or file_patch
4. Verify with bash_execute (run tests, build, etc.)
5. When done, write .dipeen-result.json:
   {"completion_promise": "DONE", "key_decisions": ["..."], "blockers": [], "changed_files": [...]}

Rules:
- Use tools iteratively — read before writing
- Prefer file_patch for small edits, file_write for new files or large rewrites
- Always verify changes work (build/test if applicable)
- If you cannot complete the task, still write .dipeen-result.json with blockers filled in
"""


def _build_system_prompt(workspace: Path) -> str:
    """P-3-2: IDENTITY.md + SOUL.md + README 주입으로 시스템 프롬프트 고도화."""
    parts = [_SYSTEM_PROMPT_BASE]

    # IDENTITY.md (에이전트 메타데이터)
    identity = workspace / "IDENTITY.md"
    if identity.exists():
        try:
            content = identity.read_text(encoding="utf-8").strip()
            if content:
                parts.append(f"\n## Your Identity\n{content[:500]}")
        except Exception:
            pass

    # SOUL.md (에이전트 역할/성격)
    soul = workspace / "SOUL.md"
    if soul.exists():
        try:
            content = soul.read_text(encoding="utf-8").strip()
            if content:
                parts.append(f"\n## Your Role\n{content[:500]}")
        except Exception:
            pass

    # README.md (프로젝트 컨텍스트)
    readme = workspace / "README.md"
    if readme.exists():
        try:
            content = readme.read_text(encoding="utf-8").strip()
            if content:
                parts.append(f"\n## Project Context\n{content[:800]}")
        except Exception:
            pass

    # CLAUDE.md (프로젝트 규칙)
    claude_md = workspace / "CLAUDE.md"
    if claude_md.exists():
        try:
            content = claude_md.read_text(encoding="utf-8").strip()
            if content:
                parts.append(f"\n## Project Rules\n{content[:800]}")
        except Exception:
            pass

    return "\n".join(parts)


def _tool_arg_hint(tool_name: str, args: dict) -> str:
    """도구 인자를 채팅 보고용 짧은 텍스트로 요약."""
    if tool_name == "bash_execute":
        cmd = args.get("command", "")
        return cmd[:80] + ("..." if len(cmd) > 80 else "")
    if tool_name == "file_read":
        return args.get("path", "?")
    if tool_name == "file_write":
        return args.get("path", "?")
    if tool_name == "file_patch":
        return args.get("path", "?")
    if tool_name == "list_dir":
        return args.get("path", ".")
    if tool_name == "search_files":
        return f'"{args.get("pattern", "")}" in {args.get("path", ".")}'
    return str(list(args.keys()))[:60]


def _list_workspace_files(workspace: Path, max_files: int = 150) -> str:
    """P-3-1: workspace 컨텍스트 — 최근 변경 파일 우선 + tree 구조."""
    sections: list[str] = []

    # 1) 최근 변경 파일 (git log 기반, 가장 중요)
    try:
        r = subprocess.run(
            ["git", "log", "--oneline", "-5", "--name-only", "--diff-filter=ACMR"],
            cwd=workspace, capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            recent: list[str] = []
            for line in r.stdout.splitlines():
                line = line.strip()
                if line and not line[0].isdigit() and "/" in line or "." in line:
                    if line not in recent:
                        recent.append(line)
            if recent:
                sections.append("## Recently Changed Files\n" + "\n".join(recent[:20]))
    except Exception:
        pass

    # 2) 전체 파일 목록 (git ls-files)
    try:
        r = subprocess.run(
            ["git", "ls-files"],
            cwd=workspace, capture_output=True, text=True, timeout=10,
        )
        if r.returncode == 0:
            files = [f.strip() for f in r.stdout.splitlines() if f.strip()]
            if len(files) > max_files:
                files = files[:max_files] + [f"... ({len(files) - max_files} more)"]
            sections.append("## All Tracked Files\n" + "\n".join(files))
    except Exception:
        pass

    # 3) Directory tree (2-level depth)
    try:
        import os as _os
        tree_lines: list[str] = []
        for entry in sorted(_os.listdir(workspace)):
            if entry.startswith(".") or entry in ("node_modules", "__pycache__", ".next", "dist", "build"):
                continue
            full = workspace / entry
            if full.is_dir():
                sub = sorted(e for e in _os.listdir(full)
                             if not e.startswith(".") and e not in ("node_modules", "__pycache__"))[:10]
                tree_lines.append(f"{entry}/")
                for s in sub:
                    sfull = full / s
                    tree_lines.append(f"  {s}/" if sfull.is_dir() else f"  {s}")
            else:
                tree_lines.append(entry)
        if tree_lines:
            sections.append("## Directory Structure\n" + "\n".join(tree_lines[:60]))
    except Exception:
        pass

    return "\n\n".join(sections) if sections else "(empty workspace)"


def _resolve_model(provider: str, task: dict | None = None) -> str:
    """우선순위: 1. task['model'] (CLI) | 2. AGENT_MODEL (Env) | 3. default (Config)"""
    if task and task.get("model"):
        return task["model"]
    if AGENT_MODEL:
        return AGENT_MODEL
    return PROVIDER_CONFIGS.get(provider, {}).get("default_model", "")


async def run_agent_loop(task: dict, workspace: Path, provider: str,
                         chat_callback=None) -> dict:
    """
    openai-compatible tool_calls 루프.

    Returns dict compatible with runtime.py:
      {"status", "summary", "tests_passed", "artifacts", "subtasks"}
    """
    try:
        from openai import AsyncOpenAI
    except ImportError:
        return _error_result("openai 패키지 미설치. pip install openai 실행 후 재시도.")

    cfg = PROVIDER_CONFIGS.get(provider)
    if not cfg:
        return _error_result(f"알 수 없는 프로바이더: {provider}")

    base_url = cfg["base_url"]
    api_key = cfg["api_key"]
    model = _resolve_model(provider, task)

    if not base_url:
        return _error_result(f"{provider}: base_url 미설정 (OPENAI_COMPAT_BASE_URL 확인)")
    if not model:
        return _error_result(f"{provider}: AGENT_MODEL 미설정")
    if not api_key or (provider not in ("ollama",) and not api_key.strip()):
        return _error_result(f"{provider}: API key 미설정")

    # OPT-5: 복잡도별 iteration 제한
    complexity = task.get("complexity", "normal") or "normal"
    max_iter = _ITERATION_BY_COMPLEXITY.get(complexity, MAX_ITERATIONS)
    print(f"[llm] {provider}/{model} agent loop 시작 (max {max_iter}회, {complexity})", flush=True)

    workspace_overview = _list_workspace_files(workspace)
    system_prompt = _build_system_prompt(workspace)
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"## Task\n"
                f"Task ID: {task.get('task_id', '')}\n"
                f"Subject: {task.get('subject', '')}\n\n"
                f"{task.get('prompt', '')}\n\n"
                f"## Workspace Files (use file_read to read any of these)\n"
                f"{workspace_overview}"
            ),
        },
    ]

    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    final_content = ""
    iterations = 0

    try:
        for i in range(max_iter):
            iterations = i + 1
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.2,
                timeout=120,
            )

            choice = resp.choices[0]
            response_message = choice.message
            final_content = response_message.content or ""

            tool_calls = response_message.tool_calls or []

            # assistant 메시지를 dict로 변환하여 추가
            msg_dict: dict = {"role": "assistant", "content": final_content}
            if tool_calls:
                msg_dict["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in tool_calls
                ]
            messages.append(msg_dict)

            if not tool_calls:
                # stop 또는 max_tokens — 루프 종료
                print(f"[llm] 루프 종료 (stop, {iterations}회)", flush=True)
                break

            # 도구 실행
            for tc in tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_name = tc.function.name
                # P-5-2: 도구 사용을 채팅방에 실시간 보고
                arg_hint = _tool_arg_hint(tool_name, args)
                print(f"[llm]   🔧 {tool_name}: {arg_hint}", flush=True)
                if chat_callback:
                    try:
                        await chat_callback(
                            f"🔧 [{tool_name}] {arg_hint}",
                            {"kind": "tool_use", "task_id": task.get("task_id", ""), "tool_name": tool_name, "tool_args": arg_hint},
                        )
                    except Exception:
                        pass
                result = execute_tool(tool_name, args, workspace)
                limit = _TOOL_OUTPUT_LIMITS.get(tool_name, _MAX_TOOL_OUTPUT)
                if len(result) > limit:
                    if tool_name == "bash_execute":
                        # 빌드 에러는 끝에 나오므로 마지막 우선
                        lines = result.splitlines()
                        result = "\n".join(lines[:5] + ["... (truncated)"] + lines[-40:])
                    elif tool_name == "file_read":
                        # 첫 + 마지막 보존
                        lines = result.splitlines()
                        result = "\n".join(lines[:80] + [f"... ({len(lines)-100} lines truncated)"] + lines[-20:])
                    else:
                        result = result[:limit] + "\n... (truncated)"

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
        else:
            print(f"[llm] MAX_ITERATIONS({max_iter}) 도달 — 강제 종료", flush=True)

    except Exception as e:
        return _error_result(f"{provider} API 호출 실패: {e}")

    # .dipeen-result.json 확인 (LLM이 직접 작성했으면 그것 사용)
    result_file = workspace / ".dipeen-result.json"
    if result_file.exists():
        try:
            result_data = json.loads(result_file.read_text(encoding="utf-8"))
            promise = result_data.get("completion_promise", "")
            summary = result_data.get("key_decisions", [""])
            summary_text = summary[0] if summary else "완료"
            changed = result_data.get("changed_files", [])
            blockers = result_data.get("blockers", [])
            subtasks = result_data.get("subtasks", [])

            print(f"[llm] 완료 (iterations={iterations}, changed={len(changed)})", flush=True)
            return {
                "status": "done" if promise == "DONE" else "error",
                "summary": summary_text,
                "tests_passed": promise == "DONE",
                "artifacts": {
                    "completion_promise": promise,
                    "changed_files": changed,
                    "key_decisions": summary,
                    "blockers": blockers,
                },
                "subtasks": subtasks,
            }
        except Exception:
            pass

    # LLM이 result json을 안 썼으면 — 완료를 *조작하지 않는다*. promise 미기재 = 미완료 신호.
    # (이전 코드는 completion_promise="DONE"을 임의 주입해 Gatekeeper의 PROMISE_FALSE를
    #  비-Anthropic 경로에서 무력화했다. 자기보고 불신·oracle 정합을 위해 제거.)
    # 루프는 끝났으나(에러 아님) 완료 약속이 없으므로 promise=None으로 보고 → HQ가 PROMISE_FALSE 판정/복구.
    print(f"[llm] .dipeen-result.json 없음 — promise 미기재로 보고(조작 안 함, iterations={iterations})", flush=True)
    return {
        "status": "done",   # 루프 정상 종료. 완료 여부는 HQ가 promise로 판정한다.
        "summary": final_content[:200] if final_content else "(완료 신호 없음)",
        "tests_passed": False,
        "artifacts": {
            "completion_promise": None,   # 조작 금지 — 모델이 DONE을 명시하지 않았다
            "changed_files": [],
            "key_decisions": [final_content[:200]] if final_content else [],
            "blockers": ["완료 약속(<promise>DONE</promise> / .dipeen-result.json) 미기재"],
        },
        "subtasks": [],
    }


def _error_result(msg: str) -> dict:
    return {
        "status": "error",
        "summary": msg,
        "tests_passed": False,
        "artifacts": {"blockers": [msg]},
        "subtasks": [],
    }
