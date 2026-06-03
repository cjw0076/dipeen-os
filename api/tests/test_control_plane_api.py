import pytest


@pytest.mark.asyncio
async def test_control_plane_task_event_and_summary(client, tmp_path, monkeypatch):
    monkeypatch.setenv("NAT_WORKSPACE", str(tmp_path / "nat"))

    created = await client.post("/api/tasks", json={
        "subject": "Implement production overview",
        "prompt": "Build the Control Tower overview from canonical resources.",
        "required_role": "FE",
    })
    assert created.status_code == 201
    task = created.json()

    events = await client.get(f"/api/events?task_id={task['task_id']}")
    assert events.status_code == 200
    payload = events.json()
    assert len(payload) == 1
    assert payload[0]["event_type"] == "task.created"

    summary = await client.get("/api/control-plane/summary")
    assert summary.status_code == 200
    data = summary.json()
    assert data["goal_progress"]["total"] == 1
    assert data["goal_progress"]["ready"] == 1
    assert data["latest_events"][0]["event_type"] == "task.created"


@pytest.mark.asyncio
async def test_agent_report_creates_canonical_run_artifacts_and_claim(client, tmp_path, monkeypatch):
    monkeypatch.setenv("NAT_WORKSPACE", str(tmp_path / "nat"))

    agent = await client.post("/api/agents", json={
        "agent_id": "fe-agent",
        "role": "FE",
        "metadata": {"llm_provider": "anthropic", "model": "claude-sonnet-4-6"},
    })
    assert agent.status_code == 201

    created = await client.post("/api/tasks", json={
        "subject": "Wire canonical hooks",
        "prompt": "Expose run and artifact hooks.",
        "required_role": "FE",
    })
    task_id = created.json()["task_id"]

    reported = await client.post("/api/agents/fe-agent/report", json={
        "task_id": task_id,
        "status": "done",
        "tests_passed": True,
        "summary": "Canonical hooks wired.",
        "usage": {"input_tokens": 100, "output_tokens": 40, "model": "claude-sonnet-4-6"},
        "artifacts": {
            "changed_files": ["web/src/lib/api.ts", "web/src/hooks/useRuns.ts"],
            "scope_diff": ["web/src/lib/api.ts", "web/src/hooks/useRuns.ts"],
            "completion_promise": "DONE",
            "checks": {"pytest": "pass"},
            "runner": "claude-code",
            "key_decisions": ["Use Dipeen NAT resources as the UI source of truth."],
            "pr_url": "https://github.com/cjw0076/Dipeen_project/pull/128",
        },
        "pr_url": "https://github.com/cjw0076/Dipeen_project/pull/128",
    })
    assert reported.status_code == 200

    runs = await client.get(f"/api/runs?task_id={task_id}")
    assert runs.status_code == 200
    run_items = runs.json()
    assert len(run_items) == 1
    run_id = run_items[0]["run_id"]

    artifacts = await client.get(f"/api/artifacts?run_id={run_id}")
    assert artifacts.status_code == 200
    artifact_types = {item["type"] for item in artifacts.json()}
    assert {"code_patch", "file_change_set", "test_report", "review_result", "pr_reference"} <= artifact_types

    claims = await client.get(f"/api/state-claims?run_id={run_id}")
    assert claims.status_code == 200
    assert claims.json()[0]["claimed_state"] == "done"

    memories = await client.get("/api/memory-candidates?status=pending")
    assert memories.status_code == 200
    assert memories.json()[0]["proposed_content"].startswith("Use Dipeen NAT")
