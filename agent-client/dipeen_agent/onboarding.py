"""dipeen-node 통합 온보딩 — doctor / runner install / setup.

study-guide §7.8/§10.5 Track C: 노드가 *한 명령*으로 합류한다. 손으로 하던 온보딩
(러너 확인 → 설치 → auth)을 하나로 묶는다. W0의 all_health()/provisioning() 위에 얹는다.

원칙:
- 설치(install_cmd)는 자동(npm/uv) — 멱등.
- **auth는 BYOK라 자동화하지 않는다** — 명령만 안내한다(키를 prompt/서버에 넣지 않는다).
"""
from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .runners import all_health, provisioning
from .support_levels import runner_support


@dataclass
class RuntimeDependency:
    """provider 러너가 의존하는 런타임(bun 등). OS 분기·멱등·dry_run 가능 — installer 셸이 아닌 여기서 관리."""
    id: str
    check: str                       # PATH에서 찾을 바이너리명
    install_cmd_win: str
    install_cmd_unix: str
    env_paths: list[str] = field(default_factory=list)   # 설치 후 PATH 보강(같은 세션 검증용)

    def installed(self) -> bool:
        if shutil.which(self.check):
            return True
        for p in self.env_paths:                          # 설치 직후 PATH 미반영 대비
            base = os.path.expanduser(p)
            if os.path.exists(os.path.join(base, self.check)) or \
               os.path.exists(os.path.join(base, self.check + ".exe")):
                return True
        return False

    def install_cmd(self) -> str:
        return self.install_cmd_win if platform.system() == "Windows" else self.install_cmd_unix


_RUNTIME_DEPS: dict[str, RuntimeDependency] = {
    "bun": RuntimeDependency(
        id="bun", check="bun",
        install_cmd_win='powershell -NoProfile -Command "irm bun.sh/install.ps1 | iex"',
        install_cmd_unix="curl -fsSL https://bun.sh/install | bash",
        env_paths=["~/.bun/bin"],
    ),
}


def get_runtime_dep(dep_id: str) -> RuntimeDependency | None:
    return _RUNTIME_DEPS.get(dep_id)


def missing_runtime_deps(dep_ids: list[str]) -> list[RuntimeDependency]:
    out: list[RuntimeDependency] = []
    for did in dep_ids:
        dep = _RUNTIME_DEPS.get(did)
        if dep and not dep.installed():
            out.append(dep)
    return out


def runner_runtime_deps(runner_names: list[str]) -> list[str]:
    """선택된 러너들의 runtime_deps 합집합(순서 보존, dedup)."""
    meta = provisioning()
    seen: set[str] = set()
    out: list[str] = []
    for name in runner_names:
        for did in meta.get(name, {}).get("runtime_deps", []):
            if did not in seen:
                seen.add(did)
                out.append(did)
    return out


def _core_checks() -> list[tuple[str, bool, str]]:
    """러너 외 핵심 도구(있으면 OK)."""
    items = [
        ("git", "필수 — 변경 추적/PR"),
        ("python", "필수 — 노드 런타임"),
        ("node", "npm 러너(omo/codex)용"),
        ("uv", "hermes 설치용(선택)"),
        ("bun", "omo(opencode) 런타임(선택)"),
        ("cloudflared", "Cloudflare Tunnel/NAT 우회용(원격 팀 권장)"),
    ]
    return [(name, _tool_path(name) is not None, hint) for name, hint in items]


def _tool_path(name: str) -> str | None:
    """PATH 기반 도구 탐색. cloudflared는 winget 기본 설치 위치도 본다."""
    found = shutil.which(name)
    if found:
        return found
    if name != "cloudflared":
        return None
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    if not local:
        return None
    link = local / "Microsoft" / "WinGet" / "Links" / "cloudflared.exe"
    if link.exists():
        return str(link)
    pkgs = local / "Microsoft" / "WinGet" / "Packages"
    if pkgs.exists():
        for p in pkgs.glob("Cloudflare.cloudflared_*/*cloudflared.exe"):
            if p.exists():
                return str(p)
    return None


