import socket

import tracerate.tester as tester
from tracerate.tester import ping


class _FakeSocketAllTimeout:
    """Fake socket whose connect() always raises socket.timeout."""

    def __init__(self, *args, **kwargs):
        pass

    def settimeout(self, _t):
        pass

    def connect(self, _addr):
        raise socket.timeout("fake timeout")

    def close(self):
        pass


class _FakeSocketAllOk:
    """Fake socket whose connect() returns immediately (instant success)."""

    def __init__(self, *args, **kwargs):
        pass

    def settimeout(self, _t):
        pass

    def connect(self, _addr):
        return None

    def close(self):
        pass


def _make_mixed_fake(fail_first_n: int, total: int):
    """Fake socket factory: the first `fail_first_n` connects time out,
    remaining (total - fail_first_n) succeed instantly. Stateful across
    instances via a closure counter."""
    state = {"calls": 0}

    class _FakeSocketMixed:
        def __init__(self, *args, **kwargs):
            state["calls"] += 1
            self._idx = state["calls"]

        def settimeout(self, _t):
            pass

        def connect(self, _addr):
            if self._idx <= fail_first_n:
                raise socket.timeout("fake timeout")
            return None

        def close(self):
            pass

    return _FakeSocketMixed


def test_ping_all_timeout_returns_full_loss_tuple(monkeypatch):
    monkeypatch.setattr(tester.socket, "socket", _FakeSocketAllTimeout)
    result = ping("host.invalid", 1, attempts=4)
    assert result == (None, 100.0, None)


def test_ping_all_success_returns_zero_loss_floats(monkeypatch):
    monkeypatch.setattr(tester.socket, "socket", _FakeSocketAllOk)
    latency, loss, jitter = ping("host.invalid", 1, attempts=4)
    assert loss == 0.0
    assert isinstance(latency, float)
    assert isinstance(jitter, float)
    assert latency >= 0.0
    assert jitter >= 0.0


def test_ping_mixed_two_of_four_fail_reports_fifty_percent(monkeypatch):
    monkeypatch.setattr(tester.socket, "socket", _make_mixed_fake(fail_first_n=2, total=4))
    latency, loss, jitter = ping("host.invalid", 1, attempts=4)
    assert loss == 50.0
    assert isinstance(latency, float)
    assert isinstance(jitter, float)
