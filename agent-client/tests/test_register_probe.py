"""Keystone C (C2) — probe travels at worker register.

The server's compute_effective drops a `provider.*` cap only if it was *probed and not
runnable*. So the worker must send a probe dict `{provider_name: {"runnable": bool, ...}}`
at register, derived from its advertised provider.* capabilities. This proves an honest
worker that advertises provider.claude but is logged out does NOT get leased claude work.
"""
from __future__ import annotations

from dipeen_agent.onboarding import build_register_probe


def _fake_probe(result_by_runner):
    def probe(name, **_):
        return result_by_runner.get(name, {"installed": False, "runnable": False})
    return probe


def test_build_probe_maps_provider_caps_to_runnable():
    """provider.claude → runner claude-code probe → {"claude": {"runnable": True}}."""
    caps = ["provider.claude", "role.fe", "workspace.write"]
    probe = build_register_probe(caps, probe_fn=_fake_probe({
        "claude-code": {"installed": True, "runnable": True, "version": "2.1"},
    }))
    assert probe["claude"]["runnable"] is True


def test_build_probe_marks_unrunnable_provider():
    """provider.omo가 bun 차단으로 실행 불가 → {"omo": {"runnable": False}} (서버가 caps에서 드롭)."""
    caps = ["provider.omo", "role.fe"]
    probe = build_register_probe(caps, probe_fn=_fake_probe({
        "omo-opencode": {"installed": True, "runnable": False, "blocker": "bun"},
    }))
    assert probe["omo"]["runnable"] is False
    assert probe["omo"]["blocker"] == "bun"


def test_build_probe_skips_fake_and_non_provider_caps():
    """fake는 내장(probe 불필요 → 미포함, compute_effective가 unprobed로 유지); role.* 등은 무시."""
    caps = ["provider.fake", "role.fe", "user.minjun", "repo.demo"]
    probe = build_register_probe(caps, probe_fn=_fake_probe({}))
    assert "fake" not in probe
    assert probe == {}


def test_build_probe_logged_out_claude_is_not_runnable():
    """로그아웃 claude(auth 미충족) → probe runnable=False → 서버가 provider.claude를 effective에서 제거."""
    caps = ["provider.claude"]
    probe = build_register_probe(caps, probe_fn=_fake_probe({
        "claude-code": {"installed": True, "runnable": False, "auth": False},
    }))
    assert probe["claude"]["runnable"] is False
