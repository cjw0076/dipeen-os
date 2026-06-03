"""NAT M2 adapters — AgentAdapter Protocol + Claude/Codex CLI *실행만*(Isolation).

비결정적·구독 의존인 실제 CLI 대신 **러너를 주입**(DI)해 어댑터 로직(명령 구성·RawAgentOutput
조립·changed_files·env·Isolation)을 hermetic하게 검증한다. done-when(§ULTRAPLAN M2):
둘 다 RawAgentOutput 반환, artifact/state 안 만듦.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from app.nat.contracts import AgentInvocation, RawAgentOutput
from app.nat.adapters.base import (
    AgentAdapter, CliExecAdapter, ExecResult, child_env, default_runner, detect_changed_files,
)
from app.nat.adapters.claude import ClaudeAdapter
from app.nat.adapters.codex import CodexAdapter


def _git_repo() -> Path:
    root = Path(tempfile.mkdtemp(prefix="nat-ws-"))
    subprocess.run(["git", "init", "-q"], cwd=root, check=True,
                   capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True,
                   capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True,
                   capture_output=True)
    return root


def _inv(workspace: str, prompt: str = "do X", **kw) -> AgentInvocation:
    return AgentInvocation(run_id="R-1", identity_id="agent://team/frontend",
                           prompt=prompt, workspace_root=workspace, **kw)


class _FakeRunner:
    """주입 러너 — argv/cwd/env/timeout 캡처, 정해진 ExecResult 반환.
    writes 주면 실행 시 워크스페이스에 파일 생성(agent 편집 시뮬)."""

    def __init__(self, result: ExecResult, *, writes: str | None = None):
        self.result = result
        self.writes = writes
        self.calls: list[dict] = []

    async def __call__(self, argv, *, cwd, env, timeout_sec):
        self.calls.append({"argv": list(argv), "cwd": cwd,
                           "env": dict(env), "timeout_sec": timeout_sec})
        if self.writes:
            (Path(cwd) / self.writes).write_text("edited\n", encoding="utf-8")
        return self.result


# ════════ base: Protocol ════════
@pytest.mark.asyncio
async def test_agent_adapter_protocol_runtime_checkable():
    assert isinstance(ClaudeAdapter(), AgentAdapter)
    assert isinstance(CodexAdapter(), AgentAdapter)

    class _NotAdapter:                       # run 없음 → 계약 불충족
        name = "x"

        async def health(self) -> bool:
            return True

    assert not isinstance(_NotAdapter(), AgentAdapter)


# ════════ base: changed_files (실제 git, raw 관찰) ════════
def test_detect_changed_files_reports_created_file():
    ws = _git_repo()
    assert detect_changed_files(str(ws)) == []
    (ws / "page.tsx").write_text("x", encoding="utf-8")
    assert "page.tsx" in detect_changed_files(str(ws))


def test_detect_changed_files_non_git_is_empty():
    ws = Path(tempfile.mkdtemp(prefix="nat-nogit-"))
    assert detect_changed_files(str(ws)) == []


# ════════ base: child_env — ""=unset(구독 크레딧0) ════════
def test_child_env_empty_value_unsets_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    env = child_env({"ANTHROPIC_API_KEY": "", "FOO": "bar"})
    assert "ANTHROPIC_API_KEY" not in env            # ""=unset → ~/.claude 자격증명 fallback
    assert env["FOO"] == "bar"


# ════════ claude: 명령 구성 + raw 조립 ════════
@pytest.mark.asyncio
async def test_claude_run_builds_print_command_and_returns_raw():
    ws = _git_repo()
    fake = _FakeRunner(ExecResult(0, "hello", ""))
    out = await ClaudeAdapter(runner=fake).run(_inv(str(ws), "구현해줘"))
    assert isinstance(out, RawAgentOutput)
    assert fake.calls[0]["argv"][-2:] == ["-p", "구현해줘"]      # 런처 토큰수 무관, 끝이 [-p, prompt]
    assert out.run_id == "R-1" and out.identity_id == "agent://team/frontend"
    assert out.exit_code == 0 and out.stdout == "hello"
    assert out.workspace_root == str(ws)


@pytest.mark.asyncio
async def test_claude_run_populates_changed_files():
    ws = _git_repo()
    fake = _FakeRunner(ExecResult(0, "", ""), writes="page.tsx")
    out = await ClaudeAdapter(runner=fake).run(_inv(str(ws)))
    assert "page.tsx" in out.changed_files                    # 어댑터가 raw 변경파일만 채움


@pytest.mark.asyncio
async def test_claude_run_passes_subscription_env_unset(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-live")
    ws = _git_repo()
    fake = _FakeRunner(ExecResult(0, "", ""))
    await ClaudeAdapter(runner=fake).run(_inv(str(ws), env={"ANTHROPIC_API_KEY": ""}))
    assert "ANTHROPIC_API_KEY" not in fake.calls[0]["env"]    # 구독 실행=키 제거


@pytest.mark.asyncio
async def test_claude_health_reflects_cli_exit():
    assert await ClaudeAdapter(runner=_FakeRunner(ExecResult(0, "claude 1.0", ""))).health() is True
    assert await ClaudeAdapter(runner=_FakeRunner(ExecResult(127, "", "not found"))).health() is False


# ════════ codex: 명령 구성 ════════
@pytest.mark.asyncio
async def test_codex_run_builds_exec_command():
    ws = _git_repo()
    fake = _FakeRunner(ExecResult(0, "ok", ""))
    out = await CodexAdapter(runner=fake).run(_inv(str(ws), "fix bug"))
    assert fake.calls[0]["argv"][-2:] == ["exec", "fix bug"]   # 런처 토큰수 무관, 끝이 [exec, prompt]
    assert isinstance(out, RawAgentOutput) and out.identity_id == "agent://team/frontend"


# ════════ M2 done-when: Isolation ════════
@pytest.mark.asyncio
async def test_both_adapters_same_invocation_only_raw_output():
    """같은 invocation → Claude·Codex raw는 달라도 둘 다 동일 RawAgentOutput shape(artifact/state 없음)."""
    ws = _git_repo()
    inv = _inv(str(ws), "same task")
    rc = await ClaudeAdapter(runner=_FakeRunner(ExecResult(0, "claude out", ""))).run(inv)
    rx = await CodexAdapter(runner=_FakeRunner(ExecResult(0, "codex out", ""))).run(inv)
    assert isinstance(rc, RawAgentOutput) and isinstance(rx, RawAgentOutput)
    assert type(rc) is type(rx)
    assert rc.run_id == rx.run_id == "R-1"
    assert rc.stdout != rx.stdout                            # raw는 다름 — NAT(M3)가 normalize


def test_adapters_do_not_import_dipeen_state_types():
    """Isolation 정적 가드 — 어댑터 모듈은 Artifact/State/Event/Memory 타입을 끌어오지 않는다."""
    import app.nat.adapters.claude as cl
    import app.nat.adapters.codex as cx
    forbidden = ("Artifact", "StateClaim", "Event", "NormalizedAgentResult", "MemoryCandidate")
    for m in (cl, cx):
        for f in forbidden:
            assert not hasattr(m, f), f"Isolation 위반: {m.__name__} exposes {f}"


# ════════ default_runner: 실제 subprocess 플러밍(python으로 hermetic) ════════
@pytest.mark.asyncio
async def test_default_runner_captures_stdout_stderr_exit():
    res = await default_runner(
        [sys.executable, "-c", "import sys; print('hi'); sys.stderr.write('warn'); sys.exit(3)"],
        cwd=".", env=dict(os.environ), timeout_sec=30)
    assert res.exit_code == 3
    assert "hi" in res.stdout and "warn" in res.stderr        # stdout/stderr 분리 캡처


@pytest.mark.asyncio
async def test_default_runner_stdin_is_eof_not_blocking():
    # headless CLI가 stdin을 읽어도 즉시 EOF(DEVNULL) — codex exec 행 방지의 회귀 가드
    res = await default_runner(
        [sys.executable, "-c", "import sys; print('got', len(sys.stdin.read()))"],
        cwd=".", env=dict(os.environ), timeout_sec=15)
    assert res.exit_code == 0 and "got 0" in res.stdout


@pytest.mark.asyncio
async def test_default_runner_missing_binary_is_127():
    res = await default_runner(["definitely-not-a-real-binary-xyz123"], cwd=".",
                               env=dict(os.environ), timeout_sec=10)
    assert res.exit_code == 127 and "not found" in res.stderr  # 누락=정직한 비0(조작 금지)


@pytest.mark.asyncio
async def test_default_runner_timeout_is_124():
    res = await default_runner(
        [sys.executable, "-c", "import time; time.sleep(5)"],
        cwd=".", env=dict(os.environ), timeout_sec=1)
    assert res.exit_code == 124 and "timeout" in res.stderr


# ════════ Windows npm 셰임 해석(_parse_shim) — synthetic 셰임으로 hermetic ════════
def test_parse_shim_resolves_direct_exe(tmp_path):
    from app.nat.adapters.base import _parse_shim
    exe = tmp_path / "node_modules" / "foo" / "bin" / "foo.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("x", encoding="utf-8")
    cmd = tmp_path / "foo.cmd"
    cmd.write_text('@ECHO off\r\n"%dp0%\\node_modules\\foo\\bin\\foo.exe"   %*\r\n', encoding="utf-8")
    assert _parse_shim(cmd) == [str(exe)]                       # claude 스타일(직접 .exe)


def test_parse_shim_resolves_node_script(tmp_path):
    from app.nat.adapters.base import _parse_shim
    js = tmp_path / "node_modules" / "bar" / "bin" / "bar.js"
    js.parent.mkdir(parents=True)
    js.write_text("x", encoding="utf-8")
    cmd = tmp_path / "bar.cmd"
    cmd.write_text('@ECHO off\r\n"%_prog%"  "%dp0%\\node_modules\\bar\\bin\\bar.js" %*\r\n', encoding="utf-8")
    toks = _parse_shim(cmd)                                     # codex 스타일(node + js)
    assert len(toks) == 2 and toks[1] == str(js)
    assert toks[0] == "node" or toks[0].lower().endswith("node.exe")


@pytest.mark.asyncio
async def test_adapter_appends_extra_args_before_prompt():
    ws = _git_repo()
    fake = _FakeRunner(ExecResult(0, "", ""))
    await ClaudeAdapter(runner=fake, extra_args=["--dangerously-skip-permissions"]).run(_inv(str(ws), "do"))
    argv = fake.calls[0]["argv"]
    assert "--dangerously-skip-permissions" in argv
    assert argv[-1] == "do"                                    # 프롬프트가 마지막, 플래그는 그 앞
