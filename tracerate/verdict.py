_HEALTHY_SUMMARY = "Connection looks healthy."
_LOW_BANDWIDTH_SUMMARY = "Low bandwidth, ISP speed is the bottleneck."

_SUMMARY_TO_STATUS = {
    _HEALTHY_SUMMARY: "healthy",
    _LOW_BANDWIDTH_SUMMARY: "low_bandwidth",
}


def _diagnose(download, ping, jitter, loss, bufferbloat_delta) -> str:
    """Produce a short human-readable diagnosis of the connection.

    Returns the first matching condition in priority order: packet loss,
    severe bufferbloat, high latency, high jitter, low bandwidth; otherwise
    a healthy summary.

    Args:
        download: Download speed in Mbps.
        ping: Round-trip latency in ms.
        jitter: Latency jitter in ms.
        loss: Loss / TCP-connect-failure rate as a percentage.
        bufferbloat_delta: Loaded-vs-idle latency delta in ms.

    Returns:
        A single English sentence summarising the dominant issue.
    """
    if loss > 5:
        return "Packet loss detected, connection is unstable."
    if bufferbloat_delta > 200:
        return "Severe bufferbloat, router queue is overloaded."
    if ping > 100 and download >= 10:
        return "High latency, likely congestion or poor routing."
    if jitter > 30:
        return "High jitter, connection is unstable."
    if download < 10:
        return _LOW_BANDWIDTH_SUMMARY
    return _HEALTHY_SUMMARY

def _issues(download, upload, ping, jitter, loss, bb_grade) -> list[str]:
    """List threshold-based issue strings for a single test result.

    Args:
        download: Download speed in Mbps.
        upload: Upload speed in Mbps, or None if upload was not tested.
        ping: Round-trip latency in ms.
        jitter: Latency jitter in ms.
        loss: Loss / TCP-connect-failure rate as a percentage.
        bb_grade: Bufferbloat letter grade ("A+".."F" or "?").

    Returns:
        A list of human-readable issue strings; empty when nothing trips
        a threshold. `upload=None` is treated as "not measured" and
        contributes no issue.
    """
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
    """Build the diagnosis bundle shown after a speed test.

    Args:
        result: Speed-test dict with optional keys `download_mbps`,
            `upload_mbps`, `ping_ms`, `jitter_ms`, `packet_loss`.
        bufferbloat: Optional bufferbloat dict with keys `delta_ms`
            and `grade`.

    Returns:
        A dict with keys:
            summary (str): Single-sentence diagnosis.
            status (str): One of "healthy", "low_bandwidth", "problem"
                (drives the verdict line's mark/color in the renderer).
            issues (list[str]): Threshold-based issue strings.
    """
    download = result.get("download_mbps") or 0.0
    upload = result.get("upload_mbps")
    ping = result.get("ping_ms")           or 0.0
    jitter = result.get("jitter_ms")       or 0.0
    loss = result.get("packet_loss")       or 0.0

    delta = (bufferbloat or {}).get("delta_ms", 0.0)
    bb_grade = (bufferbloat or {}).get("grade", "?")

    summary = _diagnose(download, ping, jitter, loss, delta)
    status = _SUMMARY_TO_STATUS.get(summary, "problem")

    return {
        "summary": summary,
        "status": status,
        "issues": _issues(download, upload, ping, jitter, loss, bb_grade),
    }
