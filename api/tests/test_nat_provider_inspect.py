"""M11a Provider Discovery — `dipeen providers inspect` read-only 진단 테스트.

검증 대상: api/app/nat/providers/inspection.py(타입+헬퍼) + 각 provider inspect().
원칙(plan): 감지는 static(which/파일), 버전만 격리된 probe_version. Core 계약(contracts.py) 무오염.
"""
import shutil
import subprocess

import pytest

from app.nat.providers.inspection import (
    ProviderInspection,
    find_existing,
    probe_version,
    which_any,
)


# ──────────────────── 1. 타입 + 공유 헬퍼 ────────────────────
def test_provider_inspection_to_dict_roundtrips():
    insp = ProviderInspection(
        name="omo", installed=True, version="3.11.0", binary_path="/usr/bin/omo",
        config_paths=["/c.json"], capabilities=["a"], known_blockers=["b"],
        recommended_next_action="next")
    d = insp.to_dict()
    assert d["name"] == "omo"
    assert d["installed"] is True
    assert d["version"] == "3.11.0"
    assert d["binary_path"] == "/usr/bin/omo"
    assert d["config_paths"] == ["/c.json"]
    assert d["capabilities"] == ["a"]
    assert d["known_blockers"] == ["b"]
    assert d["recommended_next_action"] == "next"


def test_provider_inspection_defaults_are_empty():
    insp = ProviderInspection(name="x", installed=False)
    assert insp.version is None
    assert insp.binary_path is None
    assert insp.config_paths == []
    assert insp.capabilities == []
    assert insp.known_blockers == []


def test_which_any_returns_first_found(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/omo" if n == "omo" else None)
    assert which_any(["oh-my-opencode", "omo", "opencode"]) == "/usr/bin/omo"


def test_which_any_none_when_absent(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda n: None)
    assert which_any(["omo", "opencode"]) is None


def test_probe_version_returns_trimmed_first_line(monkeypatch):
    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, stdout="omo 3.11.0\nextra line\n", stderr="")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert probe_version("/usr/bin/omo") == "omo 3.11.0"


def test_probe_version_timeout_degrades_to_none(monkeypatch):
    def fake_run(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, 5)
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert probe_version("/usr/bin/omo") is None


def test_probe_version_nonzero_exit_is_none(monkeypatch):
    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert probe_version("/usr/bin/x") is None


def test_probe_version_oserror_is_none(monkeypatch):
    def fake_run(cmd, **kw):
        raise OSError("not executable")
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert probe_version("/usr/bin/x") is None


def test_probe_version_decodes_child_output_as_utf8(monkeypatch):
    """자식 CLI의 UTF-8 출력(em dash 등)을 locale(Windows=cp949)이 아닌 UTF-8로 디코드해야 한다.

    text=True만 쓰면 Windows에서 cp949로 디코드 → omo/hermes의 UTF-8 출력이 UnicodeDecodeError로
    유실된다(라이브에서 적발). encoding="utf-8", errors="replace"를 명시해 회귀를 막는다.
    """
    captured = {}

    def fake_run(cmd, **kw):
        captured.update(kw)
        return subprocess.CompletedProcess(cmd, 0, "tool 1.0\n", "")
    monkeypatch.setattr(subprocess, "run", fake_run)
    probe_version("/usr/bin/tool")
    assert captured.get("encoding") == "utf-8"
    assert captured.get("errors") == "replace"


def test_find_existing_filters_to_present_paths(tmp_path):
    present = tmp_path / "exists.json"
    present.write_text("{}", encoding="utf-8")
    got = find_existing([str(present), str(tmp_path / "missing.json")])
    assert got == [str(present)]


# ──────────────────── 2. provider inspect() ────────────────────
def _ok_run(out):
    return lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, out, "")


def test_inspect_omo_installed(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/omo" if n == "omo" else None)
    monkeypatch.setattr(subprocess, "run", _ok_run("oh-my-opencode 3.11.0\n"))
    from app.nat.providers.omo.inspect import inspect
    insp = inspect()
    assert insp.name == "omo"
    assert insp.installed is True
    assert insp.binary_path == "/usr/bin/omo"
    assert insp.version == "oh-my-opencode 3.11.0"


def test_inspect_omo_missing_reports_install(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda n: None)
    from app.nat.providers.omo.inspect import inspect
    insp = inspect()
    assert insp.installed is False
    assert "npm" in insp.recommended_next_action


def test_inspect_omo_team_tools_in_blockers(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/omo" if n == "omo" else None)
    monkeypatch.setattr(subprocess, "run", _ok_run("3.11.0\n"))
    from app.nat.providers.omo.inspect import inspect
    blockers = " ".join(inspect().known_blockers).lower()
    assert "team" in blockers  # 번들 OMO엔 team tools 없음을 정직하게 보고


def test_inspect_omo_detects_config_even_when_binary_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda n: None)
    cfg = tmp_path / "oh-my-opencode.json"
    cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path))
    from app.nat.providers.omo.inspect import inspect
    assert str(cfg) in inspect().config_paths


