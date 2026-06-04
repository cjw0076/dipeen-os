"""CommandQueue (M6 / Core 측) — pull-based 실행 지시 큐.

Worker가 poll로 *capability에 맞는* command를 lease(점유)해 가져간다. Core는 worker에 push하지 않는다
(worker가 NAT/방화벽 뒤여도 OK). lease 만료 시 재큐(죽은 worker 복구). JSON-per-command 영속.
주의: v0 in-process 단일스레드 가정 — 멀티 worker/HTTP는 DB 트랜잭션 lock 필요(추후).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from ..contracts import Command, _now


class CommandQueue:
    def __init__(self, store_root: str | Path):
        self.dir = Path(store_root) / "commands"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, command_id: str) -> Path:
        return self.dir / f"{command_id}.json"

    def _save(self, cmd: Command) -> Command:
        self._path(cmd.command_id).write_text(cmd.model_dump_json(indent=2), encoding="utf-8")
        return cmd

    def _all(self) -> list[Command]:
        return [Command.model_validate_json(p.read_text(encoding="utf-8"))
                for p in sorted(self.dir.glob("CMD-*.json"))]

    def get(self, command_id: str) -> Optional[Command]:
        p = self._path(command_id)
        return Command.model_validate_json(p.read_text(encoding="utf-8")) if p.exists() else None

    def enqueue(self, cmd: Command) -> Command:
        cmd.state = "queued"
        return self._save(cmd)

    def poll(self, worker_id: str, capabilities: list[str], *, now: Optional[datetime] = None,
             lease_ttl_sec: int = 300) -> Optional[Command]:
        """capability를 만족하는 queued command 1개를 lease해 반환. 없으면 None(=할 일 없음)."""
        now = now or _now()
        caps = set(capabilities)
        for cmd in sorted(self._all(), key=lambda c: c.created_at):
            if cmd.state == "queued" and set(cmd.required_capabilities).issubset(caps):
                cmd.state = "leased"
                cmd.lease_owner = worker_id
                cmd.lease_id = uuid.uuid4().hex
                cmd.lease_expires_at = now + timedelta(seconds=lease_ttl_sec)
                return self._save(cmd)
        return None

    def unmatched_capabilities(self, capabilities: list[str]) -> list[dict]:
        """Read-only diagnostic: queued commands this worker CANNOT take because its capabilities
        don't cover the requirement. Returns {command_id, required, missing} so a None poll can be
        explained ('your caps miss repo.X') instead of silently skipped."""
        caps = set(capabilities)
        out: list[dict] = []
        for cmd in sorted(self._all(), key=lambda c: c.created_at):
            if cmd.state == "queued":
                req = set(cmd.required_capabilities)
                if not req.issubset(caps):
                    out.append({"command_id": cmd.command_id, "required": sorted(req),
                                "missing": sorted(req - caps)})
        return out

    def ack(self, command_id: str, worker_id: str) -> Optional[Command]:
        cmd = self.get(command_id)
        if cmd and cmd.lease_owner == worker_id and cmd.state == "leased":
            cmd.state = "running"
            return self._save(cmd)
        return cmd

    def complete(self, command_id: str) -> Optional[Command]:
        cmd = self.get(command_id)
        if cmd:
            cmd.state = "completed"
            return self._save(cmd)
        return cmd

    def fail(self, command_id: str) -> Optional[Command]:
        cmd = self.get(command_id)
        if cmd:
            cmd.state = "failed"
            return self._save(cmd)
        return cmd

    def expire_leases(self, *, now: Optional[datetime] = None) -> int:
        """만료된 lease를 queued로 되돌림(죽은 worker 복구). 반환=재큐 개수."""
        now = now or _now()
        n = 0
        for cmd in self._all():
            if cmd.state in ("leased", "running") and cmd.lease_expires_at and now > cmd.lease_expires_at:
                cmd.state = "queued"
                cmd.lease_owner = None
                cmd.lease_expires_at = None
                self._save(cmd)
                n += 1
        return n
