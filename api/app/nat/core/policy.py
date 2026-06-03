"""PolicyEngine (M7 / Core) — PermissionAction을 위험 등급으로 분류. agent는 요청만, Core가 분류.

Hard Deny(v0 무조건 차단) / Human Approval(승인 후 로컬 worker 실행) / Auto Allow(sandbox 안전).
Manual Handoff는 승인됐으나 executor가 없을 때 *실행 단계*에서 갈린다(여기선 deny/human/auto만).
"""
from __future__ import annotations

from ..contracts import PermissionAction, PolicyDecision

# v0 무조건 차단 — secret/prod deploy/global install/arbitrary network·shell. 실행 안 함.
_HARD_DENY = {"secret.read", "deployment.run", "package.install", "network.request", "shell.run"}
# 사람 승인 후 로컬 worker 실행(allowlisted side effect)
_HUMAN_APPROVAL = {"git.commit", "git.push", "github.issue.create", "github.pr.create"}
# 자동 허용 — sandbox/worktree 안전 작업
_AUTO_ALLOW = {"workspace.read", "workspace.write", "git.diff"}


def classify(action: PermissionAction | str) -> PolicyDecision:
    if action in _HARD_DENY:
        return "deny"
    if action in _HUMAN_APPROVAL:
        return "require_human_approval"
    if action in _AUTO_ALLOW:
        return "auto_allow"
    return "require_human_approval"      # 모르는 action은 보수적으로 사람 승인
