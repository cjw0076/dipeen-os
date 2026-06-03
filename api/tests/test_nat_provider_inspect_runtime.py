"""OMO/Hermes provider-specific inspect enrichment (M11a/M12a) — 사용자 통합설계 2026-06-03.

OMO = 실행팀 composite provider → inspect는 team_mode(config) + runtime(~/.omo) 탐지.
Hermes = 기억/skill/장기작업 제안자 → inspect는 memory/skills/cron(~/.hermes) 탐지.

**경계**: inspect는 read-only static. subtask≠Task / memory≠Org Memory는 실행·ingest(M11c+/M12b+)에서.
여기선 *탐지만* — capability는 declared(통합 시 제공 예정), routing은 provider.X로 별개.
모든 경로는 주입(OMO_HOME/HERMES_HOME/_config_dirs)으로 실머신 비의존.
"""
from __future__ import annotations

import json


# ──────────────── OMO: team_mode + runtime ────────────────
def test_omo_team_mode_parsed_from_config(tmp_path):
    from app.nat.providers.omo.inspect import omo_team_mode
    cfg = tmp_path / "oh-my-openagent.json"
    cfg.write_text(json.dumps({"team_mode": {"enabled": True, "max_parallel_members": 4, "max_members": 8}}),
                   encoding="utf-8")
    tm = omo_team_mode([str(cfg)])
    assert tm["enabled"] is True
    assert tm["max_parallel_members"] == 4
    assert tm["tools_available"] == 12              # team_mode on → 12 team_* tools


def test_omo_team_mode_default_off_when_absent(tmp_path):
    from app.nat.providers.omo.inspect import omo_team_mode
    cfg = tmp_path / "opencode.json"
    cfg.write_text(json.dumps({"model": "x"}), encoding="utf-8")   # team_mode 키 없음
    tm = omo_team_mode([str(cfg)])
    assert tm["enabled"] is False
    assert tm["tools_available"] == 0


def test_omo_runtime_counts_teams_and_runs(tmp_path):
    from app.nat.providers.omo.inspect import omo_runtime
    (tmp_path / "teams" / "alpha").mkdir(parents=True)
    (tmp_path / "teams" / "beta").mkdir(parents=True)
    (tmp_path / "runtime" / "run1").mkdir(parents=True)
    rt = omo_runtime(str(tmp_path))
    assert rt["declared_teams"] == 2
    assert rt["active_runs"] == 1
    assert rt["base_dir"] == str(tmp_path)


def test_omo_runtime_absent_dir_is_zero(tmp_path):
    from app.nat.providers.omo.inspect import omo_runtime
    rt = omo_runtime(str(tmp_path / "nonexistent"))
    assert rt["declared_teams"] == 0 and rt["active_runs"] == 0


def test_omo_inspect_details_and_capabilities(monkeypatch, tmp_path):
    """inspect()가 team_mode/runtime을 details에 싣고 omo.review/subtasks를 declared capability로."""
    from app.nat.providers.omo import inspect as omo_inspect
    monkeypatch.setattr(omo_inspect, "_config_dirs", lambda: [str(tmp_path)])
    monkeypatch.setattr(omo_inspect, "which_any", lambda names: "/usr/bin/omo")
    monkeypatch.setattr(omo_inspect, "probe_version", lambda b: "omo 3.11.0")
    (tmp_path / "oh-my-openagent.json").write_text(json.dumps({"team_mode": {"enabled": True}}), encoding="utf-8")
    monkeypatch.setenv("OMO_HOME", str(tmp_path / ".omo"))
    insp = omo_inspect.inspect()
    assert insp.details["team_mode"]["enabled"] is True
    assert "runtime" in insp.details
    assert "omo.review" in insp.capabilities and "omo.subtasks" in insp.capabilities
    assert "omo.team_mode" in insp.capabilities        # team_mode on → advertised
    assert "provider.omo" in insp.capabilities