def test_inspect_omo_installed_but_version_probe_fails_reports_blocker(monkeypatch):
    """binary는 PATH에 있으나 --version이 실패(omo+bun 누락 등)하면 '실행 가능성 불확실'을 정직하게
    blocker로 보고한다 — installed ✓만 보고 OK라 오해하지 않도록(Evidence First, 라이브에서 적발)."""
    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/omo" if n == "omo" else None)
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 2, "", "bun ENOENT"))
    from app.nat.providers.omo.inspect import inspect
    insp = inspect()
    assert insp.installed is True
    assert insp.version is None
    joined = " ".join(insp.known_blockers).lower()
    assert "probe" in joined or "실행" in joined  # 실행 가능성 불확실을 명시


def test_inspect_omo_missing_does_not_probe_version(monkeypatch):
    """미설치(binary None)면 subprocess 0건 — 감지는 static, 버전 probe는 설치 시에만."""
    monkeypatch.setattr(shutil, "which", lambda n: None)
    calls = []
    monkeypatch.setattr(subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""))
    from app.nat.providers.omo.inspect import inspect
    inspect()
    assert calls == []


def test_inspect_hermes_missing_reports_install_cmd(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda n: None)
    from app.nat.providers.hermes.inspect import inspect
    insp = inspect()
    assert insp.installed is False
    assert "NousResearch/hermes-agent" in insp.recommended_next_action


def test_inspect_hermes_not_confused_with_legacy_router(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/hermes" if n == "hermes" else None)
    monkeypatch.setattr(subprocess, "run", _ok_run("hermes 1.0\n"))
    from app.nat.providers.hermes.inspect import inspect
    insp = inspect()
    blob = (insp.recommended_next_action + " " + " ".join(insp.capabilities)
            + " " + " ".join(insp.known_blockers)).lower()
    assert "a2a" not in blob
    assert "websocket" not in blob
    assert "ws/hermes" not in blob


def test_inspect_claude_installed(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/claude" if n == "claude" else None)
    monkeypatch.setattr(subprocess, "run", _ok_run("1.0.0\n"))
    from app.nat.providers.claude.inspect import inspect
    insp = inspect()
    assert insp.name == "claude"
    assert insp.installed is True
    assert "nat.plugin" in insp.capabilities


def test_inspect_codex_missing(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda n: None)
    from app.nat.providers.codex.inspect import inspect
    insp = inspect()
    assert insp.name == "codex"
    assert insp.installed is False


# ──────────────────── 3. CLI: `dipeen providers inspect` ────────────────────
def test_cli_providers_inspect_json(monkeypatch, capsys):
    import json as _json

    monkeypatch.setattr(shutil, "which", lambda n: "/usr/bin/claude" if n == "claude" else None)
    monkeypatch.setattr(subprocess, "run", _ok_run("1.0.0\n"))
    from app.nat.cli import main
    rc = main(["providers", "inspect", "claude", "--json"])
    assert rc == 0
    data = _json.loads(capsys.readouterr().out)
    assert data["name"] == "claude"
    assert data["installed"] is True


def test_cli_providers_inspect_all_json(monkeypatch, capsys):
    import json as _json

    monkeypatch.setattr(shutil, "which", lambda n: None)  # 전부 미설치(결정적)
    from app.nat.cli import main
    rc = main(["providers", "inspect", "all", "--json"])
    assert rc == 0
    data = _json.loads(capsys.readouterr().out)
    assert isinstance(data, list)
    assert {d["name"] for d in data} == {"claude", "codex", "omo", "hermes"}


def test_cli_providers_inspect_human_readable(monkeypatch, capsys):
    monkeypatch.setattr(shutil, "which", lambda n: None)
    from app.nat.cli import main
    rc = main(["providers", "inspect", "hermes"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "hermes" in out
    assert "NousResearch/hermes-agent" in out  # 미설치 → 설치 안내가 사람용 출력에도 노출


def test_cli_providers_inspect_unknown_errors():
    from app.nat.cli import main
    with pytest.raises(SystemExit):  # argparse choices 거부
        main(["providers", "inspect", "nonexistent"])


def test_cli_output_safe_on_cp949_stdout(monkeypatch):
    """Windows 한국어 콘솔(cp949)에서 비ASCII 출력(✓/em dash/한글)이 UnicodeEncodeError로 죽지 않는다.

    capsys는 UTF-8이라 이 회귀를 못 잡는다 — cp949 stdout을 직접 꽂아 실제 콘솔을 재현한다.
    """
    import io
    import sys

    monkeypatch.setattr(shutil, "which", lambda n: None)
    buf = io.TextIOWrapper(io.BytesIO(), encoding="cp949", errors="strict")
    monkeypatch.setattr(sys, "stdout", buf)
    from app.nat.cli import main
    main(["providers", "inspect", "all"])  # em dash·한글·기호 전부 포함
    buf.flush()  # 인코딩 에러 없이 여기 도달하면 통과