def _cloudflared_install_cmd() -> str:
    system = platform.system()
    if system == "Windows":
        return "winget install --id Cloudflare.cloudflared -e"
    if system == "Darwin":
        return "brew install cloudflared"
    return "install cloudflared from Cloudflare package docs"


def _default_workspace() -> str:
    try:
        from .config import WORKSPACE
        return str(WORKSPACE)
    except Exception:  # noqa: BLE001
        return os.environ.get("DIPEEN_WORKSPACE", "")


def _core_tool_manifest(network: str) -> dict:
    checks = {name: ok for name, ok, _hint in _core_checks()}
    return {
        "git": {
            "required": True,
            "available": checks.get("git", False),
            "path": _tool_path("git"),
            "purpose": "workspace versioning, diff, branch, PR handoff",
            "install_hint": "install Git for your OS",
        },
        "python": {
            "required": True,
            "available": checks.get("python", False),
            "path": _tool_path("python"),
            "purpose": "dipeen-agent runtime",
            "install_hint": "install Python 3.11+",
        },
        "node": {
            "required": True,
            "available": checks.get("node", False),
            "path": _tool_path("node"),
            "purpose": "Claude/Codex/opencode npm CLIs",
            "install_hint": "install Node.js LTS",
        },
        "uv": {
            "required": False,
            "available": checks.get("uv", False),
            "path": _tool_path("uv"),
            "purpose": "Hermes runner install",
            "install_hint": "pipx install uv or use the official uv installer",
        },
        "bun": {
            "required": False,
            "available": _RUNTIME_DEPS["bun"].installed(),
            "path": _tool_path("bun"),
            "purpose": "omo(opencode) runtime",
            "install_cmd": _RUNTIME_DEPS["bun"].install_cmd(),
        },
        "cloudflared": {
            "required": network == "cloudflare",
            "available": checks.get("cloudflared", False),
            "path": _tool_path("cloudflared"),
            "purpose": "outbound-only HTTPS/WSS tunnel through NAT",
            "install_cmd": _cloudflared_install_cmd(),
        },
    }


def bootstrap_plan(
    *,
    role: str = "FE",
    workspace: str | None = None,
    network: str = "cloudflare",
    legacy_vps_url: str | None = None,
    include_runners: list[str] | None = None,
) -> dict:
    """Launcher가 따라야 할 원터치 온보딩 매니페스트.

    서버는 provider key를 받지 않는다. 자동화 범위는 도구 설치, 팀 JWT 연결,
    워크스페이스 준비, 러너 auth 명령 안내까지다.
    """
    role = role.strip() or "FE"
    network = (network or "cloudflare").lower()
    workspace = workspace or _default_workspace()
    runner_meta = provisioning()
    runner_order = include_runners or ["claude-code", "omo-codex-light", "omo-opencode", "hermes"]
    runners = {
        name: {
            "install_cmd": runner_meta.get(name, {}).get("install_cmd", ""),
            "auth_cmd": runner_meta.get(name, {}).get("auth_cmd", ""),
            "tier": "high-quality-worker" if name in {"claude-code", "omo-codex-light"} else "recursive-harness",
        }
        for name in runner_order
        if name in runner_meta
    }

    public_url = "<PUBLIC_HTTPS_URL>"
    join_code = "<CODE>"
    return {
        "name": "dipeen-launcher",
        "role": role,
        "workspace": workspace,
        "network": {
            "primary": network,
            "cloudflare": {
                "tool": "cloudflared",
                "mode": "quick tunnel for dev/demo; named tunnel for production workspace domains",
                "nat_model": "agent and HQ initiate outbound connections; no router port-forwarding",
                "hq_tunnel_command": "cd api && python -m app.services.public_tunnel",
                "agent_join_template": f"dipeen-agent connect --code {join_code} --api-url {public_url}",
                "wss_template": "wss://<PUBLIC_HOST>/ws/hermes/agent",
            },
            "legacy_vps": {
                "enabled": bool(legacy_vps_url),
                "url": legacy_vps_url or "",
                "use_when": "Cloudflare account/domain/tunnel is unavailable or existing VPS deployment is already trusted",
            },
        },
        "core_tools": _core_tool_manifest(network),
        "worker_layer": {
            "policy": "High-quality agents run locally through provider CLIs; Dipeen only orchestrates team state.",
            "runners": runners,
            "preferred": ["claude-code", "omo-codex-light"],
            "recursive": ["omo-opencode", "hermes"],
        },
        "byok": {
            "server_receives_provider_keys": False,
            "local_env_only": True,
            "auth_is_manual": True,
            "note": "Provider OAuth/API keys stay on the worker machine. The launcher only prints auth commands.",
        },
        "commands": {
            "install_launcher": [
                "python -m pip install -e agent-client",
            ],
            "hq": [
                "cd api && python -m app.services.public_tunnel",
                "open /onboarding and copy the team invite code",
            ],
            "agent": [
                f"dipeen-agent bootstrap --role {role} --workspace \"{workspace}\" --network {network}",
                f"dipeen-agent join {join_code} --api-url {public_url}",
            ],
        },
    }


