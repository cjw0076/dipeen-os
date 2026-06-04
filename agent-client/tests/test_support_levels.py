from dipeen_agent import onboarding
from dipeen_agent.runners import RunnerHealth
from dipeen_agent.support_levels import runner_support


def test_runner_support_levels_match_public_alpha_claims():
    assert runner_support("claude").level == "supported"
    assert runner_support("codex").level == "supported"
    assert runner_support("claude-code").level == "supported"
    assert runner_support("omo-codex-light").level == "preview"
    assert runner_support("omo-opencode").level == "preview"
    assert runner_support("hermes").level == "preview"
    assert runner_support("unknown").level == "preview"


def test_doctor_prints_runner_support_levels(monkeypatch, capsys):
    async def healths():
        return [
            RunnerHealth("claude-code", True, "ok"),
            RunnerHealth("hermes", False, "missing"),
        ]

    monkeypatch.setattr(onboarding, "_core_checks", lambda: [
        ("git", True, "required"),
        ("python", True, "required"),
    ])
    monkeypatch.setattr(onboarding, "all_health", healths)
    monkeypatch.setattr(onboarding, "provisioning", lambda: {
        "claude-code": {"install_cmd": "", "auth_cmd": "claude"},
        "hermes": {"install_cmd": "uv tool install hermes", "auth_cmd": "hermes model"},
    })

    import dipeen_agent.bun_link as bun_link

    monkeypatch.setattr(bun_link, "needs_bun_link", lambda: False)

    assert onboarding.doctor() == 0
    out = capsys.readouterr().out
    assert "support: supported" in out
    assert "primary worker path" in out
    assert "support: preview" in out
    assert "advertise only after live probe evidence" in out
