"""T3 — `dipeen-agent start` deprecate: 경고 후 NAT worker로 위임.

레거시 `start`는 roster에만 등록하고 NAT 큐 작업을 안 잡아 "합류했는데 작업이 안 옴" 혼란의
원인이었다. 이제 deprecation 경고를 내고 worker로 위임해 실제로 큐 작업을 잡는다.
"""
import asyncio

from dipeen_agent import main


def test_start_warns_and_delegates_to_worker(monkeypatch, capsys):
    called = {}

    async def fake_worker(*args, **kwargs):
        called["delegated"] = True

    monkeypatch.setattr(main, "cmd_worker", fake_worker)
    asyncio.run(main.cmd_start())

    captured = capsys.readouterr()
    assert called.get("delegated") is True                  # worker로 위임됨
    assert "deprecated" in (captured.out + captured.err).lower()  # 경고가 보임