def _print_bootstrap_plan(plan: dict, *, json_output: bool = False) -> None:
    if json_output:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return

    print("\n=== dipeen launcher bootstrap ===\n")
    print(f"Role      : {plan['role']}")
    print(f"Workspace : {plan['workspace']}")
    print(f"Network   : {plan['network']['primary']}")

    print("\n[Core modules/packages]")
    for name, meta in plan["core_tools"].items():
        mark = "OK" if meta.get("available") else "--"
        required = "required" if meta.get("required") else "optional"
        suffix = f" install: {meta.get('install_cmd')}" if meta.get("install_cmd") and not meta.get("available") else ""
        print(f"  [{mark}] {name:11} {required:8} {meta.get('purpose')}{suffix}")

    print("\n[Worker layer]")
    print(f"  {plan['worker_layer']['policy']}")
    for name, meta in plan["worker_layer"]["runners"].items():
        print(f"  - {name:16} install: {meta.get('install_cmd')}")
        print(f"    auth   : {meta.get('auth_cmd')}")

    print("\n[Network / NAT]")
    cf = plan["network"]["cloudflare"]
    print(f"  Cloudflare: {cf['nat_model']}")
    print(f"  HQ tunnel : {cf['hq_tunnel_command']}")
    if plan["network"]["legacy_vps"]["enabled"]:
        print(f"  Legacy VPS: {plan['network']['legacy_vps']['url']}")

    print("\n[BYOK]")
    print("  BYOK keys stay local. Dipeen HQ receives team JWT/status only, never provider keys.")

    print("\n[Next commands]")
    for cmd in plan["commands"]["agent"]:
        print(f"  {cmd}")


def _install_cloudflared_if_needed(plan: dict, *, dry_run: bool = False) -> int:
    meta = plan["core_tools"].get("cloudflared", {})
    if not meta.get("required") or meta.get("available"):
        return 0
    cmd = meta.get("install_cmd") or ""
    if not cmd or cmd.startswith("install cloudflared"):
        print("cloudflared 설치는 OS 패키지 문서 확인이 필요합니다.")
        return 1
    print(f"[install] cloudflared: {cmd}")
    if dry_run:
        return 0
    try:
        return subprocess.run(cmd, shell=True).returncode
    except Exception as e:  # noqa: BLE001
        print(f"cloudflared 설치 실패: {e}")
        return 1


