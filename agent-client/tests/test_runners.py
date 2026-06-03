"""W0/W1 — RunnerAdapter base 헬퍼 + 솔기(finalize_artifacts) 단위 테스트.

핵심 불변식: finalize_artifacts는 completion_promise를 *조작하지 않는다*(없으면 None 유지).
"""
from dipeen_agent.runners.base import (
    build_run_report,
    finalize_artifacts,
    run_checks,
)


def test_build_run_report_fields():
    r = build_run_report(task_id="T1", agent_id="a", runner="claude-code", status="done",
                         completion_promise="DONE", changed_files=["web/x.tsx"])
    assert r["task_id"] == "T1" and r["runner"] == "claude-code"
    assert r["scope_diff"] == ["web/x.tsx"]      # 없으면 changed_files로
    assert r["completion_promise"] == "DONE"
    for k in ("v", "task_id", "agent_id", "runner", "status", "completion_promise",
              "changed_files", "scope_diff", "key_decisions", "blockers"):
        assert k in r


def test_run_checks_empty_without_config(tmp_path):
    assert run_checks(tmp_path, {}) == {}
    assert run_checks(tmp_path, None) == {}


def test_run_checks_runs_configured(tmp_path):
    res = run_checks(tmp_path, {"check_commands": {"ok": "exit 0", "bad": "exit 1"}})
    assert res == {"ok": "pass", "bad": "fail"}


def test_finalize_artifacts_enriches(tmp_path):
    arts = {"completion_promise": "DONE", "key_decisions": ["d"], "changed_files": ["a.py"]}
    out = finalize_artifacts(arts, tmp_path, runner="claude-code", agent_id="a",
                             task={"task_id": "T1", "trace_id": "tr"}, status="done")
    assert out["runner"] == "claude-code"
    assert out["scope_diff"] == ["a.py"]          # changed_files로 채움
    assert out["checks"] == {}                    # config 없음 → 검증 안 함
    assert out["run_report"]["task_id"] == "T1"
    assert out["run_report"]["trace_id"] == "tr"
    assert out["run_report"]["completion_promise"] == "DONE"   # 조작 없이 그대로
    assert out["completion_promise"] == "DONE"


def test_finalize_does_not_fabricate_promise(tmp_path):
    # promise 없으면 None 유지(조작 금지) — oracle 정합
    out = finalize_artifacts({"changed_files": []}, tmp_path, runner="claude-code",
                             agent_id="a", task={"task_id": "T2"}, status="done")
    assert out["run_report"]["completion_promise"] is None
