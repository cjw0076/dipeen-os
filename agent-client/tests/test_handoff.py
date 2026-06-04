"""Handoff Runner pure units — prompt rendering + git evidence capture (no network/config)."""
import subprocess

from dipeen_agent.handoff import render_prompt, capture_git_evidence


def test_render_prompt_has_objective_workspace_safety_and_submit_hint():
    cmd = {"command_id": "CMD-1", "provider": "claude",
           "required_capabilities": ["provider.claude", "workspace.write"],
           "workspace_ref": "workspace://app", "repo": "repo.app",
           "task": {"title": "Fix README", "intent": "Fix the README Quick Start",
                    "acceptance": [{"type": "artifact_required", "artifact_type": "code_patch"}]}}
    md = render_prompt(cmd, "claude")
    assert "Fix the README Quick Start" in md       # objective
    assert "workspace://app" in md                  # workspace
    assert "dry-run" in md.lower() and "push" in md.lower()   # safety policy
    assert "task submit CMD-1" in md                # how to return evidence


def test_render_prompt_tolerates_missing_fields():
    md = render_prompt({"command_id": "CMD-2"}, "codex")
    assert "CMD-2" in md and "codex" in md


def test_capture_git_evidence_reports_tracked_and_untracked(tmp_path):
    ws = tmp_path / "repo"
    ws.mkdir()
    for a in (["git", "init", "-q"], ["git", "config", "user.email", "t@t"], ["git", "config", "user.name", "t"]):
        subprocess.run(a, cwd=ws, check=True, capture_output=True)
    (ws / "a.txt").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=ws, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=ws, check=True, capture_output=True)
    (ws / "a.txt").write_text("hello world\n", encoding="utf-8")   # tracked edit
    (ws / "b.txt").write_text("new\n", encoding="utf-8")            # untracked new file
    changed, diff = capture_git_evidence(str(ws))
    assert "a.txt" in changed and "b.txt" in changed
    assert "hello world" in diff


def test_capture_git_evidence_is_safe_and_typed(tmp_path):
    # must never raise (non-git dir, odd encodings) and always returns (list, str)
    changed, diff = capture_git_evidence(str(tmp_path / "nope"))
    assert isinstance(changed, list) and isinstance(diff, str)
