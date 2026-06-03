"""Run real Dipeen NAT Core->Worker->provider CLI regression.

This is a build-time developer tool. Codex running this script is not a Dipeen
runtime actor, not omo, and not hermes. The runtime actors exercised here are
the worker node and the actual provider CLIs launched in temp workspaces.

Usage:
  cd api
  python scripts/real_nat_connected_regression.py --provider codex --provider claude
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.nat import providers as _providers  # noqa: E402
from app.nat.contracts import TaskEnvelope  # noqa: E402
from app.nat.core import conductor  # noqa: E402
from app.nat.core.artifact_store import ArtifactStore  # noqa: E402
from app.nat.core.command_queue import CommandQueue  # noqa: E402
from app.nat.core.eventlog import EventLog  # noqa: E402
from app.nat.core.run_store import RunStore  # noqa: E402
from app.nat.core.worker_registry import WorkerRegistry  # noqa: E402
from app.nat.worker import WorkerNode  # noqa: E402


def _init_git_workspace(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for argv in (
        ["git", "init", "-q"],
        ["git", "config", "user.email", "nat@dipeen.local"],
        ["git", "config", "user.name", "Dipeen NAT Test"],
    ):
        subprocess.run(argv, cwd=root, check=True, capture_output=True)


async def run_provider(provider: str, *, timeout: int, keep: bool) -> dict[str, Any]:
    root = Path(tempfile.mkdtemp(prefix=f"dipeen-real-nat-{provider}-"))
    store = root / "store"
    workspace = root / "workspace"
    _init_git_workspace(workspace)

    proof_file = f"{provider}-proof.txt"
    proof_line = f"HELLO DIPEEN REAL {provider.upper()} NAT"
    task = TaskEnvelope(
        title=f"real {provider} nat file proof",
        intent=(
            f"Create a file named {proof_file} in the workspace root containing exactly one line: "
            f"{proof_line}. Do not modify any other files. Do not install packages."
        ),
        acceptance=[
            {"type": "artifact_required", "artifact_type": "code_patch"},
            {"type": "file_required", "path": proof_file},
        ],
    )

    queue = CommandQueue(store)
    cmd = conductor.dispatch_run(queue, task, provider=provider, workspace_root=str(workspace), store_root=str(store))
    worker = WorkerNode(
        f"real-worker-{provider}",
        capabilities=[f"provider.{provider}", "workspace.write"],
        queue=CommandQueue(store),
        registry=WorkerRegistry(store),
        store_root=str(store),
        timeout_sec=timeout,
    )
    worker.register()
    result = await worker.poll_and_run_once(bypass=True)

    path = workspace / proof_file
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    task_after = RunStore(store).load_task(task.task_id)
    command_after = CommandQueue(store).get(cmd.command_id)
    artifacts = ArtifactStore(store).list(task_id=task.task_id)
    events = EventLog(store).by_task(task.task_id)
    passed = (
        result is not None
        and result.state == "DONE"
        and task_after is not None
        and task_after.state == "DONE"
        and command_after is not None
        and command_after.state == "completed"
        and path.exists()
        and text.strip() == proof_line
        and any(a.type == "code_patch" and a.status == "verified" for a in artifacts)
        and any(a.type == "file_change_set" and a.status == "verified" for a in artifacts)
    )

    output = {
        "provider": provider,
        "passed": passed,
        "root": str(root) if keep or not passed else "(temp)",
        "workspace": str(workspace) if keep or not passed else "(temp)",
        "store": str(store) if keep or not passed else "(temp)",
        "command_id": cmd.command_id,
        "command_state": command_after.state if command_after else None,
        "task_id": task.task_id,
        "task_state": task_after.state if task_after else None,
        "result_state": result.state if result else None,
        "reasons": result.reasons if result else None,
        "proof_file": proof_file,
        "proof_text": text,
        "artifacts": [
            {
                "id": a.artifact_id,
                "type": a.type,
                "status": a.status,
                "summary": a.summary,
                "evidence": [(e.kind, e.passed) for e in a.evidence],
            }
            for a in artifacts
        ],
        "events": [e.event_type for e in events],
    }
    if passed and not keep:
        shutil.rmtree(root, ignore_errors=True)
    return output


async def main() -> int:
    parser = argparse.ArgumentParser(description="Real Dipeen NAT connected regression")
    parser.add_argument("--provider", action="append", choices=["codex", "claude"], default=None)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--keep", action="store_true", help="Print temp paths even when the run passes")
    args = parser.parse_args()

    _providers.register_defaults()
    providers = args.provider or ["codex", "claude"]
    results = []
    for provider in providers:
        results.append(await run_provider(provider, timeout=args.timeout, keep=args.keep))

    print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    return 0 if all(item["passed"] for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
