def _diagnose(download, ping, jitter, loss, bufferbloat_delta) -> str:
    if loss > 5:
        return "Packet loss detected, connection is unstable."
    if bufferbloat_delta > 200:
        return "Severe bufferbloat, router queue is overloaded."
    if ping > 100 and download >= 10:
        return "High latency, likely congestion or poor routing."
    if jitter > 30:
        return "High jitter, connection is unstable."
    if download < 10:
        return "Low bandwidth, ISP speed is the bottleneck."
    return "Connection looks healthy."

def _issues(download, upload, ping, jitter, loss, bb_grade) -> list[str]:
    issues = []
    if loss > 5:
        issues.append(f"Packet loss: {loss}%")
    if download < 25:
        issues.append(f"Low download: {download} Mbps")
    if upload is not None and upload < 10:
        issues.append(f"Low upload: {upload} Mbps")
    if ping > 80:
        issues.append(f"High ping: {ping} ms")
    if jitter > 20:
        issues.append(f"High jitter: {jitter} ms")
    if bb_grade in ("C", "D", "F"):
        issues.append(f"Bufferbloat grade: {bb_grade}")
    return issues

def analyze(result: dict, bufferbloat: dict | None = None) -> dict:
    download = result.get("download_mbps") or 0.0
    upload = result.get("upload_mbps")
    ping = result.get("ping_ms")           or 0.0
    jitter = result.get("jitter_ms")       or 0.0
    loss = result.get("packet_loss")       or 0.0

    delta = (bufferbloat or {}).get("delta_ms", 0.0)
    bb_grade = (bufferbloat or {}).get("grade", "?")

    return {
        "summary": _diagnose(download, ping, jitter, loss, delta),
        "issues": _issues(download, upload, ping, jitter, loss, bb_grade),
    }
