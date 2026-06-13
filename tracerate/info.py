import httpx
import time
import socket
from concurrent.futures import ThreadPoolExecutor


def get_ip_info() -> dict:
    """
    ISP / IP / location lookup.

    Combines ipinfo.io (city precision, friendly ISP name) with
    Cloudflare's /meta endpoint (ASN, edge PoP code) so we can
    show "you hit Cloudflare BOM via Jio" in one line.
    """

    info = {
        "ip": None,
        "isp": None,
        "city": None,
        "country": None,
        "asn": None,
        "colo": None,
        "colo_city": None,
    }

    def _fetch_ipinfo():
        try:
            r = httpx.get("https://ipinfo.io/json", timeout=5)
            r.raise_for_status()
            return r.json()
        except Exception:
            return {}

    def _fetch_cf():
        try:
            r = httpx.get(
                "https://speed.cloudflare.com/meta",
                timeout=5,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "application/json",
                    "Referer": "https://speed.cloudflare.com/",
                },
            )
            r.raise_for_status()
            return r.json()
        except Exception:
            return {}

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_ipinfo = ex.submit(_fetch_ipinfo)
        f_cf = ex.submit(_fetch_cf)
        ipinfo_data = f_ipinfo.result()
        cf_data = f_cf.result()

    info["ip"] = ipinfo_data.get("ip")
    info["city"] = ipinfo_data.get("city")
    info["country"] = ipinfo_data.get("country")
    org = ipinfo_data.get("org") or ""
    if org.startswith("AS") and " " in org:
        asn, _, name = org.partition(" ")
        info["asn"] = asn
        info["isp"] = name
    elif org:
        info["isp"] = org

    colo = cf_data.get("colo")
    if isinstance(colo, dict):
        info["colo"] = colo.get("iata")
        info["colo_city"] = colo.get("city")
    elif isinstance(colo, str):
        info["colo"] = colo
    if not info["isp"]:
        info["isp"] = cf_data.get("asOrganization")
    if not info["asn"] and cf_data.get("asn"):
        info["asn"] = f"AS{cf_data['asn']}"
    if not info["city"]:
        info["city"] = cf_data.get("city")
    if not info["country"]:
        info["country"] = cf_data.get("country")
    if not info["ip"]:
        info["ip"] = cf_data.get("clientIp")

    return info


def measure_dns(hostname: str = "speed.cloudflare.com") -> float | None:
    """
    DNS lookup time in ms via getaddrinfo.

    Returns None on lookup failure so callers can distinguish failure from
    a genuine sub-millisecond result (instead of overloading 0.0 as both).
    """

    try:
        start = time.perf_counter()
        socket.getaddrinfo(hostname, None)
        end = time.perf_counter()
        elapsed = (end - start) * 1000
        return round(elapsed, 2)
    except socket.gaierror:
        return None
