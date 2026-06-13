import inspect

from tracerate.verdict import analyze
from tracerate.cli import render_verdict


# --- analyze: status key is set alongside summary -----------------------------

def test_analyze_healthy_status_and_summary_unchanged():
    result = {
        "download_mbps": 100,
        "upload_mbps": 50,
        "ping_ms": 20,
        "jitter_ms": 5,
        "packet_loss": 0,
    }
    got = analyze(result, {"delta_ms": 10, "grade": "A"})
    assert got["status"] == "healthy"
    assert got["summary"] == "Connection looks healthy."


def test_analyze_low_bandwidth_status():
    got = analyze({"download_mbps": 5})
    assert got["status"] == "low_bandwidth"
    assert got["summary"] == "Low bandwidth, ISP speed is the bottleneck."


def test_analyze_problem_status_on_packet_loss():
    got = analyze({"packet_loss": 10, "download_mbps": 50})
    assert got["status"] == "problem"
    assert got["summary"] == "Packet loss detected, connection is unstable."


# --- render_verdict: no diagnosis prose literal in source ---------------------

def test_render_verdict_has_no_diagnosis_prose_literals():
    src = inspect.getsource(render_verdict)
    forbidden = [
        "looks healthy",
        "bottleneck",
        "Packet loss detected",
        "Severe bufferbloat",
        "High latency",
        "High jitter",
    ]
    for needle in forbidden:
        assert needle not in src, f"diagnosis prose leaked into render_verdict: {needle!r}"