def bootstrap(
    *,
    role: str = "FE",
    workspace: str | None = None,
    network: str = "cloudflare",
    legacy_vps_url: str | None = None,
    include_runners: list[str] | None = None,
    auto_install: bool = True,
    dry_run: bool = False,
    json_output: bool = False,
    env_path=None,
) -> int:
    """원터치 온보딩 준비: 매니페스트 출력 → 환경 병합 → 도구/러너 설치.

    dry_run이면 설치와 .env 쓰기를 하지 않고, 실제 명령만 보여준다.
    """
    plan = bootstrap_plan(
        role=role,
        workspace=workspace,
        network=network,
        legacy_vps_url=legacy_vps_url,
        include_runners=include_runners,
    )
    _print_bootstrap_plan(plan, json_output=json_output)
    if dry_run:
        return 0

    updates = {
        "DIPEEN_AGENT_ROLE": role,
        "DIPEEN_WORKSPACE": plan["workspace"],
        "DIPEEN_NETWORK_MODE": plan["network"]["primary"],
    }
    if legacy_vps_url:
        updates["DIPEEN_LEGACY_VPS_URL"] = legacy_vps_url
    _write_env(updates, env_path=env_path)

    if auto_install:
        if _install_cloudflared_if_needed(plan, dry_run=dry_run) != 0:
            print("Cloudflare tunnel 준비가 끝나지 않았습니다. legacy VPS 또는 수동 설치를 사용하세요.")
        return setup(auto_install=True, dry_run=dry_run)
    print("\n자동 설치 생략. 다음: `dipeen-agent setup` 후 `dipeen-agent connect ...`")
    return 0


def doctor(*, fix: bool = False, runner: str | None = None) -> int:
    """시스템 + 러너 상태 + omo-bun link를 한 화면에. fix=True면 BUN_BINARY 자동 설정.
    runner=<name>이면 그 러너만 harmless live probe로 심층 진단(installed≠runnable). exit 0 = OK."""
    if runner:
        return _doctor_runner(runner)
    print("\n=== dipeen-node doctor ===\n")
    print("[코어 도구]")
    core_ok = True
    for name, ok, hint in _core_checks():
        if name in ("git", "python") and not ok:
            core_ok = False
        print(f"  [{'OK' if ok else '--'}] {name:8} {hint}")

    healths = asyncio.run(all_health())
    meta = provisioning()
    any_runner = False
    print("\n[러너]  (실행하려면 install + auth 둘 다 필요)")
    for h in healths:
        print(f"  {h.line()}")
        support = runner_support(h.name)
        print(f"        support: {support.level} - {support.note}")
        m = meta.get(h.name, {})
        if not h.available and m.get("install_cmd"):
            print(f"        install: {m['install_cmd']}")
        if m.get("auth_cmd"):
            print(f"        auth   : {m['auth_cmd']}")
        any_runner = any_runner or h.available

    # omo-bun link (M11b 후속): omo가 bun을 못 찾는 spawnSync ENOENT 진단·자동수정(빈 머신 부트스트랩 자동화)
    from .bun_link import apply_bun_link, bun_link_command, find_bun_binary, needs_bun_link
    if needs_bun_link():
        bun_exe = find_bun_binary()
        print("\n[omo-bun link]  ⚠ omo가 bun을 못 찾을 수 있음(BUN_BINARY 미설정, PATH엔 셰임만)")
        if fix and bun_exe:
            apply_bun_link()
        elif bun_exe:
            print(f"        fix: {bun_link_command(bun_exe)}   (또는 `dipeen-agent doctor --fix`)")
        else:
            print("        bun 미설치 — `dipeen-agent setup`으로 설치 후 재시도")
    elif os.environ.get("BUN_BINARY"):
        print("\n[omo-bun link]  [OK] BUN_BINARY 설정됨")

    api = os.environ.get("API_URL", "http://localhost:8000")
    print(f"\nHQ: {api}")
    if not core_ok:
        print("⚠ 코어 도구(git/python) 누락 — 먼저 설치.")
    if not any_runner:
        print("⚠ 가용 러너 없음 → `dipeen-agent setup` 으로 설치.")
    else:
        print("→ auth 후 `dipeen-agent join <초대코드> --api-url <HQ주소>` 로 HQ 합류.")
    return 0 if (core_ok and any_runner) else 1


