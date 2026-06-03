"""OMO read-only probe (M11b) — worker가 실행할 doctor 명령 정의 + raw 출력 파싱.

실행은 worker(generic argv), 여기는 명령 정의/파싱만(provider 지식). omo는 bun 런타임 필요 —
미설치 시 `spawnSync bun ENOENT`로 실패하므로 정직하게 runtime_blocker로 표기(Evidence First).
"""
from __future__ import annotations

import json


def probe_argv() -> list[str]:
    return ["omo", "doctor", "--json"]


def parse_probe(stdout: str, stderr: str, exit_code: int) -> dict:
    blob = (stdout + "\n" + stderr).lower()
    if "spawnsync bun" in blob or "execute bun" in blob:
        return {"ok": False, "runtime_blocker": "bun",
                "reason": "omo는 bun 런타임 필요 — 미설치/미탐지(bootstrap으로 설치 가능)",
                "raw_stderr": stderr[:500]}
    if exit_code == 0 and stdout.strip():
        try:
            return {"ok": True, "doctor": json.loads(stdout)}
        except json.JSONDecodeError:
            return {"ok": True, "raw_stdout": stdout[:2000]}
    return {"ok": False, "exit": exit_code, "raw_stderr": stderr[:500], "raw_stdout": stdout[:500]}
