"""RunStore (M1) — Run / TaskEnvelope JSON 영속. Retry=새 Run이므로 한 Task에 Run이 누적된다(§6).

tasks/T-*.json, runs/R-*.json. TaskState 전이는 Reconciler가 결정하고 여기로 영속(event도 함께 남김 — 호출측).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..contracts import Run, TaskEnvelope, TaskState


class RunStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        (self.root / "runs").mkdir(parents=True, exist_ok=True)
        (self.root / "tasks").mkdir(parents=True, exist_ok=True)

    # ── Task ──
    def save_task(self, task: TaskEnvelope) -> TaskEnvelope:
        (self.root / "tasks" / f"{task.task_id}.json").write_text(
            task.model_dump_json(indent=2), encoding="utf-8")
        return task

    def load_task(self, task_id: str) -> Optional[TaskEnvelope]:
        p = self.root / "tasks" / f"{task_id}.json"
        if not p.exists():
            return None
        return TaskEnvelope.model_validate_json(p.read_text(encoding="utf-8"))

    def update_task_state(self, task_id: str, state: TaskState) -> Optional[TaskEnvelope]:
        t = self.load_task(task_id)
        if t is None:
            return None
        t.state = state
        return self.save_task(t)

    # ── Run (누적) ──
    def save_run(self, run: Run) -> Run:
        (self.root / "runs" / f"{run.run_id}.json").write_text(
            run.model_dump_json(indent=2), encoding="utf-8")
        return run

    def runs_for(self, task_id: str) -> list[Run]:
        out: list[Run] = []
        for p in sorted((self.root / "runs").glob("R-*.json")):
            r = Run.model_validate_json(p.read_text(encoding="utf-8"))
            if r.task_id == task_id:
                out.append(r)
        return sorted(out, key=lambda r: r.attempt)

    def next_attempt(self, task_id: str) -> int:
        return len(self.runs_for(task_id)) + 1
