"""WorkerRegistry (M6 / Core 측) — Worker(현장 노드) 등록 + heartbeat 생존.

capability 기반 dispatch의 근거. heartbeat가 끊긴 worker는 offline → 그 worker의 lease는 만료 재큐된다.
JSON-per-worker(workers/{id}.json). Core는 worker 내부(provider CLI)를 모른다 — capability만 안다.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ..contracts import WorkerInfo, _now


class WorkerRegistry:
    def __init__(self, store_root: str | Path):
        self.dir = Path(store_root) / "workers"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, worker_id: str) -> Path:
        return self.dir / f"{worker_id}.json"

    def _save(self, info: WorkerInfo) -> WorkerInfo:
        self._path(info.worker_id).write_text(info.model_dump_json(indent=2), encoding="utf-8")
        return info

    def register(self, info: WorkerInfo) -> WorkerInfo:
        info.last_heartbeat = _now()
        info.state = "online"
        return self._save(info)

    def get(self, worker_id: str) -> Optional[WorkerInfo]:
        p = self._path(worker_id)
        return WorkerInfo.model_validate_json(p.read_text(encoding="utf-8")) if p.exists() else None

    def heartbeat(self, worker_id: str) -> Optional[WorkerInfo]:
        w = self.get(worker_id)
        if w:
            w.last_heartbeat = _now()
            w.state = "online"
            self._save(w)
        return w

    def all(self) -> list[WorkerInfo]:
        return [WorkerInfo.model_validate_json(p.read_text(encoding="utf-8"))
                for p in sorted(self.dir.glob("*.json"))]

    def online(self, *, now: Optional[datetime] = None, ttl_sec: int = 60) -> list[WorkerInfo]:
        """heartbeat가 ttl 안에 있는 worker만. 끊긴 worker는 dispatch 대상에서 제외."""
        now = now or _now()
        return [w for w in self.all() if (now - w.last_heartbeat) <= timedelta(seconds=ttl_sec)]
