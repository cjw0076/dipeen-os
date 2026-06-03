import pytest


@pytest.mark.asyncio
async def test_room_message_and_proposal_http_keep_message_execution_boundary(client, tmp_path, monkeypatch):
    monkeypatch.setenv("NAT_WORKSPACE", str(tmp_path / "nat"))

    room = await client.post("/api/rooms", json={
        "room_id": "goal-alpha",
        "room_type": "goal",
        "ref_id": "G-1",
        "title": "Alpha Goal",
    })
    assert room.status_code == 200

    message = await client.post("/api/rooms/goal-alpha/messages", json={
        "sender_type": "human",
        "sender_id": "user://cjw",
        "body": "Build the product alpha flow.",
    })
    assert message.status_code == 200
    assert (await client.get("/api/commands")).json() == []

    proposal = await client.post("/api/proposals", json={
        "room_id": "goal-alpha",
        "intent": "Create the product alpha control tower.",
        "provider": "claude",
        "workspace_root": str(tmp_path / "workspace"),
        "proposed_by": "agent://team/pm",
        "acceptance": [{"type": "artifact_required", "artifact_type": "code_patch"}],
    })
    assert proposal.status_code == 200
    proposal_id = proposal.json()["proposal_id"]
    assert (await client.get("/api/commands")).json() == []

    confirmed = await client.post(f"/api/proposals/{proposal_id}/confirm", json={"decided_by": "user://cjw"})
    assert confirmed.status_code == 200
    command = confirmed.json()
    assert command["command_type"] == "run.start"
    assert command["state"] == "queued"

    queued = (await client.get("/api/commands?state=queued")).json()
    assert len(queued) == 1
    assert queued[0]["command_id"] == command["command_id"]


@pytest.mark.asyncio
async def test_worker_http_poll_and_result_ingests_run_artifacts_and_memory(client, tmp_path, monkeypatch):
    monkeypatch.setenv("NAT_WORKSPACE", str(tmp_path / "nat"))

    proposal = await client.post("/api/proposals", json={
        "room_id": "goal-alpha",
        "intent": "Implement worker result ingest.",
        "provider": "claude",
        "workspace_root": str(tmp_path / "workspace"),
        "proposed_by": "agent://team/pm",
        "acceptance": [{"type": "artifact_required", "artifact_type": "code_patch"}],
    })
    proposal_id = proposal.json()["proposal_id"]
    command = (await client.post(f"/api/proposals/{proposal_id}/confirm", json={"decided_by": "user://cjw"})).json()

    registered = await client.post("/api/workers", json={
        "worker_id": "w-alice-pc",
        "capabilities": ["provider.claude", "workspace.write"],
    })
    assert registered.status_code == 200
    wid = registered.json()["worker_id"]            # 서버 canonical id

    polled = await client.post(f"/api/workers/{wid}/commands/poll", json={})
    assert polled.status_code == 200
    leased = polled.json()["command"]
    assert leased["command_id"] == command["command_id"]
    assert leased["state"] == "leased"

    result = await client.post(f"/api/workers/{wid}/commands/{command['command_id']}/result", json={
        "status": "done",
        "summary": "Worker completed the product alpha path.",
        "changed_files": ["web/src/components/control-plane/ControlTower.tsx"],
        "tests_passed": True,
        "key_decisions": ["Keep Dipeen Core as source of truth for worker claims."],
        "runner": "claude-code",
    })
    assert result.status_code == 200
    assert result.json()["state"] == "DONE"

    artifacts = (await client.get(f"/api/artifacts?run_id={command['run_id']}")).json()
    assert {"code_patch", "file_change_set", "test_report", "review_result"} <= {item["type"] for item in artifacts}

    claims = (await client.get(f"/api/state-claims?run_id={command['run_id']}")).json()
    assert claims[0]["claimed_state"] == "done"

    memories = (await client.get("/api/memory-candidates?status=pending")).json()
    assert memories[0]["proposed_content"].startswith("Keep Dipeen Core")

    completed = (await client.get("/api/commands?state=completed")).json()
    assert completed[0]["command_id"] == command["command_id"]
