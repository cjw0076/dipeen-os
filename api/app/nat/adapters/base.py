"""AgentAdapter base (M2 / §10) — Adapter = *실행만*. run(invocation)->RawAgentOutput.

원칙(Isolation): 어댑터는 task state/artifact/memory/retry를 절대 모른다. RawAgentOutput(raw
stdout/exit/changed_files)만 낸다. provider별 차이는 argv 하나뿐(claude -p / codex exec) →
공통부 CliExecAdapter에 모으고, claude.py/codex.py는 argv만 특수화한다.

테스트 가능성: 실제 CLI는 비결정적·구독 의존 → CommandRunner를 주입해 hermetic하게 검증한다.
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

from ..contracts import AgentInvocation, RawAgentOutput


@dataclass
class ExecResult:
    """CommandRunner 1회 실행의 raw 결과(=어댑터가 보는 전부)."""
    exit_code: int
    stdout: str = ""
    stderr: str = ""


@runtime_checkable
class CommandRunner(Protocol):
    """argv를 cwd/env로 실행하고 ExecResult를 낸다. 기본은 default_runner(asyncio subprocess).
    테스트는 가짜 러너를 주입해 명령 구성·조립을 검증한다."""

    async def __call__(self, argv: list[str], *, cwd: str, env: dict[str, str],
                       timeout_sec: Optional[int]) -> ExecResult: ...


@runtime_checkable
class AgentAdapter(Protocol):
    """run(invocation)->RawAgentOutput + health(). *실행만* — Core 타입을 만들지 않는다(§10)."""
    name: str

    async def run(self, invocation: AgentInvocation) -> RawAgentOutput: ...
    async def health(self) -> bool: ...


def child_env(overrides: dict[str, str]) -> dict[str, str]:
    """현재 env에 override 적용. 값이 ""면 키 제거(구독 크레딧0 = ANTHROPIC_API_KEY="" → unset)."""
    env = dict(os.environ)
    for k, v in overrides.items():
        if v == "":
            env.pop(k, None)
        else:
            env[k] = v
    return env


def detect_changed_files(workspace_root: str | Path) -> list[str]:
    """워크스페이스에서 실제 만진 파일(생성·수정·삭제). `git status --porcelain` raw 관찰 —
    artifact가 아니다(번역은 M3 Inbound). git 아니거나 실패면 []."""
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=str(workspace_root), capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace",          # Windows 로케일(cp949) 디코드로 UTF-8 파일명 깨지는 것 방지
        )
        if r.returncode != 0:
            return []
    except Exception:
        return []
    out: list[str] = []
    for line in r.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:] if len(line) > 3 else line.strip()   # porcelain v1: 2상태문자+공백+경로
        if " -> " in path:                                   # rename: old -> new
            path = path.split(" -> ", 1)[1]
        out.append(path.strip().strip('"'))
    return out


def _parse_shim(cmd_path: Path) -> Optional[list[str]]:
    """npm `.cmd` 셰임에서 실제 실행 토큰 추출. 직접 .exe → [exe], node 스크립트 → [node, script.js].
    (claude.cmd=`"%dp0%\\...\\claude.exe"`, codex.cmd=`"%_prog%" "%dp0%\\...\\codex.js"`)"""
    try:
        text = cmd_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    base = cmd_path.parent
    m = re.search(r'%dp0%\\([^"\r\n]+\.exe)"', text, re.IGNORECASE)
    if m and (base / m.group(1)).exists():
        return [str(base / m.group(1))]
    m = re.search(r'%dp0%\\([^"\r\n]+\.js)"', text, re.IGNORECASE)
    if m and (base / m.group(1)).exists():
        node = base / "node.exe"
        node_tok = str(node) if node.exists() else (shutil.which("node") or "node")
        return [node_tok, str(base / m.group(1))]
    return None


def resolve_launcher(name: str) -> list[str]:
    """CLI 이름 → 실행 토큰 리스트. Windows npm 셰임(.cmd/.ps1)을 실제 .exe/node-script로 우회
    (create_subprocess_exec가 .cmd/.ps1을 직접 못 도는 문제). non-Windows면 바이너리 경로 그대로.
    CLAUDE.md 'opencode는 .exe 직접 경로로 우회' 패턴의 일반화."""
    w = shutil.which(name)
    if not w:
        return [name]
    p = Path(w)
    sibling_cmd = p if p.suffix.lower() == ".cmd" else p.with_suffix(".cmd")
    if sibling_cmd.exists():                       # 셰임이면 .cmd를 파싱(실제 .exe/.js 경로가 거기 있음)
        parsed = _parse_shim(sibling_cmd)
        if parsed:
            return parsed
    return [w]                                     # 실제 바이너리(.exe/Linux/Mac) → 그대로


async def default_runner(argv: list[str], *, cwd: str, env: dict[str, str],
                         timeout_sec: Optional[int]) -> ExecResult:
    """실제 subprocess 실행(asyncio). stdout/stderr 분리 캡처. 누락 바이너리/타임아웃은
    *정직하게* 비0 exit로 보고(완료 조작 금지). cp949 회피 위해 utf-8 replace 디코드."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv, cwd=cwd, env=env,
            stdin=asyncio.subprocess.DEVNULL,        # headless: 즉시 EOF(codex exec가 stdin 대기로 멈추는 것 방지)
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return ExecResult(127, "", f"binary not found: {argv[0] if argv else '?'}")
    except Exception as e:  # noqa: BLE001
        return ExecResult(1, "", f"spawn error: {e}")
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()            # reap + 파이프 transport 정리(Windows proactor ResourceWarning 방지)
        except Exception:
            pass
        return ExecResult(124, "", f"timeout after {timeout_sec}s")
    return ExecResult(
        proc.returncode if proc.returncode is not None else -1,
        (out or b"").decode("utf-8", "replace"),
        (err or b"").decode("utf-8", "replace"),
    )


