"""Meeting close → memory candidate 영속(리뷰 큐).

갭(첫 팀 테스트에서 적발): `control_plane.close_meeting`이 memory candidate를 *생성*만 하고 버려서
`list_memory_candidates()`가 0 → 회의 결정이 조직기억 리뷰 큐로 못 올라간다. close가 영속해야 한다.
(자동승격 아님 — 후보로 큐에 쌓고 사람이 promote: Org Memory 원칙 유지.)
"""
from app.nat.contracts import Message, Room, SenderRef


def test_close_meeting_persists_memory_candidate_to_review_queue(tmp_path, monkeypatch):
    monkeypatch.setenv("NAT_WORKSPACE", str(tmp_path / "nat"))
    from app.services import control_plane as cp
    cp.create_room(Room(room_id="r", room_type="goal", title="t"))
    cp.post_message(Message(room_id="r", sender=SenderRef(type="human", id="user://pm"),
                            body="이건 기억해두자: claude/codex는 primary, omo/hermes는 preview"))
    packet = cp.close_meeting("r")
    assert len(packet["memory_candidates"]) == 1            # 회의가 생성
    persisted = cp.list_memory_candidates()
    assert len(persisted) == 1                              # ★ 리뷰 큐에 영속(현재 갭=0)
    assert persisted[0]["status"] == "pending"             # 승격 대기(자동승격 금지)


def test_close_meeting_no_memory_marker_persists_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("NAT_WORKSPACE", str(tmp_path / "nat"))
    from app.services import control_plane as cp
    cp.create_room(Room(room_id="r2", room_type="goal", title="t"))
    cp.post_message(Message(room_id="r2", sender=SenderRef(type="human", id="user://pm"),
                            body="로그인 UI 구현해줘"))       # task — memory 아님
    cp.close_meeting("r2")
    assert cp.list_memory_candidates() == []               # memory marker 없으면 큐도 0
