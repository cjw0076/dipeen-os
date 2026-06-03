"""NAT Adapters (M2) — Agent Runtime을 *실행만* 하는 경계. 번역은 NAT(M3), 판정은 Verifier(M4)."""
from .base import (
    AgentAdapter,
    CliExecAdapter,
    CommandRunner,
    ExecResult,
    child_env,
    default_runner,
    detect_changed_files,
)
from .claude import ClaudeAdapter
from .codex import CodexAdapter

__all__ = [
    "AgentAdapter",
    "CliExecAdapter",
    "CommandRunner",
    "ExecResult",
    "child_env",
    "default_runner",
    "detect_changed_files",
    "ClaudeAdapter",
    "CodexAdapter",
]
