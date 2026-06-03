"""M11a Provider Discovery — 진단 결과 타입 + static 감지 헬퍼.

원칙(plan §Core 오염 방지): 이 타입은 contracts.py(Core가 아는 유일 타입)에 *넣지 않는다*.
provider 진단은 운영/도구 레이어다. 감지는 static(which=PATH 조회 / 파일 존재 확인)이고,
버전만 격리된 probe_version()에서 read-only `--version` probe로 얻는다 — *빌드타임 진단 CLI* 한정.
런타임 task 실행 경로(conductor/pipeline/worker)와 무관: Core는 런타임 provider CLI를 직접
실행하지 않는다는 불변식을 유지한다.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class ProviderInspection:
    name: str
    installed: bool
    version: Optional[str] = None
    binary_path: Optional[str] = None
    config_paths: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    known_blockers: list[str] = field(default_factory=list)
    recommended_next_action: str = ""
    # Provider Lifecycle(2026-06-03): 본체 설치 명령 / 런타임 의존성 / 광고 여부를 분리 보고.
    install_hint: str = ""                            # provider *본체* 공식 설치 명령(런타임 dep 아님)
    runtime_deps: list = field(default_factory=list)  # list[lifecycle.RuntimeDep] — 본체와 분리
    capability_advertised: bool = False               # probe healthy일 때만 True(static inspect=항상 False)
    details: dict = field(default_factory=dict)       # provider-고유 구조(omo→team_mode/runtime, hermes→memory/skills/cron)

    def to_dict(self) -> dict:
        return asdict(self)


def which_any(names: list[str]) -> Optional[str]:
    """PATH에서 첫 번째로 발견되는 바이너리 경로(없으면 None). shutil.which=PATH 조회(실행 아님)."""
    for n in names:
        path = shutil.which(n)
        if path:
            return path
    return None


def probe_version(binary: str, args: tuple[str, ...] = ("--version",), timeout: float = 5.0) -> Optional[str]:
    """격리된 read-only 버전 probe. 실패/타임아웃/비제로 exit → None(installed 판정과 분리).

    이 모듈에서 subprocess를 호출하는 *유일한* 지점(감지 자체는 static). 버전은 best-effort —
    못 얻어도 installed=True는 유지된다.
    """
    try:
        # encoding 명시: Windows에서 text=True만 쓰면 locale(cp949)로 디코드 → UTF-8 출력 CLI가 깨진다.
        proc = subprocess.run([binary, *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0:
        return None
    out = (proc.stdout or proc.stderr or "").strip()
    return out.splitlines()[0].strip() if out else None


def find_existing(paths: list[str]) -> list[str]:
    """존재하는 파일 경로만 필터(static — 파일시스템 read-only)."""
    return [p for p in paths if p and os.path.isfile(p)]


def runnable_blockers(version: Optional[str]) -> list[str]:
    """installed인데 version probe가 실패(None)면 '실행 가능성 불확실'을 정직하게 표기(Evidence First).

    binary는 PATH에 있으나 `--version`이 실패 — 런타임 의존성 누락(예: omo의 bun ENOENT) 또는
    버전 명령 불일치. installed ✓만 보고 OK라 오해하지 않게 한다. 구체 사유는 M11b worker
    probe(`omo doctor` 등)에서; M11a는 generic 신호만 낸다.
    """
    if version is None:
        return ["binary는 PATH에 있으나 `--version` probe 실패 — 실행 가능성 불확실"
                "(런타임 의존성/버전 명령 확인; M11b worker probe 권장)"]
    return []
