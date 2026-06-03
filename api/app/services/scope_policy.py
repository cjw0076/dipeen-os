"""기본 scope 정책 — 결정 카드가 명시하지 않아도 *항상* 적용되는 경계.

원칙(`docs/dipeen-wrap-principle.md`): 경계는 HQ가 소유한다.
BYOK 불변식: 어떤 runner도 비밀/키 파일을 만지면 안 된다(멤버 키는 로컬만, 서버 미수신).
결정 카드(entry gate)는 *추가* 범위를 줄 수 있지만, 아래 비밀 deny는 제거할 수 없다.

이 모듈은 순수(IO·LLM 없음) → 결정론적·테스트 가능. pm_loop 배정과 Gatekeeper가 공유한다.
"""
from __future__ import annotations

from app.schemas.runner import ScopeClaims

# 항상 deny — runner가 절대 만지면 안 되는 비밀/키 경로. (Gatekeeper가 위반 시 needs_human)
SECRET_DENY_PATHS: list[str] = [
    ".env", "*.env", "**/.env",
    "**/.credentials.json", "**/credentials.json",
    "**/secrets/**", "**/*.pem", "**/id_rsa*", "**/*.key",
]


def default_scope_claims(task_def: dict | None = None) -> ScopeClaims:
    """계획의 한 태스크(task_def)에서 ScopeClaims를 만든다.

    - 비밀 deny(`SECRET_DENY_PATHS`)는 항상 포함(카드가 빼지 못함).
    - allow_paths / max_files / high_risk는 task_def가 있으면 반영(결정 카드 = entry gate).
    """
    td = task_def or {}
    deny = list(SECRET_DENY_PATHS)
    for extra in (td.get("deny_paths") or []):
        if extra not in deny:
            deny.append(extra)
    return ScopeClaims(
        allow_paths=list(td.get("allow_paths") or []),
        deny_paths=deny,
        max_files=td.get("max_files"),
        requires_human_approval=bool(td.get("high_risk", False)),
    )
