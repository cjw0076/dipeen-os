"""통합 글루 테스트 — on_task_update + _gatekeep_task가 실제로 함께 동작하는지.

순수함수(test_dispatch_gatekeep)와 별개로, pm_loop의 *배선*을 검증한다:
runner가 status=done으로 보고해도, 보고한 산출물이 비밀/키를 만졌으면 채팅에
'완료'가 아니라 '사람 승인 필요'가 나가고 배치 집계에서 성공으로 세지 않는다.
"""
import asyncio
import pm_loop


class _FakeResp:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code

    def json(self):
        return self._data


class _FakeClient:
    """on_task_update / _gatekeep_task / _send_batch_summary / _remediate_retry가 쓰는 GET·POST 흉내."""
    def __init__(self, artifacts, retry_task_id="T-retry"):
        self._artifacts = artifacts
        self._retry_task_id = retry_task_id
        self.posts: list = []

    async def get(self, url, **kwargs):
        return _FakeResp({"result": {"artifacts": self._artifacts}})

    async def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return _FakeResp({"task_id": self._retry_task_id}, status_code=201)


def _drive(monkeypatch, tmp_path, *, changed_files, status="done", subject="작업", artifacts_extra=None):
    """단일 태스크 배치를 세팅하고 on_task_update를 1회 돌린 뒤, (채팅 메시지, client)를 반환."""
    # Run Journal 쓰기를 임시 디렉터리로 격리(배선이 dispatch/verdict를 저널링함).
    monkeypatch.setenv("DIPEEN_SHARED_DIR", str(tmp_path))
    sent: list[str] = []

    async def fake_send_chat(room_id, content, client):
        sent.append(content)

    async def fake_set_phase(room_id, phase, client):
        return None

    monkeypatch.setattr(pm_loop, "_send_chat", fake_send_chat)
    monkeypatch.setattr(pm_loop, "_set_phase", fake_set_phase)
    monkeypatch.setattr(pm_loop, "_auth_headers", lambda: {})
    monkeypatch.setattr(pm_loop, "_append_artifacts", lambda *a, **k: None)

    from app.schemas.runner import TaskEnvelope
    from app.services.scope_policy import default_scope_claims

    task_id, batch_id, room_id = "T-int-1", "b-int-1", "general"
    pm_loop.TASK_BATCH[task_id] = {"room_id": room_id, "subject": subject, "batch_id": batch_id}
    pm_loop.BATCH_STATE[batch_id] = {
        "room_id": room_id, "title": "배치", "total": 1,
        "done": 0, "errors": 0, "results": [],
    }
    pm_loop.TASK_ENVELOPE[task_id] = TaskEnvelope(
        task_id=task_id, team_id="t", room_id=room_id, subject=subject, prompt="p",
        scope_claims=default_scope_claims(None),
    )

    arts = {"changed_files": changed_files, "key_decisions": []}
    if artifacts_extra:
        arts.update(artifacts_extra)
    client = _FakeClient(arts)
    asyncio.run(pm_loop.on_task_update({"task_id": task_id, "status": status}, client))
    return sent, client


def test_done_but_touched_dotenv_needs_human(monkeypatch, tmp_path):
    # runner: status=done + .env 변경 보고 → SCOPE_VIOLATION → 정책상 사람(fail-closed), 재시도 안 함.
    sent, client = _drive(monkeypatch, tmp_path, changed_files=["agent-client/.env"])
    joined = "\n".join(sent)
    assert "사람 승인 필요" in joined          # 🙋
    assert "agent-client/.env" in joined        # 위반 경로가 사람에게 surface
    assert client.posts == []                   # SCOPE_VIOLATION은 자동 재시도 금지


def test_clean_done_reports_complete(monkeypatch, tmp_path):
    # 비밀 안 건드린 정상 완료 → '완료'.
    sent, client = _drive(monkeypatch, tmp_path, changed_files=["web/src/app/page.tsx"])
    joined = "\n".join(sent)
    assert "완료" in joined
    assert "사람 승인 필요" not in joined
    assert client.posts == []


def test_promise_false_triggers_bounded_retry(monkeypatch, tmp_path):
    # runner가 status=done이라 보고하지만 completion_promise가 DONE이 아님 → PROMISE_FALSE
    # → 정책상 자동 재시도(attempt 2). 같은 batch 슬롯 유지(배치 미완), 새 봉투 등록.
    pm_loop.TASK_ENVELOPE.pop("T-retry", None)
    sent, client = _drive(monkeypatch, tmp_path, changed_files=["web/x.tsx"],
                          artifacts_extra={"completion_promise": "PARTIAL"})
    joined = "\n".join(sent)
    assert "자동 재시도 2" in joined                       # 🔄 bounded retry
    assert len(client.posts) == 1                          # 같은 태스크 재배정 1회
    assert "T-retry" in pm_loop.TASK_ENVELOPE              # 새 봉투 등록
    assert pm_loop.TASK_ENVELOPE["T-retry"].attempt == 2   # attempt 증가
    assert pm_loop.BATCH_STATE["b-int-1"]["done"] == 0     # 아직 성공 집계 안 함
    assert pm_loop.BATCH_STATE["b-int-1"]["errors"] == 0   # 실패로도 안 셈(슬롯 대기)
    # Remediation Packet은 전역이 아니라 이 태스크 prompt에만
    posted_prompt = client.posts[0][1]["json"]["prompt"]
    assert "REMEDIATION" in posted_prompt and "MUST_NOT" in posted_prompt
    pm_loop.TASK_ENVELOPE.pop("T-retry", None)
    pm_loop.BATCH_STATE.pop("b-int-1", None)
