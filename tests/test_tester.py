import socket
from unittest.mock import patch, MagicMock
from tracerate.tester import ping

@patch("tracerate.tester.socket.socket")
def test_ping_success(mock_socket):
    mock_sock = MagicMock()
    mock_socket.return_value = mock_sock

    avg_latency, loss, jitter = ping("fake.host", 443, 5)

    assert all([
        avg_latency >= 0,
        loss == 0,
        jitter >=0,
    ])

@patch("tracerate.tester.socket.socket")
def test_ping_timeout(mock_socket):
    mock_sock = MagicMock()
    mock_sock.connect.side_effect = socket.timeout("Connection timed out")
    mock_socket.return_value = mock_sock

    avg_latency, loss, jitter = ping("fake.host", 443, 5)
    assert all([
        avg_latency is None,
        loss == 100.0,
        jitter is None,
    ])
