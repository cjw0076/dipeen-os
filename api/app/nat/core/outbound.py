"""Outbound NAT (M3 / §10) — TaskEnvelope(+identity/context) → AgentInvocation.

Core는 provider를 모른다 — identity.binding.adapter로 registry에서 플러그인을 찾아 위임할 뿐.
`if adapter == "claude"` 같은 분기 0건. 실제 프롬프트 렌더/ env 결정은 provider plugin이 한다.
"""
from __future__ import annotations

from typing import Optional

from ..contracts import AgentIdentity, AgentInvocation, TaskEnvelope
from .registry import get_plugin


def build_invocation(task: TaskEnvelope, identity: AgentIdentity, *, run_id: str,
                     workspace_root: str, context_pack: Optional[str] = None) -> AgentInvocation:
    """TaskEnvelope를 identity가 가리키는 provider의 AgentInvocation으로 번역(provider plugin 위임)."""
    plugin = get_plugin(identity.binding.adapter)
    return plugin.to_invocation(
        task, run_id=run_id, identity_id=identity.identity_id,
        workspace_root=workspace_root, context_pack=context_pack,
    )
