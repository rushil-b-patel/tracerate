import socket

import tracerate.info as info
from tracerate.info import measure_dns


def test_measure_dns_returns_none_on_gaierror(monkeypatch):
    def _boom(*args, **kwargs):
        raise socket.gaierror("nope")

    monkeypatch.setattr(info.socket, "getaddrinfo", _boom)
    assert measure_dns("does-not-resolve.invalid") is None


def test_measure_dns_returns_float_on_success(monkeypatch):
    def _ok(*args, **kwargs):
        # Shape mirrors a real getaddrinfo return; contents do not matter
        # because measure_dns only times the call.
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    monkeypatch.setattr(info.socket, "getaddrinfo", _ok)
    result = measure_dns("example.test")
    assert isinstance(result, float)
    assert result >= 0.0
