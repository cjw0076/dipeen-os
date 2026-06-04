"""Phase 4 (Epic B/C) — doctor --runner: harmless live probe.

'PATH에 바이너리가 있다(installed)'와 '실제로 실행된다(runnable/probe healthy)'는 *다른 주장*이다
(Evidence First — docs/SUPPORT_LEVELS.md). omo는 PATH에 omo가 있어도 bun 런타임이 없으면
`spawnSync bun ENOENT`로 죽는다 → installed=True, runnable=False. doctor --runner가 이를 드러낸다.

probe는 무해한 `--version`/status류 호출만 한다(작업 실행 아님). run/which_fn 주입으로 hermetic 검증.
"""
from __future__ import annotations

from dipeen_agent.onboarding import probe_runner


def _fake_run(exit_code: int, stdout: str = "", stderr: str = ""):
    """주입형 probe 실행기 — 실제 CLI 없이 결정론적 (exit, stdout, stderr)."""
    def run(argv: list[str]) -> tuple[int, str, str]:
        return (exit_code, stdout, stderr)
    return run


def test_probe_runner_not_installed_when_binary_absent():
    """바이너리가 PATH에 없으면 installed=False, runnable=False + 설치 안내(다음 행동)."""
    res = probe_runner("omo-opencode", which_fn=lambda b: None,
                       run=_fake_run(0, "should-not-run"))
    assert res["installed"] is False
    assert res["runnable"] is False
    assert res["install_cmd"]                         # 다음 행동 안내 존재


def test_probe_runner_installed_but_bun_blocked_is_not_runnable():
    """omo 바이너리는 PATH에 있지만 bun ENOENT → installed=True, runnable=False(가짜 OK 금지)."""
    res = probe_runner(
        "omo-opencode", which_fn=lambda b: f"/usr/bin/{b}",
        run=_fake_run(2, "", "oh-my-opencode: failed to execute Bun: spawnSync bun ENOENT"))
    assert res["installed"] is True
    assert res["runnable"] is False
    assert res["blocker"] == "bun"                    # 런타임 의존성 차단 명시


def test_probe_runner_healthy_when_version_ok():
    """정상 probe(exit 0 + 버전) → runnable=True, 버전 캡처."""
    res = probe_runner("hermes", which_fn=lambda b: f"/usr/bin/{b}",
                       run=_fake_run(0, "hermes agent v0.15.1"))
    assert res["installed"] is True
    assert res["runnable"] is True
    assert res["version"]                             # 버전 문자열 캡처


def test_probe_runner_support_level_is_evidence_gated():
    """probe가 통과해도 omo/hermes는 preview — 'supported'로 자동 광고하지 않는다(advertise after evidence)."""
    res = probe_runner("omo-opencode", which_fn=lambda b: f"/usr/bin/{b}",
                       run=_fake_run(0, "omo 4.7.4"))
    assert res["support"] == "preview"                # claude/codex만 supported


def test_probe_runner_nonzero_exit_is_not_runnable():
    """bun 무관 비0 exit(예: auth 없음)도 runnable=False — 정직(가짜 healthy 금지)."""
    res = probe_runner("hermes", which_fn=lambda b: f"/usr/bin/{b}",
                       run=_fake_run(1, "", "error: no credentials configured"))
    assert res["installed"] is True
    assert res["runnable"] is False
    assert res["blocker"] is None                     # bun 차단은 아님 — 일반 실패


# ──────────────── Keystone C: auth-aware probe (--version exit 0 ≠ authed) ────────────────
def test_probe_runner_claude_logged_out_is_not_runnable():
    """claude --version은 로그아웃 상태에서도 exit 0 → 그것만으론 runnable이면 안 된다.
    auth 미충족이면 runnable=False, auth=False (Keystone C 핵심 갭)."""
    res = probe_runner("claude-code", which_fn=lambda b: f"/usr/bin/{b}",
                       run=_fake_run(0, "2.1.162 (Claude Code)"),
                       auth_fn=lambda name: False)
    assert res["installed"] is True
    assert res["auth"] is False
    assert res["runnable"] is False                   # --version OK여도 auth 없으면 advertise 금지


def test_probe_runner_claude_authed_is_runnable():
    """auth 충족 + --version OK → runnable=True, auth=True."""
    res = probe_runner("claude-code", which_fn=lambda b: f"/usr/bin/{b}",
                       run=_fake_run(0, "2.1.162 (Claude Code)"),
                       auth_fn=lambda name: True)
    assert res["installed"] is True
    assert res["auth"] is True
    assert res["runnable"] is True


def test_probe_runner_codex_logged_out_is_not_runnable():
    """codex도 동일한 --version 갭 → auth 미충족이면 runnable=False."""
    res = probe_runner("omo-codex-light", which_fn=lambda b: f"/usr/bin/{b}",
                       run=_fake_run(0, "codex-cli 0.136.0"),
                       auth_fn=lambda name: False)
    assert res["runnable"] is False
    assert res["auth"] is False


def test_default_auth_check_reads_env_key(monkeypatch):
    """기본 auth 검사: ANTHROPIC_API_KEY가 있으면 claude auth=True."""
    from dipeen_agent.onboarding import _default_auth_check
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xxx")
    assert _default_auth_check("claude-code") is True


def test_default_auth_check_non_gated_provider_returns_none():
    """auth로 게이트하지 않는 provider(omo/hermes)는 None — 기존 probe-exit 의미 유지."""
    from dipeen_agent.onboarding import _default_auth_check
    assert _default_auth_check("hermes") is None
    assert _default_auth_check("omo-opencode") is None
