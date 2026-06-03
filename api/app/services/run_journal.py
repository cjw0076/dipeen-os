"""Run Journal — append-only 이벤트 로그 (wrap 경계 4요소 #2).

원칙(`docs/dipeen-wrap-principle.md`): LOG_STREAM(휘발성 스트림)만으로는 감사·복구가 안 된다.
배정→보고→판정의 *결정적 사실*을 팀이 소유하는 곳에 남긴다(truth는 HQ).

v1: 방별 JSONL 파일(`dipeen-shared/journal/{room}.jsonl`). DB/Redis Streams는 후속(P5).
시각은 호출자가 주거나 UTC now. IO만 — 비치명(실패해도 루프를 막지 않음)으로 호출할 것.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _safe(room_id: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in room_id) or "room"


def _journal_dir() -> Path:
    base = os.getenv("DIPEEN_SHARED_DIR") or str(Path(__file__).resolve().parents[3] / "dipeen-shared")
    d = Path(base) / "journal"
    d.mkdir(parents=True, exist_ok=True)
    return d


def journal_event(room_id: str, event_type: str, payload: dict, *,
                  trace_id: str | None = None, ts: str | None = None) -> dict:
    """이벤트 한 줄을 append. event_type: dispatch | report | verdict 등."""
    rec = {
        "ts": ts or datetime.now(timezone.utc).isoformat(),
        "room_id": room_id,
        "type": event_type,
        "trace_id": trace_id,
        **payload,
    }
    path = _journal_dir() / f"{_safe(room_id)}.jsonl"
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def read_journal(room_id: str) -> list[dict]:
    """방의 저널을 시간순(append순)으로 읽는다. 감사·복구용."""
    path = _journal_dir() / f"{_safe(room_id)}.jsonl"
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def count_failures(room_id: str, failure_code: str | None = None) -> int:
    """방의 저널에서 실패 발생 횟수(재발 카운터).

    failure_code를 주면 그 코드만 센다. "같은 실패를 또 프롬프트로 때우려는 순간"을
    시스템이 감지하는 데 쓴다(RemediationPolicy의 fixture 승격 트리거).
    ⚠ **관측 전용** — 이 수를 분류기/에이전트의 *보상 신호*로 연결하지 말 것(Goodhart: 카운터
    회피를 위해 같은 실패에 다른 라벨을 흩뿌리게 됨). 측정과 최적화 대상을 분리한다.
    """
    n = 0
    for r in read_journal(room_id):
        is_failure = r.get("type") == "failure" or (
            r.get("type") == "verdict" and r.get("verdict") not in (None, "accept")
        )
        if not is_failure:
            continue
        if failure_code is None or r.get("failure_code") == failure_code:
            n += 1
    return n
