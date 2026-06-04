"""통합 온보딩(doctor/setup/install) — Track C 단일 명령 검증."""
from dipeen_agent import onboarding
from dipeen_agent.runners import RUNNER_NAMES, RunnerHealth, provisioning


def test_setup_does_not_auto_install_provider_bodies(monkeypatch, capsys):
    """결정(2026-06-03 print-first): join/setup은 provider 본체(omo/hermes/claude/codex)를 자동 설치하지 않는다.
    런타임 dep(bun)은 자동 OK지만 본체는 install_hint 안내만 → 사용자 opt-in(`runner install <name>`)."""
    installed_bodies: list[str] = []
    monkeypatch.setattr(onboarding, "install_runner",
                        lambda name, **k: installed_bodies.append(name) or 0)
    monkeypatch.setattr(onboarding, "install_runtime_dep", lambda dep, **k: 0)   # 런타임 dep는 허용(no-op)

    async def _all_missing():
        return [RunnerHealth(n, False, "missing") for n in RUNNER_NAMES]
    monkeypatch.setattr(onboarding, "all_health", _all_missing)

    rc = onboarding.setup(auto_install=True, dry_run=True)
    out = capsys.readouterr().out
    assert rc == 0
    assert installed_bodies == []                       # provider 본체 자동 설치 0 (print-first)
    assert "runner install" in out                      # 대신 opt-in 설치 명령을 안내


def test_provisioning_has_install_auth():
    p = provisioning()
    assert set(p) == set(RUNNER_NAMES)
    for name, m in p.items():
        assert m["auth_cmd"]                       # 모든 러너에 auth 안내
    assert p["hermes"]["install_cmd"].startswith("uv tool install")
    assert "codex" in p["omo-codex-light"]["install_cmd"]
    assert "oh-my-openagent" in p["omo-opencode"]["install_cmd"]


def test_doctor_returns_int():
    assert onboarding.doctor() in (0, 1)


def test_install_runner_dry_run():
    assert onboarding.install_runner("hermes", dry_run=True) == 0     # 명령만 출력
    assert onboarding.install_runner("bogus", dry_run=True) == 2      # 모르는 러너


def test_setup_dry_run_no_actual_install():
    assert onboarding.setup(auto_install=False, dry_run=True) == 0


def test_parse_connect_full_url():
    api, code = onboarding._parse_connect("https://demo.dipeen.app/onboarding?code=ABC123", None)
    assert api == "https://demo.dipeen.app"
    assert code == "ABC123"


def test_parse_connect_code_and_apiurl():
    api, code = onboarding._parse_connect("XYZ", "http://localhost:8000/")
    assert api == "http://localhost:8000"   # trailing slash 제거
    assert code == "XYZ"


def test_write_env_merges_preserving_byok(tmp_path):
    # 기존 .env(BYOK 키 포함)에 connect가 API_URL/TOKEN만 갱신, 나머지 보존
    env = tmp_path / ".env"
    env.write_text("# comment\nANTHROPIC_API_KEY=sk-ant-SECRET\nDIPEEN_API_URL=old\n", encoding="utf-8")
    onboarding._write_env({"DIPEEN_API_URL": "https://hq", "DIPEEN_TOKEN": "jwt123"}, env_path=env)
    txt = env.read_text(encoding="utf-8")
    assert "ANTHROPIC_API_KEY=sk-ant-SECRET" in txt   # BYOK 보존
    assert "DIPEEN_API_URL=https://hq" in txt          # 갱신
    assert "DIPEEN_TOKEN=jwt123" in txt                # 추가
    assert "DIPEEN_API_URL=old" not in txt             # 옛 값 제거
    assert "# comment" in txt                          # 주석 보존


def test_connect_no_code_returns_2():
    assert onboarding.connect("", run_setup=False) == 2


def test_bootstrap_plan_cloudflare_worker_layer_contract():
    plan = onboarding.bootstrap_plan(
        role="FE",
        workspace="D:/work/acme-web",
        legacy_vps_url="https://legacy.example.com",
    )

    assert plan["role"] == "FE"
    assert plan["workspace"] == "D:/work/acme-web"
    assert plan["network"]["primary"] == "cloudflare"
    assert plan["network"]["cloudflare"]["tool"] == "cloudflared"
    assert "python -m app.services.public_tunnel" in plan["network"]["cloudflare"]["hq_tunnel_command"]
    assert plan["network"]["legacy_vps"]["url"] == "https://legacy.example.com"

    workers = plan["worker_layer"]["runners"]
    assert "claude-code" in workers
    assert "omo-codex-light" in workers
    assert "omo-opencode" in workers
    assert "hermes" in workers

    assert plan["byok"]["server_receives_provider_keys"] is False
    # SSOT: 합류는 단일 `dipeen-agent join` 경로 (connect+start 분리 폐기)
    assert any("dipeen-agent join" in cmd for cmd in plan["commands"]["agent"])
    assert not any(cmd.strip() == "dipeen-agent start" for cmd in plan["commands"]["agent"])


def test_bootstrap_dry_run_prints_plan_without_env_write(tmp_path, capsys):
    env = tmp_path / ".env"
    rc = onboarding.bootstrap(
        role="QA",
        workspace=str(tmp_path / "workspace"),
        network="cloudflare",
        dry_run=True,
        env_path=env,
    )

    assert rc == 0
    assert not env.exists()
    out = capsys.readouterr().out
    assert "cloudflared" in out
    assert "dipeen-agent join" in out          # SSOT: 단일 합류 경로
    assert "BYOK" in out
