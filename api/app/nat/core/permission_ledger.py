"""PermissionLedger (M7 / Core) — PermissionRequest + 결정 영속(감사 추적). JSON-per-request.

위험 행동의 요청·정책결정·승인·실행을 불변 기록으로 남긴다 — "누가 무엇을 승인했나"에 답할 수 있게.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..contracts import PermissionRequest


class PermissionLedger:
    def __init__(self, store_root: str | Path):
        self.root = Path(store_root)
        self.dir = self.root / "permissions"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, pid: str) -> Path:
        return self.dir / f"{pid}.json"

    def save(self, req: PermissionRequest) -> PermissionRequest:
        self._path(req.permission_request_id).write_text(req.model_dump_json(indent=2), encoding="utf-8")
        return req

    def get(self, pid: str) -> Optional[PermissionRequest]:
        p = self._path(pid)
        return PermissionRequest.model_validate_json(p.read_text(encoding="utf-8")) if p.exists() else None

    def all(self) -> list[PermissionRequest]:
        return [PermissionRequest.model_validate_json(p.read_text(encoding="utf-8"))
                for p in sorted(self.dir.glob("P-*.json"))]

    def list_pending(self) -> list[PermissionRequest]:
        return [r for r in self.all() if r.state == "requested"]
