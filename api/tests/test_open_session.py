import pytest
from app.services.open_session import ensure_hq, EnsureHqError, BootDeps


def _deps(*, health_seq, docker=True, docker_ok=True, uvicorn_ok=True):
    calls = {"docker": 0, "uvicorn": 0}
    seq = list(health_seq)
    def hq_health():
        return seq.pop(0) if seq else True
    def docker_available():
        return docker
    def boot_docker():
        calls["docker"] += 1
        return (docker_ok, "" if docker_ok else "port 8000 is already in use")
    def boot_uvicorn():
        calls["uvicorn"] += 1
        return (uvicorn_ok, "" if uvicorn_ok else "uvicorn failed")
    return BootDeps(hq_health=hq_health, docker_available=docker_available,
                    boot_docker=boot_docker, boot_uvicorn=boot_uvicorn), calls


def test_hq_already_up_skips_boot():
    deps, calls = _deps(health_seq=[True])
    r = ensure_hq(mode="auto", deps=deps)
    assert r.hq_started_by_us is False
    assert calls["docker"] == 0 and calls["uvicorn"] == 0


def test_docker_present_boots_docker():
    deps, calls = _deps(health_seq=[False, True])
    r = ensure_hq(mode="auto", deps=deps)
    assert r.hq_started_by_us is True and calls["docker"] == 1 and calls["uvicorn"] == 0


def test_docker_absent_falls_back_to_uvicorn():
    deps, calls = _deps(health_seq=[False, True], docker=False)
    r = ensure_hq(mode="auto", deps=deps)
    assert r.hq_started_by_us is True and calls["uvicorn"] == 1 and calls["docker"] == 0


def test_docker_present_but_fails_does_NOT_fall_back():
    deps, calls = _deps(health_seq=[False], docker=True, docker_ok=False)
    with pytest.raises(EnsureHqError) as e:
        ensure_hq(mode="auto", deps=deps)
    assert "Docker" in str(e.value) and "port 8000" in str(e.value)
    assert calls["uvicorn"] == 0


def test_dev_mode_forces_uvicorn():
    deps, calls = _deps(health_seq=[False, True], docker=True)
    ensure_hq(mode="uvicorn", deps=deps)
    assert calls["uvicorn"] == 1 and calls["docker"] == 0


def test_boot_timeout_raises_human_error():
    deps, calls = _deps(health_seq=[False, False, False, False], docker=False)
    with pytest.raises(EnsureHqError) as e:
        ensure_hq(mode="auto", deps=deps, health_retries=3, health_interval=0, sleep=lambda s: None)
    assert "Couldn't start the Dipeen API" in str(e.value)


from app.services.open_session import open_workspace, OpenSessionResult, SessionDeps


def _sdeps():
    return SessionDeps(
        ensure_team=lambda name: {"id": "team-1", "name": name or "Meeting Agent Team"},
        mint_invite=lambda team_id: {"code": "AB12CD34", "expires_at": "2026-06-05T00:00:00Z"},
    )


def test_open_workspace_builds_result_with_fresh_invite():
    r = open_workspace(team=None, api_url="http://localhost:8000", web_url="http://localhost:3000",
                       deps=_sdeps())
    assert isinstance(r, OpenSessionResult)
    assert r.team_name == "Meeting Agent Team"
    assert r.invite_code == "AB12CD34" and r.invite_expires_at == "2026-06-05T00:00:00Z"
    assert r.api_url == "http://localhost:8000"
    assert r.web_url == "http://localhost:3000?api=http://localhost:8000"
    assert r.join_command == "dipeen-agent join AB12CD34 --api-url http://localhost:8000"
    assert r.slash_join_command == "/dipeen join AB12CD34"
    assert r.hq_started_by_us is False


def test_open_workspace_passes_hq_started_flag():
    r = open_workspace(team="X", api_url="http://h:8000", web_url="http://h:3000",
                       deps=_sdeps(), hq_started_by_us=True)
    assert r.hq_started_by_us is True


from app.services.open_session_format import format_open_local


def test_format_local_is_action_centric():
    r = OpenSessionResult(
        team_name="Meeting Agent Team", invite_code="AB12CD34",
        invite_expires_at="2026-06-05T00:00:00Z", api_url="http://localhost:8000",
        web_url="http://localhost:3000?api=http://localhost:8000",
        join_command="dipeen-agent join AB12CD34 --api-url http://localhost:8000",
        slash_join_command="/dipeen join AB12CD34")
    out = format_open_local(r)
    assert "Dipeen workspace is open." in out
    assert "AB12CD34" in out
    assert "Next actions:" in out
    assert "/dipeen expose this session" in out
    assert "/dipeen invite teammate" in out
    assert "http://localhost:3000?api=http://localhost:8000" in out
