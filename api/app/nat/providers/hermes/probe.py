"""Hermes read-only probe (M11b) — `hermes status` 명령 정의 + raw 줄 파싱.

hermes status/doctor는 plain-text(JSON 플래그 없음)라 줄 단위로 보존한다. 실행은 worker(generic argv).
무관: legacy `api/app/routers/hermes.py`(WebSocket A2A relay) — 외부 Nous Research hermes-agent CLI다.
"""
from __future__ import annotations


def probe_argv() -> list[str]:
    return ["hermes", "status"]


def parse_probe(stdout: str, stderr: str, exit_code: int) -> dict:
    if exit_code != 0 and not stdout.strip():
        return {"ok": False, "exit": exit_code, "raw_stderr": stderr[:500]}
    lines = [ln.rstrip() for ln in stdout.splitlines() if ln.strip()]
    version_hint = next((ln for ln in lines if "hermes agent v" in ln.lower()), None)
    return {"ok": True, "lines": lines, "version_hint": version_hint}
