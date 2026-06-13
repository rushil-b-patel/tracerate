import math
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from tracerate.tester import SERVER, REQUEST_HEADERS


# Cap saturation streams. Mirrors tester.download's streams=6 ceiling so the
# probe itself does not become the bottleneck on slow links (see plan 003 §11).
_MAX_SATURATION_STREAMS = 6


def _percentile(samples: list[float], pct: float) -> float:
    """
    Nearest-rank percentile of `samples` at `pct` in [0, 100].

    Returns 0.0 for an empty list to match how callers treat "no samples".
    For a single-element list, returns that element. p0 returns the min,
    p100 returns the max.
    """
    if not samples:
        return 0.0
    ordered = sorted(samples)
    n = len(ordered)
    if pct <= 0:
        return ordered[0]
    if pct >= 100:
        return ordered[-1]
    # Nearest-rank: rank = ceil(pct/100 * n), then index = rank - 1.
    rank = math.ceil((pct / 100.0) * n)
    if rank < 1:
        rank = 1
    if rank > n:
        rank = n
    return ordered[rank - 1]


def _grade(delta: float) -> str:
    """
    Map loaded-vs-idle latency delta (ms) to a bufferbloat letter grade.
    Thresholds are preserved verbatim from the original implementation.
    """
    if   delta < 5:    return "A+"
    elif delta < 30:   return "A"
    elif delta < 60:   return "B"
    elif delta < 200:  return "C"
    elif delta < 400:  return "D"
    else:              return "F"


def _saturate_workers(stop_flag: threading.Event, url: str, streams: int):
    """
    Start `streams` background daemon threads that each open an httpx stream
    and discard bytes until `stop_flag` is set. Mirrors the multi-stream shape
    used by tracerate.tester.download: one shared httpx.Client, N daemon
    threads each running client.stream("GET", url) with iter_bytes, broad
    `except (httpx.HTTPError, OSError)` resilience so a failed saturation
    stream cannot crash the measurement.

    Returns (threads, client) so the caller can stop, join, and close cleanly.
    """
    client = httpx.Client(
        http2=False,
        timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0),
        headers=REQUEST_HEADERS,
        follow_redirects=True,
    )

    def worker() -> None:
        try:
            with client.stream("GET", url) as response:
                for _ in response.iter_bytes(chunk_size=1 << 20):
                    if stop_flag.is_set():
                        return
        except (httpx.HTTPError, OSError):
            return

    threads = [
        threading.Thread(target=worker, daemon=True)
        for _ in range(streams)
    ]
    for t in threads:
        t.start()
    return threads, client


def sample_ping(host: str, port: int) -> float | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        try:
            start = time.perf_counter()
            s.connect((host, port))
            end = time.perf_counter()
            return (end - start) * 1000
        finally:
            s.close()
    except (socket.timeout, socket.error):
        return None


def bufferbloat(duration: float = 5.0, attempts: int = 8, streams: int = 4) -> dict:
    """
    Saturate the link with `streams` parallel downloads in background threads,
    sample TCP-connect latency repeatedly during the saturation, compare to idle.

    Idle latency is `min(idle_samples)` (the right estimator for base RTT).
    Loaded latency is the p90 of samples taken during saturation: bufferbloat
    is about latency under load, so a min would systematically report the best
    case and hide the queueing delay the metric exists to expose.

    Returns: {"idle_ms", "loaded_ms", "delta_ms", "grade"}.
    """
    # Clamp streams to the cap so callers can't accidentally make the probe
    # itself the bottleneck.
    if streams < 1:
        streams = 1
    if streams > _MAX_SATURATION_STREAMS:
        streams = _MAX_SATURATION_STREAMS

    with ThreadPoolExecutor(max_workers=attempts) as ex:
        idle_samples = [
            ms for ms in ex.map(lambda _: sample_ping(SERVER["host"], SERVER["port"]), range(attempts))
            if ms is not None
        ]

    if not idle_samples:
        return {"idle_ms": 0.0, "loaded_ms": 0.0, "delta_ms": 0.0, "grade": "?"}

    idle = min(idle_samples)
    url = SERVER["download_url"].format(bytes=200_000_000)
    stop = threading.Event()

    threads, client = _saturate_workers(stop, url, streams)
    # Short warmup so streams ramp past TCP slow-start before we sample.
    time.sleep(0.3)

    # NOTE: TCP-connect sampling under load has a known limitation -- a SYN
    # retransmit can mask packet loss as latency. See plan 009 spike for a
    # kernel tcp_info / netlink based replacement.
    samples = []
    end_time = time.time() + duration

    while time.time() < end_time:
        ms = sample_ping(SERVER["host"], SERVER["port"])
        if ms is not None:
            samples.append(ms)
        time.sleep(0.2)

    stop.set()
    for t in threads:
        t.join(timeout=2)
    try:
        client.close()
    except Exception:
        pass

    if not samples:
        return {
            "idle_ms": round(idle, 2),
            "loaded_ms": 0.0,
            "delta_ms": 0.0,
            "grade": "?",
        }

    loaded = _percentile(samples, 90)
    delta = max(0.0, loaded - idle)
    grade = _grade(delta)

    return {
        "idle_ms": round(idle, 2),
        "loaded_ms": round(loaded, 2),
        "delta_ms": round(delta, 2),
        "grade": grade,
    }
