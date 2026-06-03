import importlib

from starlette.testclient import TestClient


def _client(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import app.config as config
    importlib.reload(config)
    import app.main as main
    importlib.reload(main)
    return TestClient(main.app)


def _preflight(client, origin):
    return client.options(
        "/api/teams",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization",
        },
    )


def test_tunnel_origin_allowed_when_flag_on(monkeypatch):
    c = _client(
        monkeypatch,
        DIPEEN_DEBUG="true",
        DIPEEN_CORS_ORIGINS="http://localhost:3000",
        DIPEEN_ENABLE_PUBLIC_TUNNEL_CORS="true",
    )
    r = _preflight(c, "https://abc123.trycloudflare.com")
    assert r.headers.get("access-control-allow-origin") == "https://abc123.trycloudflare.com"
    assert r.headers.get("access-control-allow-credentials") == "true"


def test_unknown_origin_blocked(monkeypatch):
    c = _client(
        monkeypatch,
        DIPEEN_DEBUG="true",
        DIPEEN_CORS_ORIGINS="http://localhost:3000",
        DIPEEN_ENABLE_PUBLIC_TUNNEL_CORS="true",
    )
    r = _preflight(c, "https://attacker.com")
    assert r.headers.get("access-control-allow-origin") is None


def test_tunnel_origin_blocked_when_flag_off(monkeypatch):
    c = _client(
        monkeypatch,
        DIPEEN_DEBUG="true",
        DIPEEN_CORS_ORIGINS="http://localhost:3000",
        DIPEEN_ENABLE_PUBLIC_TUNNEL_CORS="false",
    )
    r = _preflight(c, "https://abc123.trycloudflare.com")
    assert r.headers.get("access-control-allow-origin") is None
