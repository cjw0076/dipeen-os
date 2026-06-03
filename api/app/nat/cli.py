"""dipeen NAT CLI (M5) — `task run/inspect`, `artifacts list`, `events tail`.

in-process 파이프라인을 사람이 돌려 M1~M4를 실측 검증한다. `if agent==` 0건 — provider는 --adapter로만.
실행:  cd api && python -m app.nat.cli task run "<intent>" --adapter claude --workspace <dir> [--bypass]

두 평면: 이 CLI는 *빌드타임* 도구(개발자/나). --bypass + 실측은 *런타임* provider(별개 claude/codex)를
스크래치 워크스페이스에서 실행 — 그 agent는 격리 대상이지 나도 Dipeen Core도 아니다.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from . import providers as _providers
from .core import permission_nat, pipeline
from .core.artifact_store import ArtifactStore
from .core.command_queue import CommandQueue
from .core.eventlog import EventLog
from .core.permission_ledger import PermissionLedger
from .core.worker_registry import WorkerRegistry
from .executors import default_executors
from .worker import WorkerNode
from .workspace_cli import add_workspace_parser

_DEFAULT_STORE = os.environ.get("DIPEEN_NAT_STORE", "./nat-workspace")
_ACCEPT = {"code_patch": {"type": "artifact_required", "artifact_type": "code_patch"}}


def _print_inspect(view: dict) -> None:
    print(f"\n  task {view['task_id']}  [{view['state']}]  {view['title']}")
    for r in view["runs"]:
        print(f"    run {r['run_id']}  {r['identity']}  attempt={r['attempt']}")
    print("    artifacts:")
    for a in view["artifacts"]:
        ev = " ".join(f"{k}={'✓' if p else '✗'}" for k, p in a["evidence"])
        print(f"      {a['id']}  {a['type']:<16} [{a['status']:<8}] {ev}  {a['summary'][:50]}")
    print(f"    events: {len(view['events'])}  "
          + ", ".join(t for t, _ in view["events"][:8]) + ("…" if len(view["events"]) > 8 else ""))


async def _cmd_run(args) -> int:
    acceptance = [_ACCEPT[a] for a in (args.acceptance or []) if a in _ACCEPT]
    outcome = await pipeline.run_task(
        args.intent, provider=args.adapter, workspace_root=args.workspace,
        store_root=args.store, acceptance=acceptance, bypass=args.bypass,
        timeout_sec=args.timeout)
    print(f"\n[run] provider={args.adapter} run={outcome.run.run_id} → state={outcome.state}"
          + (f" ({outcome.failure_type})" if outcome.failure_type else ""))
    print(f"      exit={outcome.raw.exit_code}  changed_files={outcome.raw.changed_files}")
    print(f"      stdout[:200]={outcome.raw.stdout[:200]!r}")
    if outcome.reasons:
        print(f"      reasons={outcome.reasons}")
    _print_inspect(pipeline.inspect_task(outcome.task.task_id, store_root=args.store))
    print(f"\n  task_id={outcome.task.task_id}")
    return 0


def _cmd_inspect(args) -> int:
    view = pipeline.inspect_task(args.task_id, store_root=args.store)
    if args.json:
        print(json.dumps(view, ensure_ascii=False, indent=2))
    else:
        _print_inspect(view)
    return 0


# ──────── providers inspect (M11a) — read-only 진단. plugin 등록과 독립(미등록 provider도 진단 가능) ────────
_PROVIDER_INSPECT_MODULES = {
    "claude": "app.nat.providers.claude.inspect",
    "codex": "app.nat.providers.codex.inspect",
    "omo": "app.nat.providers.omo.inspect",
    "hermes": "app.nat.providers.hermes.inspect",
}


def _print_provider_inspection(insp) -> None:
    head = f"\n  provider {insp.name}  [{'✓ installed' if insp.installed else '✗ missing'}]"
    if insp.version:
        head += f"  v={insp.version}"
    print(head)
    if insp.binary_path:
        print(f"    binary: {insp.binary_path}")
    if insp.config_paths:
        print(f"    config: {', '.join(insp.config_paths)}")
    if insp.capabilities:
        print(f"    capabilities: {', '.join(insp.capabilities)}")
    # provider-고유 details(omo→team_mode/runtime, hermes→memory/skills/cron). declared(외부 선언)는 노이즈라 생략.
    for key, val in (getattr(insp, "details", {}) or {}).items():
        if key == "declared" or not isinstance(val, dict):
            continue
        inner = "  ".join(f"{k}={v}" for k, v in val.items() if k != "path" and v is not None)
        print(f"    {key}: {inner}")
    # Provider Lifecycle: 런타임 의존성 / 본체 설치 명령 / 광고 여부를 분리 보고.
    for d in getattr(insp, "runtime_deps", []):
        mark = "✓" if d.available else "✗ missing"
        tail = "" if d.available else f" — {d.install_cmd}"
        print(f"    runtime dep: {d.name} [{mark}]{tail}")
    if getattr(insp, "install_hint", ""):
        print(f"    install: {insp.install_hint}")
    advertised = getattr(insp, "capability_advertised", False)
    print(f"    capability advertised: {'yes' if advertised else 'no (run `providers probe` to advertise)'}")
    for b in insp.known_blockers:
        print(f"    blocker: {b}")
    print(f"    next: {insp.recommended_next_action}")


def _cmd_providers_inspect(args) -> int:
    import importlib
    names = list(_PROVIDER_INSPECT_MODULES) if args.name == "all" else [args.name]
    results = [importlib.import_module(_PROVIDER_INSPECT_MODULES[n]).inspect() for n in names]
    if args.json:
        payload = [r.to_dict() for r in results]
        print(json.dumps(payload if args.name == "all" else payload[0], ensure_ascii=False, indent=2))
    else:
        for r in results:
            _print_provider_inspection(r)
    return 0


def _print_provider_probe(name: str, parsed: dict) -> None:
    print(f"\n  probe {name}  [{'ok' if parsed.get('ok') else 'failed'}]")
    if parsed.get("runtime_blocker"):
        print(f"    runtime blocker: {parsed['runtime_blocker']} — {parsed.get('reason', '')}")
    if parsed.get("version_hint"):
        print(f"    version: {parsed['version_hint']}")
    for ln in (parsed.get("lines") or [])[:10]:
        print(f"    | {ln}")
    if parsed.get("doctor"):
        print(f"    doctor: {json.dumps(parsed['doctor'], ensure_ascii=False)[:300]}")
    if parsed.get("raw_stderr"):
        print(f"    stderr: {parsed['raw_stderr'][:200]}")


def _cmd_providers_probe(args) -> int:
    """provider 라이브 probe(M11b): probe command enqueue → in-process worker가 doctor/status 실행 → event 파싱.
    이 CLI는 worker 머신에서 도는 *빌드타임* 도구(Core api 아님) — Core가 provider를 직접 실행하지 않는다."""
    import importlib

    from .core.command_queue import CommandQueue
    from .core.conductor import dispatch_probe
    from .core.eventlog import EventLog
    from .core.worker_registry import WorkerRegistry
    from .worker import WorkerNode

    probe_mod = importlib.import_module(f"app.nat.providers.{args.name}.probe")
    q = CommandQueue(args.store)
    dispatch_probe(q, provider=args.name, argv=probe_mod.probe_argv())
    worker = WorkerNode("w-probe", capabilities=[f"provider.{args.name}"], queue=q,
                        registry=WorkerRegistry(args.store), store_root=args.store)
    asyncio.run(worker.poll_and_run_once())
    evs = [e for e in EventLog(args.store).tail(20)
           if e.event_type == "provider.probed" and (e.payload or {}).get("provider") == args.name]
    if not evs:
        print(f"probe 결과 없음(provider={args.name})")
        return 1
    p = evs[-1].payload
    parsed = probe_mod.parse_probe(p.get("stdout", ""), p.get("stderr", ""), p.get("exit", -1))
    if args.json:
        print(json.dumps(parsed, ensure_ascii=False, indent=2))
    else:
        _print_provider_probe(args.name, parsed)
    return 0


def _cmd_providers_render(args) -> int:
    """M11c dry-run: TaskEnvelope → provider invocation 렌더(outbound). **실행 0** — preview만.
    omo/hermes/claude/codex 등록된 NAT plugin의 to_invocation으로 위임(Core는 provider 모름)."""
    from .contracts import AgentBinding, AgentIdentity, TaskEnvelope
    from .core import outbound

    task = TaskEnvelope(title=args.intent[:48], intent=args.intent)
    identity = AgentIdentity(identity_id=f"agent://team/{args.name}", role=args.name,
                             binding=AgentBinding(adapter=args.name))
    inv = outbound.build_invocation(task, identity, run_id="R-preview", workspace_root=args.workspace)
    if args.json:
        print(json.dumps(inv.model_dump(), ensure_ascii=False, indent=2))
    else:
        print(f"\n  render {args.name}  (dry-run, no exec)")
        print(f"    prompt:\n{inv.prompt}")
        print(f"    workspace: {inv.workspace_root}   env: {inv.env}")
    return 0


def _cmd_providers_install(args) -> int:
    """print-first provider 본체 설치. 기본=공식 명령 *출력만*(실행 0). --execute는 명시적 opt-in:
    dry-run 미리보기 → interactive 확인 → 공식 명령 대행 실행 → 설치 후 probe 재검증.
    Core는 키/auth를 다루지 않고, 본체를 패키징/재배포하지 않는다(업스트림 공식 출처만)."""
    import importlib

    from .core.conductor import dispatch_probe
    from .providers import lifecycle

    if not args.execute:                                  # 기본: print-only(안전)
        res = lifecycle.run_install(args.name, execute=False)
        print(json.dumps(res, ensure_ascii=False, indent=2) if args.json else res["text"])
        return 0

    plan = lifecycle.install_plan(args.name)              # --execute: dry-run 미리보기 먼저
    print(f"\n[dry-run] {args.name} — 실행 예정(업스트림 공식 명령):")
    for d in plan.runtime_deps:
        if not d.available:
            print(f"  (runtime dep) {d.name}: {d.install_cmd}")
    print(f"  {plan.install_hint or '(설치 명령 없음)'}")

    def _confirm() -> bool:
        try:
            return input("위 공식 명령을 이 머신에서 실행할까요? [y/N] ").strip().lower() in ("y", "yes")
        except EOFError:
            return False

    def _prober(provider: str) -> dict:
        try:
            mod = importlib.import_module(f"app.nat.providers.{provider}.probe")
        except ModuleNotFoundError:
            return {"ok": False}
        q = CommandQueue(args.store)                      # in-process live probe(빌드타임 도구)
        dispatch_probe(q, provider=provider, argv=mod.probe_argv())
        w = WorkerNode("w-install-probe", capabilities=[f"provider.{provider}"], queue=q,
                       registry=WorkerRegistry(args.store), store_root=args.store)
        asyncio.run(w.poll_and_run_once())
        evs = [e for e in EventLog(args.store).tail(20)
               if e.event_type == "provider.probed" and (e.payload or {}).get("provider") == provider]
        if not evs:
            return {"ok": False}
        p = evs[-1].payload
        return mod.parse_probe(p.get("stdout", ""), p.get("stderr", ""), p.get("exit", -1))

    res = lifecycle.run_install(args.name, execute=True, confirm=_confirm, prober=_prober)
    if res.get("aborted"):
        print("취소됨 — 설치 실행 안 함.")
        return 0
    print(f"\n[install] executed exit={res.get('exit')}  advertised={res.get('advertised')}"
          + (f"  reprobe.ok={res['reprobe'].get('ok')}" if res.get("reprobe") else ""))
    return 0


def _cmd_artifacts(args) -> int:
    for a in ArtifactStore(args.store).list(task_id=args.task):
        print(f"{a.artifact_id}  {a.type:<16} [{a.status:<8}] task={a.task_id}  {a.summary[:60]}")
    return 0


def _cmd_events(args) -> int:
    for e in EventLog(args.store).tail(args.n):
        print(f"{e.created_at.isoformat()}  {e.event_type:<20} task={e.task_id} {e.message}")
    return 0


def _cmd_perm_list(args) -> int:
    for r in PermissionLedger(args.store).all():
        print(f"{r.permission_request_id}  {r.action:<18} [{r.state:<9}] policy={r.policy_decision} "
              f"target={r.target} task={r.task_id}")
    return 0


def _cmd_perm_approve(args) -> int:
    cmd = permission_nat.approve(args.permission_id, decider=args.by,
                                 ledger=PermissionLedger(args.store), queue=CommandQueue(args.store))
    print(f"approved → permission.execute {cmd.command_id}" if cmd
          else "거부됨: requested 상태가 아니거나 없음")
    return 0 if cmd else 1


def _cmd_perm_reject(args) -> int:
    r = permission_nat.reject(args.permission_id, ledger=PermissionLedger(args.store), reason=args.reason)
    print(f"rejected {args.permission_id}" if r else "not found")
    return 0 if r else 1


async def _cmd_worker(args) -> int:
    """agent-client 후신 — NAT WorkerNode를 등록하고 command를 pull/실행한다.
    --remote <url>이면 control_plane HTTP로 원격 접속(다른 PC), 아니면 로컬 file store."""
    caps = [c for c in args.capabilities.split(",") if c]
    if args.remote:
        import asyncio as _aio
        import httpx
        from .worker_http import WorkerHttpClient
        async with httpx.AsyncClient(base_url=args.remote, timeout=args.timeout + 30) as http:
            w = WorkerHttpClient(args.id, caps, http=http, bypass=args.bypass, timeout_sec=args.timeout,
                                 executors=default_executors())   # local_execute 시에만 호출됨(dry_run=미사용)
            await w.register()
            print(f"[worker] {args.id} registered @ {args.remote}  caps={caps}")
            if args.once:
                print(f"[worker] processed: {await w.poll_once()}")
            else:
                print("[worker] remote run_loop 시작 (Ctrl+C로 중지)…")
                while True:
                    await w.heartbeat()
                    if not await w.poll_once():
                        await _aio.sleep(2)
        return 0
    w = WorkerNode(args.id, capabilities=caps, queue=CommandQueue(args.store),
                   registry=WorkerRegistry(args.store), store_root=args.store, timeout_sec=args.timeout,
                   executors=default_executors())                 # local_execute 시에만 호출됨(dry_run=미사용)
    w.register()
    print(f"[worker] {args.id} registered  caps={w.capabilities}  store={args.store}")
    if args.once:
        results = await w.drain(bypass=args.bypass)
        print(f"[worker] drained {len(results)} command(s) → {[r.state for r in results]}")
    else:
        print("[worker] run_loop 시작 (Ctrl+C로 중지)…")
        await w.run_loop(bypass=args.bypass)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dipeen", description="Dipeen NAT CLI (M5 in-process)")
    p.add_argument("--store", default=_DEFAULT_STORE, help="NAT 저장 루트(기본 ./nat-workspace)")
    sub = p.add_subparsers(dest="group", required=True)

    t = sub.add_parser("task").add_subparsers(dest="action", required=True)
    r = t.add_parser("run", help="intent을 provider로 실행→번역→검증→영속")
    r.add_argument("intent")
    r.add_argument("--adapter", required=True, choices=["claude", "codex"])
    r.add_argument("--workspace", required=True, help="실행 워크스페이스(git repo)")
    r.add_argument("--acceptance", nargs="*", default=["code_patch"], help="완료기준(code_patch …)")
    r.add_argument("--bypass", action="store_true", help="실측 headless 권한우회(스크래치 전용)")
    r.add_argument("--timeout", type=int, default=180, help="provider 실행 타임아웃(초, 기본 180)")
    r.set_defaults(fn=lambda a: asyncio.run(_cmd_run(a)))
    i = t.add_parser("inspect", help="task 구조 뷰")
    i.add_argument("task_id")
    i.add_argument("--json", action="store_true")
    i.set_defaults(fn=_cmd_inspect)

    a = sub.add_parser("artifacts").add_subparsers(dest="action", required=True)
    al = a.add_parser("list")
    al.add_argument("--task", default=None)
    al.set_defaults(fn=_cmd_artifacts)

    e = sub.add_parser("events").add_subparsers(dest="action", required=True)
    et = e.add_parser("tail")
    et.add_argument("-n", type=int, default=30)
    et.set_defaults(fn=_cmd_events)

    pm = sub.add_parser("permission").add_subparsers(dest="action", required=True)
    pm.add_parser("list").set_defaults(fn=_cmd_perm_list)
    pa = pm.add_parser("approve")
    pa.add_argument("permission_id")
    pa.add_argument("--by", default="user://cli")
    pa.set_defaults(fn=_cmd_perm_approve)
    prj = pm.add_parser("reject")
    prj.add_argument("permission_id")
    prj.add_argument("--reason", default="")
    prj.set_defaults(fn=_cmd_perm_reject)

    pv = sub.add_parser("providers").add_subparsers(dest="action", required=True)
    pi = pv.add_parser("inspect", help="provider 설치/버전/capability 진단(read-only, static)")
    pi.add_argument("name", choices=["claude", "codex", "omo", "hermes", "all"])
    pi.add_argument("--json", action="store_true")
    pi.set_defaults(fn=_cmd_providers_inspect)
    pp = pv.add_parser("probe", help="provider 라이브 진단(worker가 doctor/status 실행, read-only)")
    pp.add_argument("name", choices=["omo", "hermes"])
    pp.add_argument("--json", action="store_true")
    pp.set_defaults(fn=_cmd_providers_probe)
    pin = pv.add_parser("install", help="provider 본체 설치 — 기본 print-only(실행 0), --execute는 명시적 opt-in")
    pin.add_argument("name", choices=["claude", "codex", "omo", "hermes"])
    pin.add_argument("--execute", action="store_true",
                     help="공식 설치 명령을 대행 실행(dry-run 미리보기 + interactive 확인 + 설치 후 probe)")
    pin.add_argument("--print", dest="print_only", action="store_true", help="설치 명령만 출력(기본값, 명시적 표기)")
    pin.add_argument("--json", action="store_true")
    pin.set_defaults(fn=_cmd_providers_install)
    prn = pv.add_parser("render", help="M11c dry-run: TaskEnvelope→provider invocation 렌더(실행 0, preview)")
    prn.add_argument("name", choices=["omo", "hermes", "claude", "codex"])
    prn.add_argument("intent")
    prn.add_argument("--workspace", required=True)
    prn.add_argument("--json", action="store_true")
    prn.set_defaults(fn=_cmd_providers_render)

    wk = sub.add_parser("worker", help="NAT Worker 실행(agent-client 후신) — command pull/실행")
    wk.add_argument("--id", default="w-local")
    wk.add_argument("--capabilities", default="provider.claude,provider.codex,workspace.write")
    wk.add_argument("--remote", default=None, help="control_plane base URL(예: http://localhost:8000) — 원격 접속")
    wk.add_argument("--once", action="store_true", help="큐 비울 때까지 한 사이클만")
    wk.add_argument("--bypass", action="store_true", help="실측 headless 권한우회(스크래치 전용)")
    wk.add_argument("--timeout", type=int, default=180)
    wk.set_defaults(fn=lambda a: asyncio.run(_cmd_worker(a)))

    dm = sub.add_parser("demo", help="API 키 없이 Product Alpha 가치를 한 명령으로 시연(진짜 증거)")
    dm.set_defaults(fn=lambda a: __import__("app.demo.product_alpha", fromlist=["main"]).main())
    add_workspace_parser(sub)
    return p


def main(argv: list[str] | None = None) -> int:
    # Windows 콘솔(cp949 등)에서 비ASCII 출력(한글·✓·em dash)이 UnicodeEncodeError로 죽지 않게 UTF-8로.
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    _providers.register_defaults()
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
