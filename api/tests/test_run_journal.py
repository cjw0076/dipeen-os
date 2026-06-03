"""Run Journal — append-only 라운드트립 + 격리(DIPEEN_SHARED_DIR) 검증."""
from app.services import run_journal


def test_journal_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("DIPEEN_SHARED_DIR", str(tmp_path))
    run_journal.journal_event("general", "dispatch", {"task_id": "T1", "subject": "s"},
                              trace_id="tr-1", ts="2026-01-01T00:00:00+00:00")
    run_journal.journal_event("general", "verdict",
                              {"task_id": "T1", "verdict": "needs_human"},
                              trace_id="tr-1", ts="2026-01-01T00:00:01+00:00")
    recs = run_journal.read_journal("general")
    assert len(recs) == 2
    assert recs[0]["type"] == "dispatch" and recs[0]["task_id"] == "T1"
    assert recs[0]["trace_id"] == "tr-1"
    assert recs[1]["verdict"] == "needs_human"


def test_journal_isolated_per_room(tmp_path, monkeypatch):
    monkeypatch.setenv("DIPEEN_SHARED_DIR", str(tmp_path))
    run_journal.journal_event("room-a", "dispatch", {"task_id": "A"}, ts="2026-01-01T00:00:00+00:00")
    assert run_journal.read_journal("room-b") == []
    assert len(run_journal.read_journal("room-a")) == 1


def test_read_missing_room_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("DIPEEN_SHARED_DIR", str(tmp_path))
    assert run_journal.read_journal("never") == []


def test_count_failures_recurrence(tmp_path, monkeypatch):
    monkeypatch.setenv("DIPEEN_SHARED_DIR", str(tmp_path))
    # accept는 실패 아님, reject/needs_human은 실패로 카운트
    run_journal.journal_event("r", "verdict", {"verdict": "accept", "failure_code": "NONE"}, ts="2026-01-01T00:00:00+00:00")
    run_journal.journal_event("r", "verdict", {"verdict": "reject", "failure_code": "PROMISE_FALSE"}, ts="2026-01-01T00:00:01+00:00")
    run_journal.journal_event("r", "verdict", {"verdict": "reject", "failure_code": "PROMISE_FALSE"}, ts="2026-01-01T00:00:02+00:00")
    run_journal.journal_event("r", "verdict", {"verdict": "needs_human", "failure_code": "SCOPE_VIOLATION"}, ts="2026-01-01T00:00:03+00:00")
    assert run_journal.count_failures("r") == 3                       # accept 제외
    assert run_journal.count_failures("r", "PROMISE_FALSE") == 2      # 재발 2회 → fixture 승격 신호
    assert run_journal.count_failures("r", "SCOPE_VIOLATION") == 1
    assert run_journal.count_failures("r", "TIMEOUT") == 0
