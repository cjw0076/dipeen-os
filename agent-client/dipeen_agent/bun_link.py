"""omo-bun link — omo가 bun을 못 찾는 spawnSync ENOENT 진단·수정(BUN_BINARY 자동 설정).

빈 머신 부트스트랩 자동화: bun 설치 후 omo(oh-my-opencode)가 내부 spawnSync("bun")로 bun.exe를
찾도록 BUN_BINARY를 잡아준다. npm 셰임(bun.cmd/.ps1)만 PATH에 있고 실제 bun.exe 경로를 못 찾으면
omo가 ENOENT로 죽는 문제(M11b probe가 적발)의 근본 수정.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path


def find_bun_binary() -> str | None:
    """bun 실행 파일(.exe/실바이너리) 실경로. npm 셰임(bun.cmd)이 아닌 진짜 바이너리를 찾는다."""
    env = os.environ.get("BUN_BINARY")
    if env and os.path.isfile(env):
        return env
    home = os.path.expanduser("~")
    for cand in (Path(home) / ".bun" / "bin" / "bun.exe", Path(home) / ".bun" / "bin" / "bun"):
        if cand.is_file():
            return str(cand)
    which = shutil.which("bun")
    if which:
        p = Path(which)
        npm_bun = p.parent / "node_modules" / "bun" / "bin" / "bun.exe"   # 셰임 옆 실체
        if npm_bun.is_file():
            return str(npm_bun)
        if p.suffix.lower() not in (".cmd", ".ps1") and p.is_file():
            return str(p)                                                 # 이미 실바이너리
    return None


def bun_link_command(bun_exe: str) -> str:
    """BUN_BINARY를 영구 설정하는 OS별 명령(시스템 변경 — doctor --fix opt-in에서만 실행)."""
    if platform.system() == "Windows":
        return f'setx BUN_BINARY "{bun_exe}"'
    return f'export BUN_BINARY="{bun_exe}"   # add to ~/.bashrc or ~/.zshrc'


def needs_bun_link() -> bool:
    """omo가 bun을 못 찾을 위험: BUN_BINARY 미설정 + PATH의 bun이 셰임(.cmd/.ps1)뿐.

    bun 자체가 없으면 False(그건 RuntimeDependency가 설치할 일) — 여기는 '설치됐는데 omo가 못 찾음'만.
    """
    if os.environ.get("BUN_BINARY"):
        return False
    which = shutil.which("bun")
    if not which:
        return False
    return Path(which).suffix.lower() in (".cmd", ".ps1")


def apply_bun_link(*, dry_run: bool = False) -> int:
    """bun.exe를 찾아 BUN_BINARY를 영구 설정(setx/export). **시스템 변경 — opt-in(doctor --fix)에서만**.

    빈 머신 부트스트랩 자동화의 마지막 고리: bun 설치 후 omo가 바로 동작하게. 못 찾으면 정직하게 실패(1).
    """
    bun_exe = find_bun_binary()
    if not bun_exe:
        print("bun 실파일 미발견 — `dipeen-agent setup`으로 bun 설치 후 재시도")
        return 1
    cmd = bun_link_command(bun_exe)
    print(f"[omo-bun link] {cmd}")
    if dry_run:
        return 0
    if platform.system() == "Windows":
        try:
            subprocess.run(["setx", "BUN_BINARY", bun_exe], capture_output=True, text=True)
        except Exception as e:  # noqa: BLE001
            print(f"BUN_BINARY 설정 실패: {e}")
            return 1
    else:
        print("위 export 줄을 ~/.bashrc 또는 ~/.zshrc에 추가하세요(영구 적용).")
    os.environ["BUN_BINARY"] = bun_exe          # 현재 세션도 즉시 반영(같은 세션 검증용)
    return 0
