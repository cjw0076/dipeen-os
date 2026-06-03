"""OMO(oh-my-opencode) provider inspect (M11a) — read-only static 진단.

번들 OMO 3.11.0은 standalone harness(Ralph Loop·tmux·단일 프로세스 병렬)다. team orchestration
(team_create/team_send_message/team_task_*)은 OMO가 아니라 Dipeen 책임 — capability로 허위 보고하지
않고 known_blockers로 정직하게 표기한다(Evidence First). 감지는 static(which=PATH / config 파일),
버전만 설치 확인 후 격리된 probe_version.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from .. import lifecycle
from ..inspection import ProviderInspection, find_existing, probe_version, runnable_blockers, which_any

_BINARIES = ["omo", "oh-my-opencode", "opencode"]
# 실제 config(신)=oh-my-openagent.json. 구 oh-my-opencode.json/opencode.json도 탐지(하위호환).
_CONFIG_FILES = ["oh-my-openagent.json", "oh-my-opencode.json", "opencode.json"]
# 출처: agent-client/dipeen_agent/runners/omo_opencode.py (worker 실행기, install_cmd)
_INSTALL = "OMO 미설치 — `bunx oh-my-openagent install`(OpenCode Ultimate; Codex Light: `npx lazycodex-ai install`) — ⚠️ global npm·`npx omo`·`bunx omo` 금지"
_TEAM_BLOCKER = (
    "team tools(team_create/team_send_message/team_task_*)가 번들 OMO 3.11.0에 없음 "
    "— team orchestration은 Dipeen-side(OMO는 standalone harness)"
)


def _config_dirs() -> list[str]:
    """OMO/opencode config가 위치할 후보 디렉토리(static — env/홈 조회만)."""
    dirs: list[str] = []
    explicit = os.environ.get("OPENCODE_CONFIG_DIR")
    if explicit:
        dirs.append(explicit)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    dirs.append(os.path.join(xdg, "opencode") if xdg
                else os.path.join(os.path.expanduser("~"), ".config", "opencode"))
    appdata = os.environ.get("APPDATA")
    if appdata:
        dirs.append(os.path.join(appdata, "opencode"))
    return dirs


def _omo_home() -> str:
    """OMO 런타임 베이스(team/run state). OMO_HOME > ~/.omo (static — 조회만)."""
    return os.environ.get("OMO_HOME") or os.path.join(os.path.expanduser("~"), ".omo")


def omo_team_mode(config_paths: list[str]) -> dict:
    """Team Mode 설정 탐지(static — opencode config의 team_mode 키 읽기, 기본 off).

    team_mode 활성 시 12개 team_* tools가 열린다(team_create/send_message/task_*…). 미설정/미발견이면
    enabled=False(거짓보고 금지) — OMO는 standalone harness가 기본이고 team은 opt-in 구성이다."""
    for p in config_paths:
        try:
            cfg = json.loads(Path(p).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        tm = cfg.get("team_mode") if isinstance(cfg, dict) else None
        if isinstance(tm, dict):
            enabled = bool(tm.get("enabled"))
            return {"enabled": enabled, "configured": True,
                    "max_parallel_members": tm.get("max_parallel_members"),
                    "max_members": tm.get("max_members"),
                    "tools_available": 12 if enabled else 0}
    return {"enabled": False, "configured": False, "tools_available": 0}


def omo_runtime(home: Optional[str] = None) -> dict:
    """OMO runtime state 탐지(static FS — ~/.omo/{teams,runtime} 카운트만). OMO state는 provider-local —
    Dipeen이 소유하지 않고 읽기만(이후 Event/Artifact로 정규화)."""
    base = home or _omo_home()
    teams, runtime = os.path.join(base, "teams"), os.path.join(base, "runtime")
    return {"base_dir": base,
            "declared_teams": len(os.listdir(teams)) if os.path.isdir(teams) else 0,
            "active_runs": len(os.listdir(runtime)) if os.path.isdir(runtime) else 0}


def inspect() -> ProviderInspection:
    config_paths = find_existing([os.path.join(d, f) for d in _config_dirs() for f in _CONFIG_FILES])
    binary = which_any(_BINARIES)
    hint, deps = lifecycle.install_hint_for("omo"), lifecycle.runtime_deps_for("omo")
    team_mode = omo_team_mode(config_paths)
    details = {"team_mode": team_mode, "runtime": omo_runtime()}
    if not binary:
        return ProviderInspection(
            name="omo", installed=False, config_paths=config_paths,
            known_blockers=[_TEAM_BLOCKER],
            recommended_next_action=_INSTALL,
            install_hint=hint, runtime_deps=deps, details=details)   # capability_advertised=False(probe 전): default
    version = probe_version(binary)
    # capability: provider.omo(routing) + cli.harness + (team_mode on이면) omo.team_mode + declared(omo.review/subtasks, M11c+ 제공예정)
    caps = ["provider.omo", "cli.harness"]
    if config_paths:
        caps.append("configured")
    if team_mode["enabled"]:
        caps.append("omo.team_mode")
    caps += ["omo.review", "omo.subtasks", "workspace.write"]
    return ProviderInspection(
        name="omo", installed=True, binary_path=binary, version=version,
        config_paths=config_paths, capabilities=caps,
        known_blockers=[_TEAM_BLOCKER, *runnable_blockers(version)],
        recommended_next_action="M11b: read-only adapter via worker (`omo doctor --json`)",
        install_hint=hint, runtime_deps=deps, details=details)       # 설치돼도 광고는 probe healthy 후에만

