"""M11b Read-only Provider Probe — HQ→worker transport (provider.probe command).

permission.execute 미러: non-run command를 worker가 실행, task-less Event(provider.probed)로 결과 수집.
omo doctor(현재 bun ENOENT)·hermes status를 정직하게 캡처. Core/worker는 provider 불가지론(argv payload).
"""
import json
import subprocess

import pytest


# ──────────────── Task 1: contracts (provider.probe / task-less / provider.probed) ────────────────
def test_command_probe_is_task_less():
    from app.nat.contracts import Command
    cmd = Command(command_type="provider.probe", provider="omo",
                  required_capabilities=["provider.omo"], payload={"argv": ["omo", "doctor"]})
    assert cmd.command_type == "provider.probe"
    assert cmd.task_id is None
    assert cmd.run_id is None
    assert cmd.payload["argv"] == ["omo", "doctor"]


def test_run_command_still_carries_task_id():
    from app.nat.contracts import Command
    cmd = Command(command_type="run.start", task_id="T-1", run_id="R-1", provider="claude")
    assert cmd.task_id == "T-1" and cmd.run_id == "R-1"


def test_provider_probed_event_is_task_less():
    from app.nat.contracts import Event
    ev = Event(event_type="provider.probed", producer="dipeen://worker/w1",
               payload={"provider": "hermes", "exit": 0})
    assert ev.event_type == "provider.probed"
    assert ev.task_id is None


# ──────────────── Task 2: provider probe 모듈 (argv + parse) ────────────────
def test_omo_probe_argv():
    from app.nat.providers.omo.probe import probe_argv
    argv = probe_argv()
    assert argv[0] == "omo" and "doctor" in argv


def test_omo_parse_bun_enoent():
    from app.nat.providers.omo.probe import parse_probe
    r = parse_probe(stdout="", stderr="oh-my-opencode: failed to execute Bun: spawnSync bun ENOENT", exit_code=2)
    assert r["ok"] is False
    assert r.get("runtime_blocker") == "bun"


def test_omo_parse_doctor_json():
    from app.nat.providers.omo.probe import parse_probe
    r = parse_probe(stdout='{"version":"3.11.0","checks":[]}', stderr="", exit_code=0)
    assert r["ok"] is True
    assert r["doctor"]["version"] == "3.11.0"


def test_hermes_probe_argv():
    from app.nat.providers.hermes.probe import probe_argv
    assert probe_argv()[0] == "hermes"


def test_hermes_parse_status_lines():
    from app.nat.providers.hermes.probe import parse_probe
    r = parse_probe(stdout="Hermes Agent v0.15.1\nMemory: ~/.hermes\n", stderr="", exit_code=0)
    assert r["ok"] is True
    assert any("Hermes" in ln for ln in r["lines"])


# ──────────────── Task 3: dispatch_probe ────────────────
def test_dispatch_probe_enqueues_task_less(tmp_path):
    from app.nat.core.command_queue import CommandQueue
    from app.nat.core.conductor import dispatch_probe
    store = str(tmp_path / "nat")
    q = CommandQueue(store)
    cmd = dispatch_probe(q, provider="omo", argv=["omo", "doctor", "--json"])
    assert cmd.command_type == "provider.probe"
    assert cmd.task_id is None
    assert cmd.payload["argv"] == ["omo", "doctor", "--json"]
    assert cmd.required_capabilities == ["provider.omo"]
    leased = CommandQueue(store).poll("w1", ["provider.omo"])      # 맞는 capability worker가 lease 가능
    assert leased is not None and leased.command_id == cmd.command_id


# ──────────────── Task 4: worker _execute_probe (local, task-less event) ────────────────
def _run(coro):
    import asyncio
    return asyncio.run(coro)


def test_execute_probe_appends_event_task_less(tmp_path, monkeypatch):
    from app.nat.core.command_queue import CommandQueue
    from app.nat.core.conductor import dispatch_probe
    from app.nat.core.eventlog import EventLog
    from app.nat.core.worker_registry import WorkerRegistry
    from app.nat.worker import WorkerNode

    store = str(tmp_path / "nat")
    q = CommandQueue(store)
    cmd = dispatch_probe(q, provider="hermes", argv=["hermes", "status"])
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, "Hermes Agent v0.15.1\n", ""))
    w = WorkerNode("w1", capabilities=["provider.hermes"], queue=q,
                   registry=WorkerRegistry(store), store_root=store)
    _run(w.poll_and_run_once())

    probed = [e for e in EventLog(store).tail(10) if e.event_type == "provider.probed"]
    assert len(probed) == 1
    assert probed[0].task_id is None
    assert probed[0].payload["provider"] == "hermes"
    assert probed[0].payload["exit"] == 0
    assert "Hermes" in probed[0].payload["stdout"]
    assert CommandQueue(store).get(cmd.command_id).state == "completed"


