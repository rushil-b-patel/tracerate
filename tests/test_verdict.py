import pytest

from tracerate.verdict import _diagnose, _issues, analyze


# --- _diagnose: priority/branch coverage --------------------------------------

@pytest.mark.parametrize(
    "download, ping, jitter, loss, delta, expected",
    [
        # loss > 5 wins over everything else
        (100, 20, 5, 6, 10, "Packet loss detected, connection is unstable."),
        # bufferbloat delta > 200 (loss not tripping)
        (100, 20, 5, 0, 201, "Severe bufferbloat, router queue is overloaded."),
        # high latency: ping > 100 AND download >= 10
        (50, 101, 5, 0, 10, "High latency, likely congestion or poor routing."),
        # high jitter
        (50, 20, 31, 0, 10, "High jitter, connection is unstable."),
        # low bandwidth
        (5, 20, 5, 0, 10, "Low bandwidth, ISP speed is the bottleneck."),
        # healthy
        (100, 20, 5, 0, 10, "Connection looks healthy."),
    ],
)
def test_diagnose_branches(download, ping, jitter, loss, delta, expected):
    assert _diagnose(download, ping, jitter, loss, delta) == expected


# --- _diagnose: boundary conditions ------------------------------------------

def test_diagnose_loss_boundary_exactly_five_does_not_trip():
    # loss > 5 is strict; loss == 5 must NOT be packet-loss verdict
    assert _diagnose(100, 20, 5, 5, 10) == "Connection looks healthy."


def test_diagnose_high_latency_download_exactly_ten_trips():
    # download >= 10 with ping > 100 trips high latency
    assert _diagnose(10, 101, 5, 0, 10) == "High latency, likely congestion or poor routing."


def test_diagnose_ping_boundary_exactly_100_does_not_trip_latency():
    # ping > 100 is strict; ping == 100 must NOT trip latency
    assert _diagnose(100, 100, 5, 0, 10) == "Connection looks healthy."


# --- _issues: explicit numeric uploads only (never None) ---------------------

def test_issues_healthy_returns_empty():
    assert _issues(download=100, upload=50, ping=20, jitter=5, loss=0, bb_grade="A") == []


def test_issues_degraded_lists_all_expected_strings():
    got = _issues(download=5, upload=2, ping=120, jitter=40, loss=10, bb_grade="F")
    assert got == [
        "Packet loss: 10%",
        "Low download: 5 Mbps",
        "Low upload: 2 Mbps",
        "High ping: 120 ms",
        "High jitter: 40 ms",
        "Bufferbloat grade: F",
    ]


# --- analyze: end-to-end ------------------------------------------------------

def test_analyze_healthy_result():
    result = {
        "download_mbps": 100,
        "upload_mbps": 50,
        "ping_ms": 20,
        "jitter_ms": 5,
        "packet_loss": 0,
    }
    bufferbloat = {"delta_ms": 10, "grade": "A"}
    got = analyze(result, bufferbloat)
    assert got["summary"] == "Connection looks healthy."
    assert got["issues"] == []


def test_analyze_returns_exactly_summary_and_issues_keys():
    result = {
        "download_mbps": 100,
        "upload_mbps": 50,
        "ping_ms": 20,
        "jitter_ms": 5,
        "packet_loss": 0,
    }
    got = analyze(result, {"delta_ms": 10, "grade": "A"})
    assert set(got.keys()) == {"summary", "issues"}
