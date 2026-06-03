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