def test_execute_probe_resolves_binary_via_which(tmp_path, monkeypatch):
    """Windows에서 'omo'(확장자 없음)는 subprocess가 omo.CMD를 못 찾는다(WinError 2). worker가 which로
    full path를 resolve해야 실제 실행된다(라이브에서 적발). generic resolve(provider 불가지론 유지)."""
    import shutil

    from app.nat.core.command_queue import CommandQueue
    from app.nat.core.conductor import dispatch_probe
    from app.nat.core.worker_registry import WorkerRegistry
    from app.nat.worker import WorkerNode

    store = str(tmp_path / "nat")
    q = CommandQueue(store)
    dispatch_probe(q, provider="omo", argv=["omo", "doctor", "--json"])
    monkeypatch.setattr(shutil, "which", lambda n: "C:/x/omo.CMD" if n == "omo" else None)
    captured = {}
    monkeypatch.setattr(subprocess, "run",
                        lambda argv, **k: captured.update(argv=list(argv)) or subprocess.CompletedProcess(argv, 0, "", ""))
    w = WorkerNode("w1", capabilities=["provider.omo"], queue=q,
                   registry=WorkerRegistry(store), store_root=store)
    _run(w.poll_and_run_once())
    assert captured["argv"][0] == "C:/x/omo.CMD"           # which로 resolve(.CMD)
    assert captured["argv"][1:] == ["doctor", "--json"]


def test_execute_probe_captures_failure(tmp_path, monkeypatch):
    from app.nat.core.command_queue import CommandQueue
    from app.nat.core.conductor import dispatch_probe
    from app.nat.core.eventlog import EventLog
    from app.nat.core.worker_registry import WorkerRegistry
    from app.nat.worker import WorkerNode

    store = str(tmp_path / "nat")
    q = CommandQueue(store)
    dispatch_probe(q, provider="omo", argv=["omo", "doctor", "--json"])
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 2, "", "spawnSync bun ENOENT"))
    w = WorkerNode("w1", capabilities=["provider.omo"], queue=q,
                   registry=WorkerRegistry(store), store_root=store)
    _run(w.poll_and_run_once())
    probed = [e for e in EventLog(store).tail(10) if e.event_type == "provider.probed"]
    assert probed[0].payload["exit"] == 2
    assert "bun" in probed[0].payload["stderr"].lower()


# ──────────────── Task 6: CLI providers probe (local in-process) ────────────────
def test_cli_probe_hermes_end_to_end(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, "Hermes Agent v0.15.1\nMemory: ok\n", ""))
    from app.nat.cli import main
    rc = main(["--store", str(tmp_path / "nat"), "providers", "probe", "hermes"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "hermes" in out
    assert "Hermes Agent v0.15.1" in out


def test_cli_probe_omo_reports_bun_blocker(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 2, "", "spawnSync bun ENOENT"))
    from app.nat.cli import main
    rc = main(["--store", str(tmp_path / "nat"), "providers", "probe", "omo"])
    assert rc == 0
    out = capsys.readouterr().out.lower()
    assert "bun" in out


# ──────────────── Task 5: http 경로 (service ingest + worker_http) ────────────────
def test_ingest_probe_result_appends_event_and_completes(tmp_path, monkeypatch):
    monkeypatch.setenv("NAT_WORKSPACE", str(tmp_path / "nat"))
    from app.nat.core.conductor import dispatch_probe
    from app.services import control_plane as cp
    q = cp._command_queue()
    cmd = dispatch_probe(q, provider="hermes", argv=["hermes", "status"])
    q.poll("w1", ["provider.hermes"])                       # w1이 lease
    res = cp.ingest_probe_result(worker_id="w1", command_id=cmd.command_id,
                                 probe={"provider": "hermes", "exit": 0,
                                        "stdout": "Hermes Agent v0.15.1", "stderr": ""})
    assert res is not None
    assert cp._command_queue().get(cmd.command_id).state == "completed"
    evs = [e for e in cp._event_log().tail(10) if e.event_type == "provider.probed"]
    assert evs and evs[-1].payload["provider"] == "hermes"
    assert evs[-1].task_id is None


def test_ingest_probe_result_rejects_non_lease_owner(tmp_path, monkeypatch):
    monkeypatch.setenv("NAT_WORKSPACE", str(tmp_path / "nat"))
    from app.nat.core.conductor import dispatch_probe
    from app.services import control_plane as cp
    q = cp._command_queue()
    cmd = dispatch_probe(q, provider="omo", argv=["omo", "doctor"])
    q.poll("w1", ["provider.omo"])                          # w1이 lease
    res = cp.ingest_probe_result(worker_id="w-other", command_id=cmd.command_id,
                                 probe={"provider": "omo", "exit": 2, "stdout": "", "stderr": "bun ENOENT"})
    assert res is None                                       # 점유자 아님 → 거부(위조 방지, permission 미러)


@pytest.mark.asyncio
async def test_worker_http_execute_probe_posts_result(monkeypatch):
    from app.nat.contracts import Command
    from app.nat.worker_http import WorkerHttpClient
    posted = {}

    class _R:
        def raise_for_status(self): pass
        def json(self): return {}

    class FakeHttp:
        async def post(self, url, json=None):
            posted["url"] = url
            posted["json"] = json
            return _R()

    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, "Hermes Agent v0.15.1", ""))
    cmd = Command(command_type="provider.probe", provider="hermes", payload={"argv": ["hermes", "status"]})
    w = WorkerHttpClient("w1", ["provider.hermes"], http=FakeHttp())
    await w._execute_probe(cmd)
    assert "probe-result" in posted["url"]
    assert posted["json"]["provider"] == "hermes"
    assert posted["json"]["exit"] == 0
