from app.nat import cli
from app.services.open_session import OpenSessionResult


def test_cmd_open_prints_action_centric(capsys, monkeypatch):
    monkeypatch.setattr(cli, "_run_open", lambda args: OpenSessionResult(
        team_name="Meeting Agent Team", invite_code="AB12CD34", invite_expires_at="T+24h",
        api_url="http://localhost:8000", web_url="http://localhost:3000?api=http://localhost:8000",
        join_command="dipeen-agent join AB12CD34 --api-url http://localhost:8000",
        slash_join_command="/dipeen join AB12CD34"))
    rc = cli.main(["open"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Dipeen workspace is open." in out and "Next actions:" in out and "AB12CD34" in out


def test_cmd_open_human_error_on_boot_failure(capsys, monkeypatch):
    from app.services.open_session import EnsureHqError
    def _boom(args):
        raise EnsureHqError("Couldn't start the Dipeen API. Is Docker running?", "docker compose exited 1")
    monkeypatch.setattr(cli, "_run_open", _boom)
    rc = cli.main(["open"])
    out = capsys.readouterr().out
    assert rc == 1 and "Couldn't start the Dipeen API" in out
    assert "docker compose exited 1" not in out          # internal detail hidden without --verbose


def test_open_lecture_prints_public_and_receipt(capsys, monkeypatch):
    from app.services.open_session import OpenSessionResult
    from app.services.session_expose import ExposeResult
    monkeypatch.setattr(cli, "_run_open", lambda args: OpenSessionResult(
        team_name="Lecture Team", invite_code="LEC1", invite_expires_at="T+24h",
        api_url="http://localhost:8000", web_url="http://localhost:3000?api=http://localhost:8000",
        join_command="dipeen-agent join LEC1 --api-url http://localhost:8000",
        slash_join_command="/dipeen join LEC1"))
    monkeypatch.setattr(cli, "_run_expose", lambda args, started: ExposeResult(
        ok=True, permission_id="perm_L", receipt_id="rcpt_L", tunnel_started=True,
        web_url="https://web.trycloudflare.com", api_url="https://api.trycloudflare.com",
        message="Public access requested and approved for this session (receipt rcpt_L)."))
    monkeypatch.setattr(cli, "_hold_tunnel", lambda: None)   # don't block in the test
    rc = cli.main(["open", "lecture"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "https://web.trycloudflare.com" in out and "rcpt_L" in out
    assert "join LEC1" in out


def test_open_lecture_fail_closed_when_expose_refused(capsys, monkeypatch):
    from app.services.open_session import OpenSessionResult
    from app.services.session_expose import ExposeResult
    monkeypatch.setattr(cli, "_run_open", lambda args: OpenSessionResult(
        team_name="T", invite_code="X", invite_expires_at="t", api_url="http://localhost:8000",
        web_url="http://localhost:3000?api=http://localhost:8000",
        join_command="dipeen-agent join X --api-url http://localhost:8000",
        slash_join_command="/dipeen join X"))
    monkeypatch.setattr(cli, "_run_expose", lambda args, started: ExposeResult(
        ok=False, tunnel_started=False, message="Refusing to expose with authentication disabled."))
    rc = cli.main(["open", "lecture"])
    out = capsys.readouterr().out
    assert "Refusing to expose" in out   # the refusal is surfaced; HQ still opened locally


def test_close_command_prints_hq_stays(capsys, monkeypatch):
    rc = cli.main(["close"])
    out = capsys.readouterr().out
    assert rc == 0 and "Dipeen HQ is still running" in out
