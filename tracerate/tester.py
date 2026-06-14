import socket
import time
from typing import Callable
import httpx
import os
import threading


SERVER = {
    "name": "Cloudflare",
    "download_url": "https://speed.cloudflare.com/__down?bytes={bytes}",
    "upload_url" : "https://speed.cloudflare.com/__up",
    "host": "speed.cloudflare.com",
    "port": 443,
}

REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "*/*",
    "Referer": "https://speed.cloudflare.com/",
}

def ping(host: str, port: int, attempts: int = 5):
    """Measure latency, reachability and jitter via repeated TCP handshakes.

    Performs `attempts` TCP connect() probes (each with a 3s socket timeout)
    and aggregates the timings. The "packet_loss" value here is the TCP
    connect-failure rate, not true packet loss: a lost SYN is silently
    retransmitted by the kernel and only counts as "lost" when no retry
    succeeds within the timeout.

    Args:
        host: Target hostname or IP.
        port: Target TCP port.
        attempts: Number of handshakes to perform (default 5).

    Returns:
        A `(average_latency, packet_loss, jitter)` tuple, or
        `(None, 100.0, None)` if every attempt failed:
            average_latency (float | None): Mean RTT in milliseconds.
            packet_loss (float): Connect-failure rate, as a percentage.
            jitter (float | None): max(latencies) - min(latencies), in ms.
    """

    results = []

    for _ in range(attempts):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(3)
            try:
                start = time.perf_counter()
                s.connect((host, port))
                end = time.perf_counter()

                latency = (end - start) * 1000
                results.append(latency)
            finally:
                s.close()
        except (socket.timeout, socket.error):
            results.append(None)

    valid_results = [r for r in results if r is not None]
    if not valid_results:
        return None, 100.0, None

    average_latency = sum(valid_results) / len(valid_results)
    packet_loss = ((attempts - len(valid_results)) / attempts) * 100
    jitter = max(valid_results) - min(valid_results)
    return round(average_latency, 2), round(packet_loss, 1), round(jitter, 2)

def download(
        url: str,
        duration_s: float = 10.0,
        streams: int = 6,
        warmup_s: float = 1.5,
        on_progress: Callable[[int, float], None] | None = None
    ) -> float:
    """
    Time bound parallel download speed test.

    Runs `streams` parallel HTTP downloads. Discards first `warmup_s`
    seconds (TCP slow-start). Measures bytes/sec over next `duration_s`
    seconds.

    Returns Mbps.
    """
    url = url.format(bytes=10**9)
    stop = threading.Event()
    counters = [0] * streams  # per-thread byte counts, no lock needed
    measure_start: float | None = None

    client = httpx.Client(
        http2=False,
        timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0),
        headers=REQUEST_HEADERS,
        follow_redirects=True,
    )

    def worker(idx: int) -> None:
        try:
            with client.stream("GET", url) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes(chunk_size=1 << 20):
                    if stop.is_set():
                        return
                    if measure_start is None:
                        continue
                    counters[idx] += len(chunk)
        except (httpx.HTTPError, OSError):
            return

    threads = [
        threading.Thread(target=worker, args=(i,), daemon=True)
        for i in range(streams)
    ]
    for t in threads:
        t.start()

    time.sleep(warmup_s)

    counters[:] = [0] * streams
    measure_start = time.perf_counter()

    end_at = measure_start + duration_s
    while time.perf_counter() < end_at:
        if on_progress:
            elapsed_now = time.perf_counter() - measure_start
            on_progress(sum(counters), elapsed_now)
        time.sleep(0.1)

    stop.set()
    elapsed = time.perf_counter() - measure_start
    bytes_transferred = sum(counters)

    for t in threads:
        t.join(timeout=2)
    client.close()

    if elapsed <= 0 or bytes_transferred == 0:
        return 0.0

    speed_mbps = (bytes_transferred * 8) / elapsed / 1_000_000
    return round(speed_mbps, 2)

UPLOAD_MAX_BYTES = 25 * 1024 * 1024
_UPLOAD_STREAMS = 4

def upload(url: str, size_bytes: int, on_progress: Callable[[int, int], None] | None = None) -> float:
    """
    Uploads random bytes of data in parallel stream to saturate asymmetric links.
    Generates a small random chunk and repeats it.

    Returns: speed in Mbps, or 0.0 if it fails.
    """
    size_bytes = min(size_bytes, UPLOAD_MAX_BYTES)
    per_stream = size_bytes // _UPLOAD_STREAMS

    chunk = os.urandom(min(per_stream, 1 << 20))
    repeats, extra = divmod(per_stream, len(chunk))
    payload = chunk * repeats + chunk[:extra]

    timeout = httpx.Timeout(connect=10.0, read=60.0, write=300.0, pool=10.0)
    sent_counters = [0] * _UPLOAD_STREAMS
    successful = [0]
    done = threading.Event()
    lock = threading.Lock()
    total = per_stream * _UPLOAD_STREAMS

    def make_body(idx: int):
        step = 64 * 1024
        for offset in range(0, len(payload), step):
            data = payload[offset:offset + step]
            sent_counters[idx] += len(data)
            yield data

    def upload_one(idx: int) -> None:
        try:
            r = httpx.post(url, content=make_body(idx), timeout=timeout, headers=REQUEST_HEADERS)
            r.raise_for_status()
            with lock:
                successful[0] += 1
        except (httpx.HTTPError, OSError):
            pass

    def monitor() -> None:
        while not done.is_set():
            on_progress(sum(sent_counters), total)
            time.sleep(0.1)

    start = time.perf_counter()
    threads = [threading.Thread(target=upload_one, args=(i,), daemon=True) for i in range(_UPLOAD_STREAMS)]
    for t in threads:
        t.start()

    if on_progress:
        m = threading.Thread(target=monitor, daemon=True)
        m.start()

    for t in threads:
        t.join()

    done.set()
    elapsed = time.perf_counter() - start

    if on_progress:
        m.join(timeout=1)
        on_progress(total, total)

    if elapsed <= 0 or successful[0] == 0:
        return 0.0
    total_bytes = per_stream * successful[0]
    return round((total_bytes * 8) / elapsed / 1_000_000, 2)