# ──────────────── doctor --runner: harmless live probe (Phase 4 / Epic B·C) ────────────────
# 'PATH에 있다(installed)' ≠ '실제 실행된다(runnable/probe healthy)'. omo는 bun ENOENT면 PATH에 omo가
# 있어도 죽는다 → installed=True, runnable=False, blocker="bun"(Evidence First, docs/SUPPORT_LEVELS.md).
# probe는 무해한 `--version`류만 호출한다(작업 실행 아님). 바이너리 출처: runners/*.health()의 which().
_PROBE_SPECS: dict[str, dict] = {
    "claude-code":     {"binaries": ["claude"],          "args": ["--version"], "runtime_deps": []},
    "omo-opencode":    {"binaries": ["omo", "opencode"], "args": ["--version"], "runtime_deps": ["bun"]},
    "omo-codex-light": {"binaries": ["codex"],           "args": ["--version"], "runtime_deps": []},
    "hermes":          {"binaries": ["hermes"],          "args": ["--version"], "runtime_deps": []},
}


def _default_probe_run(argv: list[str]) -> tuple[int, str, str]:
    """무해한 probe 실행(real). 누락=127, Windows .cmd/.ps1 셰임은 shell로 재시도. utf-8 강제(cp949 회피)."""
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=20,
                           encoding="utf-8", errors="replace")
        return (r.returncode, r.stdout or "", r.stderr or "")
    except FileNotFoundError:
        return (127, "", f"binary not found: {argv[0] if argv else '?'}")
    except OSError:                                   # Windows .cmd/.ps1 셰임은 직접 exec 불가 → shell 재시도
        try:
            r = subprocess.run(subprocess.list2cmdline(argv), shell=True, capture_output=True,
                              text=True, timeout=20, encoding="utf-8", errors="replace")
            return (r.returncode, r.stdout or "", r.stderr or "")
        except Exception as e:  # noqa: BLE001
            return (1, "", f"probe error: {e}")
    except Exception as e:  # noqa: BLE001
        return (1, "", f"probe error: {e}")


def _default_auth_check(name: str) -> bool | None:
    """provider auth(BYOK) 충족 여부 — Keystone C. `--version`은 exit 0이어도 auth를 증명하지
    않으므로(로그아웃 워커가 'runnable'로 광고되던 갭) claude/codex는 자격증명 존재를 확인한다:
    env 키 또는 CLI credentials 파일. auth로 게이트하지 않는 provider(omo/hermes)는 None을 반환해
    기존 probe-exit 의미(비0 exit=unhealthy)를 그대로 유지한다. 키/파일 *내용*은 읽지 않는다(존재만)."""
    home = Path.home()
    if name == "claude-code":
        return bool(os.environ.get("ANTHROPIC_API_KEY")) or (home / ".claude" / ".credentials.json").exists()
    if name == "omo-codex-light":
        return (bool(os.environ.get("OPENAI_API_KEY")) or bool(os.environ.get("CODEX_API_KEY"))
                or (home / ".codex" / "auth.json").exists())
    return None                                       # auth-gate 대상 아님(probe-exit이 이미 신호)


