"""NAT-hermes provider inspect (M11a) — read-only 진단.

무관: legacy `api/app/routers/hermes.py`(WebSocket A2A relay). 이건 외부 제품 Nous Research
hermes-agent CLI를 감지한다. memory/skill/scheduler/gateway는 외부 제품의 *선언된* 기능이라
static probe로 검증되지 않는다 → (external) 태그로 표기(허위 capability 금지). 감지는 static
(which=PATH / config 파일), 버전만 설치 확인 후 격리된 probe_version.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .. import lifecycle
from ..inspection import ProviderInspection, find_existing, probe_version, runnable_blockers, which_any

# 출처: agent-client/dipeen_agent/runners/hermes_runner.py (worker 실행기, install_cmd/auth_cmd)
_INSTALL_CMD = "uv tool install --python 3.11 git+https://github.com/NousResearch/hermes-agent"
_AUTH_CMD = "hermes model   # provider/model 선택(interactive, TTY) — Nous Portal/OpenRouter/OpenAI 등"
# 외부 제품의 *선언* 기능 — static probe로 미검증임을 (external)로 명시(details.declared)
_DECLARED = ["memory(external)", "skill(external)", "scheduler(external)", "gateway(external)"]
# Dipeen 통합 시 hermes provider가 제공할 capability(M12b+). routing은 provider.hermes로 별개.
_INTEGRATION_CAPS = ["provider.hermes", "memory.retrieve", "memory.propose", "skill.propose", "long_task.run"]


def _hermes_home() -> str:
    """Hermes state 홈. HERMES_HOME > ~/.hermes (static — 조회만)."""
    return os.environ.get("HERMES_HOME") or os.path.join(os.path.expanduser("~"), ".hermes")


def _config_candidates() -> list[str]:
    return [
        os.path.join(_hermes_home(), "config.yaml"),
        os.path.join(os.path.expanduser("~"), ".config", "hermes", "config.yaml"),
    ]


def hermes_runtime(home: Optional[str] = None) -> dict:
    """Hermes runtime 탐지(static — config.yaml + ~/.hermes/{memories,skills,cron,state.db}).

    **경계**: Hermes memory/skill은 personal/agent 것 — Dipeen Org Memory가 아니다. 여기선 *탐지만*(read-only).
    실제 ingest는 MemoryCandidate/SkillCandidate → review queue(M12c+). gateway 실행여부는 static 미검증."""
    base = home or _hermes_home()
    cfg: dict = {}
    cfg_path = os.path.join(base, "config.yaml")
    if os.path.isfile(cfg_path):
        try:
            import yaml
            cfg = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001 — 파싱 실패는 빈 설정으로(정직, 크래시 금지)
            cfg = {}
    mem = cfg.get("memory", {}) if isinstance(cfg, dict) else {}
    mem_dir, skills_dir, cron_dir = (os.path.join(base, d) for d in ("memories", "skills", "cron"))
    used = sum(len(Path(os.path.join(mem_dir, fn)).read_text(encoding="utf-8", errors="replace"))
               for fn in ("MEMORY.md", "USER.md") if os.path.isfile(os.path.join(mem_dir, fn)))
    char_limit = (mem.get("memory_char_limit") or 0) + (mem.get("user_char_limit") or 0)
    return {
        "memory": {"enabled": bool(mem.get("memory_enabled", False)), "path": mem_dir,
                   "used_chars": used, "char_limit": char_limit or None},
        "skills": {"path": skills_dir, "enabled": isinstance(cfg, dict) and cfg.get("skills") is not None,
                   "count": len(os.listdir(skills_dir)) if os.path.isdir(skills_dir) else 0},
        "cron": {"available": (isinstance(cfg, dict) and cfg.get("cron") is not None) or os.path.isdir(cron_dir),
                 "jobs": len(os.listdir(cron_dir)) if os.path.isdir(cron_dir) else 0,
                 "gateway_running": False},     # static inspect로는 미검증(process 스캔 필요 — M12a probe)
        "state_db": os.path.isfile(os.path.join(base, "state.db")),
        "declared": list(_DECLARED),            # 외부 제품 선언 기능(미검증)
    }


def inspect() -> ProviderInspection:
    config_paths = find_existing(_config_candidates())
    binary = which_any(["hermes"])
    hint, deps = lifecycle.install_hint_for("hermes"), lifecycle.runtime_deps_for("hermes")
    details = hermes_runtime()                       # memory/skills/cron 탐지(바이너리 없어도 ~/.hermes 읽음)
    if not binary:
        return ProviderInspection(
            name="hermes", installed=False, config_paths=config_paths,
            known_blockers=["hermes CLI(외부 Nous Research 제품)가 PATH에 없음"],
            recommended_next_action=f"설치: {_INSTALL_CMD}  →  인증: {_AUTH_CMD}",
            install_hint=hint, runtime_deps=deps, details=details)
    version = probe_version(binary)
    # capability=Dipeen 통합 시 제공할 것(memory.retrieve/propose·skill.propose·long_task.run). 외부 선언기능은 details.declared.
    return ProviderInspection(
        name="hermes", installed=True, binary_path=binary, version=version,
        config_paths=config_paths, capabilities=list(_INTEGRATION_CAPS),
        known_blockers=["capability는 Dipeen 통합 시 제공값 — 외부 기능은 static 미검증(M12a worker probe 필요)",
                        *runnable_blockers(version)],
        recommended_next_action=f"인증 확인: {_AUTH_CMD}  →  M12 read-only adapter(context/memory candidate)",
        install_hint=hint, runtime_deps=deps, details=details)
