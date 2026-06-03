"""First-run demo의 핵심 beats를 잠근다 — 데모가 가짜 증거를 보이면 'Evidence First' 자기모순.

데모는 진짜 canonical 경로를 타야 하므로: 1차=거짓완료(NEEDS_RETRY), 2차=진짜 code_patch(DONE),
위험행동=dry_run receipt(진짜 side effect 0), 결정=memory candidate. 이 서사가 회귀하면 안 됨.
"""
import pytest

from app.demo.product_alpha import _new_repo, run_demo


@pytest.mark.asyncio
async def test_demo_tells_the_accountable_story_with_real_evidence(tmp_path):
    store = str(tmp_path / "nat")
    ws = _new_repo(tmp_path)

    out = await run_demo(store, ws)

    # Evidence First: agent의 거짓 완료는 차단되고, 증거가 있을 때만 DONE
    assert out["attempt1"] == "NEEDS_RETRY", "1차 거짓완료는 NEEDS_RETRY로 차단돼야 함"
    assert out["attempt2"] == "DONE", "2차 진짜 code_patch로 DONE"
    assert out["code_patch"] is True, "real git diff → code_patch artifact"

    # 진짜 파일이 워크스페이스에 생겼다(가짜 아님)
    assert (ws / "login.py").exists(), "데모는 진짜 파일을 만든다"

    # Permissioned Action: 승인해도 기본 dry_run — 진짜 PR 없음
    assert out["dry_run_receipt"] is True, "승인은 dry_run receipt(would_execute)로 — side effect 0"

    # Organization Memory: 결정이 후보로 남는다
    assert out["memory_candidate"], "결정은 memory candidate로 큐잉"