def probe_runner(name, *, run=None, which_fn=None, auth_fn=None) -> dict:
    """러너 하나를 무해 live probe로 진단 — 'installed(PATH)'와 'runnable(probe healthy)'를 분리한다.

    Evidence First: omo는 omo 바이너리가 PATH에 있어도 bun 런타임이 없으면 spawnSync bun ENOENT로
    죽는다 → installed=True, runnable=False, blocker="bun". probe는 --version류 무해 호출만 한다(작업 아님).
    Keystone C: `--version` exit 0은 auth를 증명하지 않으므로 claude/codex는 auth_fn으로 자격증명
    존재까지 확인한다(미충족이면 runnable=False, auth=False). auth_fn(name)→None이면 auth-gate 안 함.
    run/which_fn/auth_fn 주입으로 hermetic 테스트. 반환: installed/runnable/auth/blocker/version/support/install_cmd.
    """
    which_fn = which_fn or shutil.which
    run = run or _default_probe_run
    auth_fn = auth_fn or _default_auth_check
    spec = _PROBE_SPECS.get(name)
    meta = provisioning().get(name, {})
    support = runner_support(name)
    base = {"runner": name, "support": support.level, "support_note": support.note,
            "install_cmd": meta.get("install_cmd", "")}
    if spec is None:
        return {**base, "installed": False, "runnable": False, "auth": None, "blocker": None,
                "version": None, "reason": f"unknown runner: {name}"}

    binary = next((which_fn(b) for b in spec["binaries"] if which_fn(b)), None)
    if not binary:                                    # PATH에 없음 — 설치 안내가 다음 행동
        return {**base, "installed": False, "runnable": False, "auth": None, "blocker": None,
                "version": None, "reason": "binary not found in PATH"}

    exit_code, stdout, stderr = run([binary, *spec["args"]])
    blob = (stdout + "\n" + stderr).lower()
    blocker = "bun" if ("spawnsync bun" in blob or "execute bun" in blob) else None
    auth = auth_fn(name)                              # True | False | None(게이트 안 함)
    runnable = exit_code == 0 and blocker is None and auth is not False   # auth 미충족이면 광고 금지
    version = next((ln.strip() for ln in stdout.splitlines() if ln.strip()), None) if runnable else None
    reason = "no provider credentials (auth)" if auth is False else None
    return {**base, "installed": True, "runnable": runnable, "auth": auth, "blocker": blocker,
            "version": version, "binary": binary, "exit": exit_code,
            "raw": reason or (((stderr or stdout)[:300] or None) if not runnable else None)}


# provider.<name>(capability) → probe_runner의 runner 이름. fake는 내장이라 probe 대상이 아니다.
_PROVIDER_TO_RUNNER: dict[str, str] = {
    "claude": "claude-code",
    "codex": "omo-codex-light",
    "omo": "omo-opencode",
    "hermes": "hermes",
}


def build_register_probe(capabilities, *, probe_fn=None) -> dict:
    """worker가 register 시 보내는 probe dict — Keystone C(C2).

    advertised `provider.<name>` capability를 실제 runnable 여부로 매핑한다(설치+auth까지). 서버의
    compute_effective는 *probed-and-not-runnable*인 provider cap만 드롭하므로, 로그아웃/미설치 워커가
    광고만 하고 실행 못 하는 silent-failure를 register 단계에서 차단한다. 반환 shape는 compute_effective가
    먹는 `{provider_name: {"runnable": bool, ...}}`. fake(내장)·비 provider cap(role/repo/...)은 제외."""
    probe_fn = probe_fn or probe_runner
    out: dict[str, dict] = {}
    for cap in capabilities:
        if not cap.startswith("provider."):
            continue
        provider = cap.split(".", 1)[1]
        runner = _PROVIDER_TO_RUNNER.get(provider)
        if not runner:                                # fake(내장) 등 — probe 안 함(미포함=unprobed로 유지)
            continue
        res = probe_fn(runner)
        out[provider] = {"runnable": bool(res.get("runnable")),
                         "installed": bool(res.get("installed")),
                         "blocker": res.get("blocker"), "version": res.get("version")}
    return out


