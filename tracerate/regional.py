import socket
import time
from concurrent.futures import ThreadPoolExecutor


REGIONS = [
    ("IN", "Mumbai (South Asia)", "speedtest.mumbai1.linode.com"),
    ("SG", "Singapore (Southeast Asia)", "speedtest.singapore.linode.com"),
    ("JP", "Tokyo (East Asia)", "speedtest.tokyo2.linode.com"),
    ("GB", "London (Europe)", "speedtest.london.linode.com"),
    ("DE", "Frankfurt (Europe)", "speedtest.frankfurt.linode.com"),
    ("US", "Newark (US East)", "speedtest.newark.linode.com"),
    ("US", "Fremont/Seattle (US West)", "speedtest.fremont.linode.com"),
    ("AU", "Sydney (Australia)", "speedtest.sydney.linode.com"),
]

def tcp_ping(host: str, port: int = 443, attempts: int = 3, timeout: float = 2.0) -> float:
    """
    TCP connect latency in ms.
    """

    samples = []
    for _ in range(attempts):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            try:
                start = time.perf_counter()
                s.connect((host, port))
                end = time.perf_counter()
                samples.append((end-start) * 1000)
            finally:
                s.close()
        except (socket.timeout, socket.error):
            pass

    if not samples:
        return 0.0
    return round(min(samples), 2)

def ping_regions() -> list[dict]:
    results = []

    with ThreadPoolExecutor(max_workers=len(REGIONS)) as executor:
        futures = {executor.submit(tcp_ping, host): (code, city, host)
                   for code, city, host in REGIONS}
        for future, (code, city, host) in futures.items():
            try:
                ms = future.result()
            except Exception:
                ms = 0.0
            results.append({"code": code, "city": city, "host": host, "ms": ms})
    return results
