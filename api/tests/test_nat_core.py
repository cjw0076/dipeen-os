"""NAT M1 core — EventLog(append→replay) / ArtifactStore(save→load+content) / RunStore(retry 누적). tmp 루트."""
import tempfile
from pathlib import Path

from app.nat.contracts import Event, Artifact, ArtifactProducer, Run, TaskEnvelope
from app.nat.core.eventlog import EventLog
from app.nat.core.artifact_store import ArtifactStore
from app.nat.core.run_store import RunStore


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="nat-"))


def test_eventlog_append_replay():
    root = _tmp()
    log = EventLog(root)
    log.append(Event(event_type="task.created", task_id="T-1"))
    log.append(Event(event_type="agent.working", task_id="T-1", message="editing"))
    log.append(Event(event_type="task.completed", task_id="T-2"))
    fresh = EventLog(root).read_all()                       # 새 인스턴스로 replay
    assert len(fresh) == 3 and fresh[0].event_type == "task.created"
    assert len(EventLog(root).by_task("T-1")) == 2
    assert EventLog(root).tail(1)[0].task_id == "T-2"


def test_artifact_save_load_content():
    root = _tmp()
    a = Artifact(type="code_patch", task_id="T-1",
                 producer=ArtifactProducer(identity="agent://team/frontend", adapter="claude"))
    ArtifactStore(root).save(a, content=b"diff --git a/x b/x\n", filename="diff.patch")
    loaded = ArtifactStore(root).load(a.artifact_id)
    assert loaded and loaded.type == "code_patch"
    assert any("diff.patch" in loc.uri for loc in loaded.locations)   # content location 자동추가
    assert len(ArtifactStore(root).list(task_id="T-1")) == 1
    assert ArtifactStore(root).list(task_id="T-9") == []


def test_runstore_retry_accumulates():
    root = _tmp()
    rs = RunStore(root)
    t = rs.save_task(TaskEnvelope(title="login", intent="x"))
    assert rs.next_attempt(t.task_id) == 1
    rs.save_run(Run(task_id=t.task_id, identity_id="agent://team/frontend", attempt=1, failure_type="test_failed"))
    assert rs.next_attempt(t.task_id) == 2
    rs.save_run(Run(task_id=t.task_id, identity_id="agent://team/frontend", attempt=2))
    runs = RunStore(root).runs_for(t.task_id)
    assert [r.attempt for r in runs] == [1, 2]             # retry=새 Run 누적(Task 불변)
    assert runs[0].failure_type == "test_failed"
    rs.update_task_state(t.task_id, "DONE")
    assert RunStore(root).load_task(t.task_id).state == "DONE"
