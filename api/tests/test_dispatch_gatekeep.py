"""배정 정책(default_scope_claims) + 출구 게이트(gatekeep) 합성 테스트.

핵심 불변식: runner가 'done'이라 자기보고해도 비밀/키 파일을 만졌거나 범위를 넘으면
HQ는 accept 하지 않는다(needs_human). = "truth는 runner가 아니라 HQ가 가진다."
"""
from app.schemas.runner import TaskEnvelope, RunReport
from app.services.scope_policy import default_scope_claims, SECRET_DENY_PATHS
from app.services.gatekeeper import gatekeep


def _env(task_def=None) -> TaskEnvelope:
    return TaskEnvelope(task_id="T-1", team_id="t", subject="s", prompt="p",
                        scope_claims=default_scope_claims(task_def))


def _rep(files, status="done", promise="DONE") -> RunReport:
    return RunReport(task_id="T-1", agent_id="a", runner="claude-code", status=status,
                     completion_promise=promise, changed_files=files, scope_diff=files)


# ── BYOK 불변식: 비밀/키 파일 deny는 카드 없이도 항상 적용 ──

def test_default_denies_dotenv():
    v = gatekeep(_env(), _rep(["agent-client/.env"]))
    assert v.verdict == "needs_human" and v.scope_violations and v.human_card_prompt


def test_default_denies_top_level_dotenv():
    v = gatekeep(_env(), _rep([".env"]))
    assert v.verdict == "needs_human"


def test_default_denies_credentials():
    v = gatekeep(_env(), _rep(["home/u/.claude/.credentials.json"]))
    assert v.verdict == "needs_human"


def test_default_denies_pem_key():
    v = gatekeep(_env(), _rep(["deploy/tls/server.pem"]))
    assert v.verdict == "needs_human"


def test_clean_change_accepted():
    v = gatekeep(_env(), _rep(["web/src/app/page.tsx"]))
    assert v.verdict == "accept"


# ── 결정 카드(task_def)가 추가 경계를 줄 수 있다 ──

def test_extra_deny_merged_secrets_kept():
    sc = default_scope_claims({"deny_paths": ["infra/**"]})
    assert "infra/**" in sc.deny_paths
    assert all(p in sc.deny_paths for p in SECRET_DENY_PATHS)


def test_allow_paths_restrict_to_card_scope():
    # 카드가 web/**만 허용 → api/ 편집은 범위 밖 → 사람에게.
    v = gatekeep(_env({"allow_paths": ["web/**"]}), _rep(["api/secret_logic.py"]))
    assert v.verdict == "needs_human"


def test_high_risk_needs_human_even_clean():
    v = gatekeep(_env({"high_risk": True}), _rep(["web/x.tsx"]))
    assert v.verdict == "needs_human"


def test_max_files_from_card():
    v = gatekeep(_env({"max_files": 1}), _rep(["a.tsx", "b.tsx"]))
    assert v.verdict == "needs_human"


def test_runner_claims_done_but_no_promise_rejected():
    # runner가 done 상태인데 promise 미충족 → HQ reject (자기보고 불신)
    v = gatekeep(_env(), _rep(["web/x.tsx"], promise=None))
    assert v.verdict == "reject"