def _doctor_runner(name: str) -> int:
    """단일 러너 심층 진단 — harmless live probe로 'PATH에 있다'와 '실제로 돈다'를 분리해 보여준다."""
    from .runners import RUNNER_NAMES
    if name not in RUNNER_NAMES:
        print(f"알 수 없는 러너: {name}. 가능: {', '.join(RUNNER_NAMES)}")
        return 2
    res = probe_runner(name)
    print(f"\n=== dipeen-node doctor --runner {name} ===\n")
    print(f"  installed : {'OK' if res['installed'] else '--'}  ({res.get('binary') or 'not in PATH'})")
    line = f"  runnable  : {'OK' if res['runnable'] else '--'}"
    if res.get("version"):
        line += f"  v={res['version']}"
    print(line)
    print(f"  support   : {res['support']} - {res['support_note']}")
    if res.get("blocker") == "bun":
        print("  blocker   : bun 런타임 미탐지 — omo는 bun 필요(spawnSync bun ENOENT)")
        print("              fix: `dipeen-agent doctor --fix`(BUN_BINARY) 또는 `dipeen-agent setup`(bun 설치)")
    elif not res["installed"]:
        print(f"  install   : {res.get('install_cmd') or '(설치 명령 미정)'}")
    elif not res["runnable"]:
        print(f"  reason    : {res.get('raw') or 'probe 실패(비0 exit)'} — auth/설치 확인")
    runnable = bool(res["runnable"])
    print(f"\n→ {'준비됨(advertise 가능, 단 BYOK auth 필요)' if runnable else '아직 advertise 불가 — 위 조치 후 재probe'}")
    return 0 if runnable else 1


def install_runtime_dep(dep: RuntimeDependency, *, dry_run: bool = False) -> int:
    """런타임 의존성 설치(OS 분기). dry_run=명령만 출력. 설치 후 env_paths를 PATH에 보강(같은 세션 검증)."""
    cmd = dep.install_cmd()
    print(f"[runtime] {dep.id}: {cmd}")
    if dry_run:
        return 0
    try:
        rc = subprocess.run(cmd, shell=True).returncode
    except Exception as e:  # noqa: BLE001
        print(f"{dep.id} 설치 실패: {e}")
        return 1
    for p in dep.env_paths:                       # 같은 세션에서 즉시 검증/사용 가능하게
        base = os.path.expanduser(p)
        if base not in os.environ.get("PATH", ""):
            os.environ["PATH"] = base + os.pathsep + os.environ.get("PATH", "")
    return rc


def install_runner(name: str, *, dry_run: bool = False) -> int:
    """러너 하나 설치(install_cmd 실행). 주석(#…) 제거 후 shell 실행. dry_run=명령만 출력."""
    meta = provisioning()
    if name not in meta:
        print(f"알 수 없는 러너: {name}. 가능: {', '.join(meta)}")
        return 2
    cmd = (meta[name].get("install_cmd") or "").split("#")[0].strip()
    if not cmd:
        print(f"{name}: 설치 명령 없음(기본 동작).")
        return 0
    print(f"[install] {name}: {cmd}")
    if dry_run:
        return 0
    try:
        return subprocess.run(cmd, shell=True).returncode
    except Exception as e:  # noqa: BLE001
        print(f"설치 실패: {e}")
        return 1


