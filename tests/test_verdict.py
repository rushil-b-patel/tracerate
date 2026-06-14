from tracerate.verdict import analyze

def test_healthy_connection():
    result = {
        "download_mbps": 100,
        "upload_mbps": 50,
        "ping_ms": 20,
        "jitter_ms": 5,
        "packet_loss": 0,
    }
    output = analyze(result, bufferbloat={"delta_ms": 2, "grade": "A+"})
    assert output["summary"] == "Connection looks healthy."
    assert output["issues"] == []
