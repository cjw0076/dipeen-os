"""Routing Preview — User-facing "이 작업은 누구에게 갈지"를 백엔드가 계산.

User는 capability/lease를 몰라야 하므로, UI는 배정(역할/사람/repo)을 주고 "→ 민준 MacBook, Claude 가능"
같은 사람이 읽는 결과를 받는다. preview_routing이 그 데이터를 만든다(현재 등록된 worker 대상).
"""
from app.nat.contracts import AssignmentSpec, WorkerInfo
from app.nat.core.routing import preview_routing


def _w(wid, caps, state="online"):
    return WorkerInfo(worker_id=wid, capabilities=caps, state=state)


def test_preview_includes_only_matching_workers():
    workers = [
        _w("worker.minjun-mac", ["provider.claude", "role.frontend", "user.minjun", "repo.ezmap-web", "workspace.write"]),
        _w("worker.soojin-pc", ["provider.claude", "role.backend", "user.soojin", "repo.ezmap-api", "workspace.write"]),
    ]
    out = preview_routing(AssignmentSpec(role="frontend", repo="ezmap-web"), provider="claude", workers=workers)
    ids = [m["worker_id"] for m in out["matching_workers"]]
    assert ids == ["worker.minjun-mac"]          # backend/다른 repo worker는 제외
    assert out["deliverable"] is True
    assert "role.frontend" in out["required_capabilities"]


def test_preview_extracts_human_labels():
    workers = [_w("worker.minjun-mac", ["provider.claude", "role.frontend", "user.minjun", "workspace.write"])]
    out = preview_routing(AssignmentSpec(role="frontend"), provider="claude", workers=workers)
    m = out["matching_workers"][0]
    assert m["user"] == "minjun" and m["role"] == "frontend"   # UI 표시용 사람-읽는 라벨


def test_preview_no_online_worker_is_not_deliverable_with_reason():
    workers = [_w("worker.soojin-pc", ["provider.claude", "role.backend", "workspace.write"])]
    out = preview_routing(AssignmentSpec(role="frontend"), provider="claude", workers=workers)
    assert out["deliverable"] is False
    assert out["online_matches"] == 0
    assert "role.frontend" in out["reason"]      # 왜 못 가는지 사람이 읽게


def test_preview_counts_online_only():
    workers = [
        _w("w.on", ["provider.claude", "role.fe", "workspace.write"], state="online"),
        _w("w.off", ["provider.claude", "role.fe", "workspace.write"], state="offline"),
    ]
    out = preview_routing(AssignmentSpec(role="fe"), provider="claude", workers=workers)
    assert len(out["matching_workers"]) == 2     # 둘 다 capability는 맞음
    assert out["online_matches"] == 1            # 온라인만 카운트
    assert out["deliverable"] is True
