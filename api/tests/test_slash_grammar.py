"""ux-command-layer-v0 — slash grammar v0 parser (pure). The one surface a teammate types."""
from app.nat.core.slash import parse_slash


def test_status_no_args():
    i = parse_slash("/dipeen status")
    assert i.verb == "status" and i.error is None and i.body == ""


def test_ask_captures_body():
    i = parse_slash('/dipeen ask fix the README Quick Start')
    assert i.verb == "ask" and i.body == "fix the README Quick Start" and i.error is None


def test_assign_cap_target_and_body():
    i = parse_slash("/dipeen assign cap:codex make a README patch")
    assert i.verb == "assign" and i.error is None
    assert i.target == {"kind": "cap", "value": "codex"}
    assert i.body == "make a README patch"


def test_assign_worker_target():
    i = parse_slash("/dipeen assign @minjun-mac review the change with Claude")
    assert i.target == {"kind": "worker", "value": "minjun-mac"}
    assert i.body == "review the change with Claude"


def test_assign_role_and_any_targets():
    assert parse_slash("/dipeen assign role:fe build login").target == {"kind": "role", "value": "fe"}
    assert parse_slash("/dipeen assign any do anything").target == {"kind": "any", "value": "any"}


def test_join_carries_code():
    assert parse_slash("/dipeen join DPN-8K7X-M2Q4").arg == "DPN-8K7X-M2Q4"


def test_approve_carries_id():
    assert parse_slash("/dipeen approve 12").arg == "12"


def test_prefix_variants_and_bare():
    assert parse_slash("dipeen status").verb == "status"
    assert parse_slash("/dp workers").verb == "workers"


def test_errors_are_user_language_not_http():
    assert parse_slash("/dipeen frobnicate x").error and "Unknown command" in parse_slash("/dipeen frobnicate x").error
    assert parse_slash("/dipeen assign").error and "target" in parse_slash("/dipeen assign").error
    assert parse_slash("/dipeen ask").error and "request" in parse_slash("/dipeen ask").error
    assert parse_slash("/dipeen approve").error and "id" in parse_slash("/dipeen approve").error
    assert parse_slash("/dipeen").error  # bare prefix → guidance
    # no error leaks an HTTP-ish code
    for txt in ("/dipeen frobnicate", "/dipeen assign", "/dipeen approve"):
        assert not any(c.isdigit() and len(c) == 3 for c in (parse_slash(txt).error or "").split())


def test_invite_verb_parses():
    i = parse_slash("/dipeen invite")
    assert i.verb == "invite" and i.error is None


def test_invite_with_optional_role_is_tolerated():
    i = parse_slash("/dipeen invite FE")
    assert i.verb == "invite" and i.error is None


def test_expose_and_close_verbs_parse():
    assert parse_slash("/dipeen expose this session").verb == "expose"
    assert parse_slash("/dipeen expose this session").error is None
    assert parse_slash("/dipeen close").verb == "close" and parse_slash("/dipeen close").error is None
