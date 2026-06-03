"""W1 솔기: TaskArtifacts가 RunReport 필드를 드롭하지 않고 보존하는지.

이전엔 completion_promise/checks/scope_diff/runner가 schema에 없어 report 엔드포인트의
model_dump()에서 *드롭*됐고, 그 결과 Gatekeeper의 PROMISE_FALSE/DETERMINISTIC_FAIL이
실제 보고에서 죽어 있었다(통합 테스트는 dict를 직접 주입해 이 필터를 우회했음).
"""
from app.schemas.agent import AgentReport


def test_artifacts_preserve_runreport_fields():
    rep = AgentReport(
        task_id="T1", status="done", tests_passed=False, summary="s",
        artifacts={
            "changed_files": ["a.py"], "scope_diff": ["a.py"],
            "completion_promise": "DONE", "checks": {"pytest": "pass"},
            "runner": "claude-code", "run_report": {"task_id": "T1"},
        },
    )
    dumped = rep.artifacts.model_dump()
    assert dumped["completion_promise"] == "DONE"     # 이전엔 드롭됐음
    assert dumped["checks"] == {"pytest": "pass"}
    assert dumped["scope_diff"] == ["a.py"]
    assert dumped["runner"] == "claude-code"
    assert dumped["run_report"] == {"task_id": "T1"}


def test_artifacts_promise_none_preserved():
    rep = AgentReport(task_id="T2", status="done",
                      artifacts={"completion_promise": None, "changed_files": []})
    assert rep.artifacts.model_dump()["completion_promise"] is None
