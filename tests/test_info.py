import socket
from unittest.mock import patch
from tracerate.info import measure_dns, get_ip_info


@patch("tracerate.info.socket.getaddrinfo")
def test_measure_dns(mock_getaddrinfo):
    mock_getaddrinfo.return_value = [("family", "type", "proto", "canonname", ("addr", 0))]
    elapsed_time = measure_dns("example.com")
    print(f"DNS lookup time: {elapsed_time} ms")
    assert elapsed_time >= 0

@patch("tracerate.info.socket.getaddrinfo")
def test_measure_dns_failure(mock_getaddrinfo):
    mock_getaddrinfo.side_effect = socket.gaierror("DNS resolution failed")
    elapsed_time = measure_dns("example.com")
    assert elapsed_time == 0.0

def test_get_ip_info():
    