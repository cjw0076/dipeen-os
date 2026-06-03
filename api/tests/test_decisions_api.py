import pytest


@pytest.mark.asyncio
async def test_create_list_and_answer_decision_card(client):
    create = await client.post("/api/decisions", json={
        "room_id": "orion-launch",
        "task_id": "T-123",
        "source_agent_id": "pm-agent",
        "decision_type": "approve",
        "question": "Approve checkout Wave 1 execution?",
        "options": ["Approve", "Ask for risk review"],
        "recommended_option": "Approve",
        "risk": "medium",
        "confidence": 0.78,
        "cost_estimate": "$0.42",
        "deadline": "2026-06-03T09:00:00Z",
        "context": "PM-Agent extracted a two-task wave from the meeting.",
    })
    assert create.status_code == 201
    card = create.json()
    assert card["status"] == "pending"
    assert card["room_id"] == "orion-launch"
    assert card["options"] == ["Approve", "Ask for risk review"]
    assert card["server_receives_provider_keys"] is False

    pending = await client.get("/api/decisions?status=pending&room_id=orion-launch")
    assert pending.status_code == 200
    items = pending.json()
    assert len(items) == 1
    assert items[0]["decision_id"] == card["decision_id"]

    answered = await client.post(
        f"/api/decisions/{card['decision_id']}/answer",
        json={"answer": "Approve", "note": "Proceed with Wave 1."},
    )
    assert answered.status_code == 200
    updated = answered.json()
    assert updated["status"] == "answered"
    assert updated["answer"] == "Approve"
    assert updated["answered_by"] == "human"

    pending_after = await client.get("/api/decisions?status=pending&room_id=orion-launch")
    assert pending_after.status_code == 200
    assert pending_after.json() == []


@pytest.mark.asyncio
async def test_decision_card_actions(client):
    create = await client.post("/api/decisions", json={
        "room_id": "general",
        "decision_type": "clarify",
        "question": "Which repository should the FE agent edit?",
    })
    card = create.json()

    snoozed = await client.post(f"/api/decisions/{card['decision_id']}/snooze")
    assert snoozed.status_code == 200
    assert snoozed.json()["status"] == "snoozed"

    delegated = await client.post(
        f"/api/decisions/{card['decision_id']}/delegate",
        json={"delegate_to": "pm-agent", "note": "Let PM decide."},
    )
    assert delegated.status_code == 200
    payload = delegated.json()
    assert payload["status"] == "delegated"
    assert payload["delegated_to"] == "pm-agent"