class CliExecAdapter:
    """CLI shell-out 실행만 하는 어댑터 공통부. 만드는 건 RawAgentOutput뿐(Isolation).
    하위는 argv_for(invocation)만 특수화한다. cli는 클래스속성."""
    name = "cli"
    cli = ""

    def __init__(self, runner: Optional[CommandRunner] = None, cli: Optional[str] = None,
                 extra_args: Optional[list[str]] = None):
        self._runner: CommandRunner = runner or default_runner
        if cli:
            self.cli = cli
        self.extra_args: list[str] = list(extra_args or [])   # provider CLI 추가 인자(예: 권한우회)

    def argv_for(self, invocation: AgentInvocation) -> list[str]:
        raise NotImplementedError

    def _base_argv(self) -> list[str]:
        # Windows npm 셰임(.cmd/.ps1)을 실제 .exe/node-script로 우회. non-Windows면 바이너리 그대로.
        return resolve_launcher(self.cli)

    async def run(self, invocation: AgentInvocation) -> RawAgentOutput:
        argv = self.argv_for(invocation)                 # 한 번만 — RunReport에 그대로 기록(replay)
        res = await self._runner(
            argv,
            cwd=invocation.workspace_root,
            env=child_env(invocation.env),
            timeout_sec=invocation.timeout_sec,
        )
        return RawAgentOutput(
            run_id=invocation.run_id,
            identity_id=invocation.identity_id,
            runner=self.name,                            # 어느 실행기가 돌렸나
            command=argv,                                # 실제 argv
            cwd=invocation.workspace_root,               # 실행 디렉토리(=subprocess cwd)
            exit_code=res.exit_code,
            stdout=res.stdout,
            stderr=res.stderr,
            changed_files=detect_changed_files(invocation.workspace_root),
            workspace_root=invocation.workspace_root,
            session_id=invocation.session_id,
        )

    async def health(self) -> bool:
        res = await self._runner(self._base_argv() + ["--version"], cwd=".",
                                 env=dict(os.environ), timeout_sec=15)
        return res.exit_code == 0
