"""Assignment Routing (Core) — 회의 배정(AssignmentSpec) → Command.required_capabilities.

"회의에서 민준이 FE 맡자" → assignment{role:frontend, user:minjun, repo:ezmap-web} →
caps=[provider.claude, workspace.write, repo.ezmap-web, role.frontend, user.minjun] →
CommandQueue.poll이 `caps ⊆ worker.capabilities`로 lease → **민준 머신 worker만** 가져간다.

capability 누적 = AND 필터: 필드가 많을수록 라우팅이 좁아진다(역할 풀 → 특정 사람의 특정 머신).
assignment가 없으면 기존 동작(provider + workspace.write) — 하위호환.
**Core는 push하지 않는다** — 이 함수는 "주소"만 만든다. 실제 전달은 worker가 poll로 당겨가는 것.
"""
from __future__ import annotations

from typing import Optional

from ..contracts import AssignmentSpec

_DEFAULT_BASE = ("workspace.write",)


def _ns(prefix: str, value: str) -> str:
    """'frontend' → 'role.frontend' / 이미 'role.frontend'면 그대로(idempotent namespacing)."""
    value = value.strip()
    return value if value.startswith(f"{prefix}.") else f"{prefix}.{value}"


def assignment_to_capabilities(assignment: Optional[AssignmentSpec], *, provider: str,
                               base: tuple[str, ...] = _DEFAULT_BASE) -> list[str]:
    """AssignmentSpec → required_capabilities(중복 제거, 순서 보존). assignment=None이면 풀 라우팅."""
    prov = (assignment.provider if assignment and assignment.provider else provider)
    caps: list[str] = [f"provider.{prov}", *base]
    if assignment is not None:
        if assignment.repo:
            caps.append(_ns("repo", assignment.repo))
        if assignment.role:
            caps.append(_ns("role", assignment.role))
        if assignment.user:
            caps.append(_ns("user", assignment.user))
        if assignment.preferred_worker:
            caps.append(_ns("worker", assignment.preferred_worker))
    seen: set[str] = set()
    out: list[str] = []
    for c in caps:                                 # dedupe, 순서 보존
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def resolve_workspace(cmd, workspaces: list) -> str:
    """command.workspace_ref → 이 worker의 local_path. **worker-side resolution** — HQ는 로컬 경로를
    모른다. workspace_ref가 없거나 worker가 그 workspace를 안 가졌으면 workspace_root(legacy fallback)."""
    ref = getattr(cmd, "workspace_ref", None)
    if ref:
        for ws in (workspaces or []):
            if ws.workspace_ref == ref:
                return ws.local_path or cmd.workspace_root
    return cmd.workspace_root


def _label(capabilities: list[str], prefix: str) -> Optional[str]:
    """worker capabilities에서 'prefix.X' → 'X' 추출(첫 매치). UI 표시용 사람-읽는 라벨."""
    for c in capabilities:
        if c.startswith(f"{prefix}."):
            return c[len(prefix) + 1:]
    return None


def preview_routing(assignment: Optional[AssignmentSpec], *, provider: str, workers: list) -> dict:
    """배정 → required_capabilities + *어느 worker가 받을지* (사람이 읽는 미리보기).

    User는 capability/poll/lease를 몰라야 한다 — 이 함수가 "이 작업 → 민준 MacBook, Claude 가능"을 만든다.
    Assignment UI가 역할/사람/repo를 고르는 동안 이걸 호출해 "누구에게 가는지"를 즉시 보여준다.
    """
    caps = assignment_to_capabilities(assignment, provider=provider)
    req = set(caps)
    target_ref = assignment.workspace_ref if assignment else None
    matching: list[dict] = []
    online = 0
    for w in workers:
        if req.issubset(set(w.capabilities)):
            is_online = (w.state == "online")
            online += int(is_online)
            ws_avail = (target_ref is None) or any(
                ws.workspace_ref == target_ref for ws in getattr(w, "workspaces", []) or [])
            matching.append({
                "worker_id": w.worker_id, "state": w.state, "online": is_online,
                "user": _label(w.capabilities, "user"), "role": _label(w.capabilities, "role"),
                "repo": _label(w.capabilities, "repo"), "workspace_available": ws_avail,
            })
    if not matching:
        reason = f"no worker has all of [{', '.join(caps)}]"
    elif online == 0:
        reason = f"{len(matching)} worker(s) match but none online"
    else:
        who = [m["user"] or m["worker_id"] for m in matching if m["online"]]
        reason = f"{online} online: {', '.join(who)}"
    return {
        "required_capabilities": caps,
        "matching_workers": matching,
        "online_matches": online,
        "deliverable": bool(matching),     # capability상 받을 worker 존재(오프라인이면 온라인 시 실행)
        "reason": reason,
    }
