"""runners — RunnerAdapter 패키지 (W0~W6).

study-guide §7.4: Node는 RunnerAdapter로 omo/hermes/claude-code 중 하나를 실행해
동일한 RunReport를 낸다. 어댑터는 base.RunnerAdapter Protocol을 따른다.
레지스트리(get_adapter/all_health)는 어댑터 모듈(claude_code/omo_*/hermes_runner)에서 채운다.
"""
from .base import (
    RunContext,
    RunnerAdapter,
    RunnerHealth,
    RUNNER_NAMES,
    build_run_report,
    finalize_artifacts,
    git_changed_files,
    run_checks,
    which,
)

__all__ = [
    "RunContext", "RunnerAdapter", "RunnerHealth", "RUNNER_NAMES",
    "build_run_report", "finalize_artifacts", "git_changed_files", "run_checks", "which",
    "get_adapter", "resolve_runner_name", "all_health", "provisioning",
]


def provisioning() -> dict:
    """name → {install_cmd, auth_cmd, runtime_deps} — doctor/setup가 설치·auth에 쓴다."""
    return {
        a.name: {
            "install_cmd": getattr(a, "install_cmd", ""),
            "auth_cmd": getattr(a, "auth_cmd", ""),
            "runtime_deps": list(getattr(a, "runtime_deps", [])),
        }
        for a in _registry().values()
    }


def _registry() -> dict:
    """name → adapter 인스턴스. 어댑터는 무상태라 매 호출 새로 만들어도 무방(순환 import 회피용 지연 import)."""
    from .claude_code import ClaudeCodeAdapter
    from .omo_opencode import OmoOpencodeAdapter
    from .omo_codex_light import OmoCodexLightAdapter
    from .hermes_runner import HermesRunnerAdapter
    return {
        "claude-code": ClaudeCodeAdapter(),
        "omo-opencode": OmoOpencodeAdapter(),
        "omo-codex-light": OmoCodexLightAdapter(),
        "hermes": HermesRunnerAdapter(),
    }


def get_adapter(name: str) -> RunnerAdapter:
    """러너 이름으로 어댑터 선택. 모르는 이름은 기본(claude-code)로 fail-safe."""
    reg = _registry()
    return reg.get(name) or reg["claude-code"]


def resolve_runner_name(task: dict | None = None, config: dict | None = None) -> str:
    """이 노드/태스크가 쓸 러너 이름. task.runner(HQ 지정) 우선 → config/env(AGENT_EXECUTOR)."""
    explicit = (task or {}).get("runner")
    if explicit in RUNNER_NAMES:
        return explicit
    try:
        from ..config import AGENT_EXECUTOR
        return "omo-opencode" if AGENT_EXECUTOR == "omo" else "claude-code"
    except Exception:
        return "claude-code"


async def all_health() -> list:
    """모든 러너 health (dipeen-node doctor용). 미설치는 available=False로 정직하게."""
    out = []
    for adapter in _registry().values():
        try:
            out.append(await adapter.health())
        except Exception as e:  # noqa: BLE001
            out.append(RunnerHealth(adapter.name, False, f"health 오류: {e}"))
    return out
