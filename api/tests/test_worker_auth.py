from app.nat.core.command_queue import CommandQueue
from app.nat.contracts import Command


def test_poll_assigns_lease_id(tmp_path):
    q = CommandQueue(tmp_path)
    q.enqueue(Command(provider="claude", required_capabilities=[]))
    leased = q.poll("wkr_a", [])
    assert leased is not None
    assert leased.lease_id is not None and len(leased.lease_id) >= 8
    assert leased.lease_owner == "wkr_a"
