import pytest

from app.services import public_tunnel as pt


class _FakeProc:
    def __init__(self, terminated_log, name):
        self._log = terminated_log
        self._name = name

    def terminate(self):
        self._log.append(self._name)


def test_dual_tunnel_returns_both_urls(monkeypatch):
    calls = []

    def fake_start(port, timeout=30.0):
        calls.append(port)
        url = f"https://r{port}.trycloudflare.com"
        return _FakeProc([], f"proc{port}"), url

    monkeypatch.setattr(pt, "start_quick_tunnel", fake_start)

    api_proc, api_url, web_proc, web_url = pt.start_dual_tunnel(api_port=8000, web_port=3000)
    assert api_url == "https://r8000.trycloudflare.com"
    assert web_url == "https://r3000.trycloudflare.com"
    assert calls == [8000, 3000]


def test_dual_tunnel_terminates_first_when_second_fails(monkeypatch):
    terminated = []

    def fake_start(port, timeout=30.0):
        if port == 8000:
            return _FakeProc(terminated, "api"), "https://api.trycloudflare.com"
        raise RuntimeError("web tunnel failed")

    monkeypatch.setattr(pt, "start_quick_tunnel", fake_start)

    with pytest.raises(RuntimeError, match="web tunnel failed"):
        pt.start_dual_tunnel(api_port=8000, web_port=3000)
    assert terminated == ["api"]  # 부분 노출 방지: 첫 터널 정리됨


def test_human_url_encodes_api_param():
    human = pt.build_human_url("https://web.trycloudflare.com", "https://api.trycloudflare.com")
    assert human == "https://web.trycloudflare.com/?api=https%3A%2F%2Fapi.trycloudflare.com"
