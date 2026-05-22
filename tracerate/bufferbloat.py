import threading
import httpx
import socket
import time
from concurrent.futures import ThreadPoolExecutor

from tracerate.tester import SERVER


def saturate_download(stop_flag: threading.Event, url: str) -> None:
    "Stream a large download until told to stop. Discard bytes."
    try:
        with httpx.stream("GET", url, timeout=60, follow_redirects=True) as response:
            for _ in response.iter_bytes():
                if stop_flag.is_set():
                    break
    except Exception:
        pass

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

def bufferbloat(duration: float = 5.0, attempts: int = 8) -> dict:
    """
    Saturate the link with a download in a background thread,
    sample ping repeatedly during the saturation, compare to idle.
    """

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
    worker = threading.Thread(target=saturate_download, args=(stop, url), daemon=True)
    worker.start()
    time.sleep(0.2)

    samples = []
    end_time = time.time() + duration

    while time.time() < end_time:
        ms = sample_ping(SERVER["host"], SERVER["port"])
        if ms is not None:
            samples.append(ms)
        time.sleep(0.2)

    stop.set()
    worker.join(timeout=2)

    if not samples:
        return {
            "idle_ms": round(idle, 2),
            "loaded_ms": 0.0,
            "delta_ms": 0.0,
            "grade": "?",
        }

    loaded = min(samples)
    delta = max(0.0, loaded - idle)

    if   delta < 5:    grade = "A+"
    elif delta < 30:   grade = "A"
    elif delta < 60:   grade = "B"
    elif delta < 200:  grade = "C"
    elif delta < 400:  grade = "D"
    else:              grade = "F"

    return {
        "idle_ms": round(idle, 2),
        "loaded_ms": round(loaded, 2),
        "delta_ms": round(delta, 2),
        "grade": grade,
    }