def test_omo_inspect_detects_openagent_config_filename(tmp_path, monkeypatch):
    """실제 config는 oh-my-openagent.json(신) — 구 oh-my-opencode.json과 함께 탐지."""
    from app.nat.providers.omo import inspect as omo_inspect
    monkeypatch.setattr(omo_inspect, "_config_dirs", lambda: [str(tmp_path)])
    monkeypatch.setattr(omo_inspect, "which_any", lambda names: None)
    cfg = tmp_path / "oh-my-openagent.json"
    cfg.write_text("{}", encoding="utf-8")
    assert str(cfg) in omo_inspect.inspect().config_paths


# ──────────────── Hermes: memory + skills + cron ────────────────
def test_hermes_runtime_reads_config_and_dirs(tmp_path):
    from app.nat.providers.hermes.inspect import hermes_runtime
    (tmp_path / "config.yaml").write_text(
        "memory:\n  memory_enabled: true\n  memory_char_limit: 2200\nskills:\n  external_dirs: []\ncron:\n  wrap_response: true\n",
        encoding="utf-8")
    (tmp_path / "skills" / "apple").mkdir(parents=True)
    (tmp_path / "skills" / "devops").mkdir(parents=True)
    (tmp_path / "memories").mkdir()
    (tmp_path / "state.db").write_text("x", encoding="utf-8")
    rt = hermes_runtime(str(tmp_path))
    assert rt["memory"]["enabled"] is True
    assert rt["memory"]["char_limit"] == 2200
    assert rt["skills"]["count"] == 2
    assert rt["cron"]["available"] is True
    assert rt["state_db"] is True


def test_hermes_runtime_absent_home_graceful(tmp_path):
    from app.nat.providers.hermes.inspect import hermes_runtime
    rt = hermes_runtime(str(tmp_path / "nohome"))
    assert rt["memory"]["enabled"] is False
    assert rt["skills"]["count"] == 0
    assert rt["cron"]["available"] is False


def test_hermes_memory_usage_counts_chars(tmp_path):
    from app.nat.providers.hermes.inspect import hermes_runtime
    (tmp_path / "config.yaml").write_text(
        "memory:\n  memory_enabled: true\n  memory_char_limit: 100\n  user_char_limit: 50\n", encoding="utf-8")
    (tmp_path / "memories").mkdir()
    (tmp_path / "memories" / "MEMORY.md").write_text("a" * 30, encoding="utf-8")
    (tmp_path / "memories" / "USER.md").write_text("b" * 10, encoding="utf-8")
    rt = hermes_runtime(str(tmp_path))
    assert rt["memory"]["used_chars"] == 40
    assert rt["memory"]["char_limit"] == 150           # 100 + 50


def test_hermes_inspect_details_and_proposal_capabilities(monkeypatch, tmp_path):
    """inspect()가 memory/skills/cron을 details에, memory.propose/skill.propose/long_task.run을 capability로."""
    from app.nat.providers.hermes import inspect as hermes_inspect
    home = tmp_path / ".hermes"
    (home / "skills").mkdir(parents=True)
    (home / "memories").mkdir()
    (home / "config.yaml").write_text("memory:\n  memory_enabled: true\n", encoding="utf-8")
    monkeypatch.setattr(hermes_inspect, "which_any", lambda names: "/usr/bin/hermes")
    monkeypatch.setattr(hermes_inspect, "probe_version", lambda b: "Hermes Agent v0.15.1")
    monkeypatch.setenv("HERMES_HOME", str(home))
    insp = hermes_inspect.inspect()
    assert "memory" in insp.details and "skills" in insp.details and "cron" in insp.details
    assert insp.details["memory"]["enabled"] is True
    assert "memory.retrieve" in insp.capabilities
    assert "memory.propose" in insp.capabilities
    assert "skill.propose" in insp.capabilities
    assert "long_task.run" in insp.capabilities


# ──────────────── human(--json 아닌) 출력에 details 표시 ────────────────
def test_human_inspect_prints_details(capsys):
    """`dipeen providers inspect omo`(사람용)가 team_mode/runtime을 출력 — --json 없이도 보이게."""
    from app.nat.cli import main
    rc = main(["providers", "inspect", "omo"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "team_mode" in out        # details가 사람 출력에도 노출
    assert "runtime" in out
