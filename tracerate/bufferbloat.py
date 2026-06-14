import math
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from tracerate.tester import SERVER, REQUEST_HEADERS


# Cap on parallel saturation streams. Beyond this the probe itself starts
# competing for upstream bandwidth on slow links and skews the measurement;
# matches the streams=6 ceiling used by the main download test.
_MAX_SATURATION_STREAMS = 6


def _percentile(samples: list[float], pct: float) -> float:
    """Compute the nearest-rank percentile of a numeric sample list.

    Args:
        samples: Numeric values (any order); not mutated.
        pct: Percentile to extract, clamped to [0, 100]. p0 returns the
            min, p100 returns the max.

    Returns:
        The selected sample value, or 0.0 if `samples` is empty (so
        callers can treat "no samples" as a neutral zero).
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
    """Convert a loaded-vs-idle latency delta into a bufferbloat letter grade.

    Args:
        delta: Latency increase under load, in milliseconds.

    Returns:
        One of "A+", "A", "B", "C", "D", "F" (lower delta is better).
    """
    if   delta < 5:    return "A+"
    elif delta < 30:   return "A"
    elif delta < 60:   return "B"
    elif delta < 200:  return "C"
    elif delta < 400:  return "D"
    else:              return "F"


def _saturate_workers(stop_flag: threading.Event, url: str, streams: int):
    """Spawn parallel HTTP download streams to saturate the link.

    Each worker streams bytes from `url` and discards them until
    `stop_flag` is set; HTTP and OS errors are swallowed so a single
    failing stream cannot crash the measurement.

    Args:
        stop_flag: Event the caller sets to signal workers to exit.
        url: HTTP(S) URL to stream from.
        streams: Number of parallel daemon threads to start.

    Returns:
        A `(threads, client)` tuple. The caller is responsible for
        setting `stop_flag`, joining the threads, and closing the shared
        `httpx.Client`.
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
    """Measure bufferbloat by comparing idle and under-load TCP-connect latency.

    Samples ping latency to the configured server while a parallel
    multi-stream download saturates the link, then compares the under-load
    p90 against the idle min RTT to grade queueing delay.

    Args:
        duration: Seconds to sample under load (default 5.0).
        attempts: Number of idle samples taken before saturation
            (default 8).
        streams: Parallel saturation streams; clamped to [1, 6]
            (default 4).

    Returns:
        A dict with keys:
            idle_ms (float): Best idle round-trip latency, in
                milliseconds (`min(idle_samples)`).
            loaded_ms (float): p90 round-trip latency under load.
            delta_ms (float): `max(0.0, loaded_ms - idle_ms)`.
            grade (str): Letter grade A+..F, or "?" if sampling failed.
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

    # TCP-connect sampling under load has a known limitation: a lost SYN is
    # silently retransmitted by the kernel (after >=1s), so packet loss shows
    # up as inflated latency rather than a missed sample. Reading the kernel
    # tcp_info via getsockopt/netlink would be the accurate alternative.
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