def setup(*, auto_install: bool = True, dry_run: bool = False) -> int:
    """통합 온보딩 한 명령: 상태 → 빠진 러너 자동 설치 → auth 안내."""
    print("\n=== dipeen-node setup (통합 온보딩) ===")
    healths = asyncio.run(all_health())
    missing = [h.name for h in healths if not h.available]
    have = [h.name for h in healths if h.available]
    print(f"\n설치됨: {', '.join(have) or '없음'}")
    print(f"미설치: {', '.join(missing) or '없음'}")

    if missing and auto_install:
        # 결정(2026-06-03 print-first): 런타임 의존성(bun 등)은 자동(멱등) OK. 그러나 provider *본체*
        # (omo/hermes/claude/codex)는 자동 설치하지 않는다 — install_hint만 안내하고 사용자 opt-in.
        # 본체 자동설치는 ① dipeen 신뢰성을 third-party install에 묶고 ② "Core 실행0"·BYOK와 충돌.
        deps = missing_runtime_deps(runner_runtime_deps(missing))   # 런타임 dep만 자동(omo→bun)
        if deps:
            print(f"\n[runtime] 런타임 의존성 설치(자동, 멱등): {', '.join(d.id for d in deps)}")
            for dep in deps:
                install_runtime_dep(dep, dry_run=dry_run)
        print("\n[providers] 미설치 provider 본체 — 자동 설치 안 함(print-first). 필요한 것만 직접 설치:")
        meta = provisioning()
        for name in missing:
            cmd = (meta.get(name, {}).get("install_cmd") or "").split("#")[0].strip()
            print(f"  dipeen-agent runner install {name}" + (f"    # {cmd}" if cmd else ""))

    print("\n[2/2] auth — BYOK, 키는 로컬에만. 아래를 직접 실행:")
    meta = provisioning()
    for h in healths:
        if h.available:
            ac = meta.get(h.name, {}).get("auth_cmd")
            if ac:
                print(f"  {h.name:16} {ac}")
    print("\n다음: auth 후 `dipeen-agent join <초대코드> --api-url <HQ주소>` 로 HQ에 합류. (상세: dipeen-agent doctor)")
    return 0


def _parse_connect(code: str, api_url: str | None) -> tuple[str, str]:
    """초대코드/전체 join URL → (api_url, code). 전체 URL이면 거기서 host+code 추출."""
    import urllib.parse
    if code.startswith("http"):
        p = urllib.parse.urlparse(code)
        api_url = api_url or f"{p.scheme}://{p.netloc}"
        code = (urllib.parse.parse_qs(p.query).get("code") or [""])[0]
    api_url = (api_url or os.environ.get("DIPEEN_API_URL") or "http://127.0.0.1:8000").rstrip("/")
    return api_url, code


def _write_env(updates: dict, env_path=None) -> None:
    """agent-client/.env 키를 *병합* 갱신(기존 키·BYOK는 보존). env_path 주입 가능(테스트용)."""
    from pathlib import Path
    env_path = Path(env_path) if env_path else Path(__file__).parent.parent / ".env"
    out, seen = [], set()
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            key = line.split("=", 1)[0].strip() if ("=" in line and not line.lstrip().startswith("#")) else None
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
            else:
                out.append(line)
    for k, v in updates.items():
        if k not in seen:
            out.append(f"{k}={v}")
    env_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def connect(code: str, api_url: str | None = None, *, run_setup: bool = True) -> int:
    """초대코드로 팀 합류 → JWT를 .env에 기록 → (기본) setup까지 한 번에. = "한 방" 온보딩."""
    import json
    import urllib.request

    api_url, code = _parse_connect(code, api_url)
    if not code:
        print("초대코드 필요: dipeen-agent connect --code ABC123 [--api-url https://hq]")
        return 2
    import urllib.parse
    url = f"{api_url}/api/teams/join?code={urllib.parse.quote(code)}"
    print(f"\n=== dipeen-node connect ===\n[join] {url}")
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"⚠ 합류 실패: {e}\n  (HQ 주소/초대코드 확인. 예: --api-url https://demo.dipeen.app)")
        return 1
    token = data.get("token")
    team_id = data.get("team_id")
    if not token:
        print(f"⚠ 토큰 없음: {data}")
        return 1
    _write_env({"DIPEEN_API_URL": api_url, "DIPEEN_TOKEN": token, "DIPEEN_TEAM_ID": team_id or ""})
    print(f"✅ 팀 합류: team={team_id}. .env 갱신(API_URL/TOKEN, BYOK 키는 보존).")
    if run_setup:
        print("\n→ 이어서 러너 온보딩(setup)…")
        setup()
    print("\n준비 끝 → `dipeen-agent join <초대코드> --api-url <HQ주소>` 로 합류.")
    return 0
