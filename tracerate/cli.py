import typer
import json
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from rich.console import Console

from tracerate.info import get_ip_info, measure_dns
from tracerate.tester import (
    SERVER,
    UPLOAD_MAX_BYTES,
    ping,
    download,
    upload,
)
from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
)
from tracerate.verdict import analyze
from tracerate.regional import ping_regions
from tracerate.bufferbloat import bufferbloat as measure_bufferbloat

app = typer.Typer(help="tracerate - a no-nonsense CLI internet speed tester")
console = Console()


def run_upload(size_bytes: int, quiet: bool) -> float:
    """Run the upload test with a live progress bar."""
    if quiet:
        return upload(SERVER["upload_url"], size_bytes)

    start = time.perf_counter()
    with Progress(
        TextColumn("  [dim]Uploading  [/dim]"),
        BarColumn(bar_width=30, complete_style="cyan", finished_style="cyan"),
        TextColumn("[bold]{task.fields[mbps]:>7.2f}[/bold] [dim]Mbps[/dim]"),
        TextColumn("[dim]{task.fields[secs]:>4.1f}s[/dim]"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("ul", total=1000, mbps=0.0, secs=0.0)

        def on_progress(sent: int, total: int) -> None:
            elapsed = time.perf_counter() - start
            mbps = (sent * 8) / elapsed / 1_000_000 if elapsed > 0 else 0.0
            ratio = min(sent / total, 1.0) if total > 0 else 0.0
            progress.update(task, completed=int(ratio * 1000), mbps=mbps, secs=elapsed)

        return upload(SERVER["upload_url"], size_bytes, on_progress=on_progress)


def run_download(duration_s: float, streams: int, quiet: bool) -> float:
    """Run the main download with a live progress bar."""

    if quiet:
        return download(SERVER["download_url"], duration_s=duration_s, streams=streams)

    with Progress(
        TextColumn("  [dim]Downloading[/dim]"),
        BarColumn(bar_width=30, complete_style="cyan", finished_style="cyan"),
        TextColumn("[bold]{task.fields[mbps]:>7.2f}[/bold] [dim]Mbps[/dim]"),
        TextColumn("[dim]{task.fields[secs]:>4.1f}s[/dim]"),
        console=console,
        transient=True,
    ) as progress:
        ticks = 1000
        task = progress.add_task("dl", total=ticks, mbps=0.0, secs=0.0)

        def on_progress(total_bytes: int, elapsed: float) -> None:
            mbps = (total_bytes * 8) / elapsed / 1_000_000 if elapsed > 0 else 0.0
            ratio = min(elapsed / duration_s, 1.0)
            progress.update(task, completed=int(ratio * ticks), mbps=mbps, secs=elapsed)

        return download(SERVER["download_url"], duration_s=duration_s, streams=streams, on_progress=on_progress)


@app.command()
def run(
        quick: bool = typer.Option(default=False, help="Skip upload, bufferbloat, and regional probes. Use 10s download."),
        duration: float = typer.Option(default=15.0, help="Download test duration in seconds."),
        streams: int = typer.Option(default=6, help="Parallel download streams."),
        output: str = typer.Option(default="pretty", help="Output format: pretty or json.")
    ):
        if output not in ("pretty", "json"):
                typer.echo("--output must be 'pretty' or 'json'", err=True)
                raise typer.Exit(code=1)

        duration_s = 10.0 if quick else duration
        test_upload = not quick
        test_extras = not quick

        if output == "pretty":
            console.print()
            console.print("[bold]tracerate[/bold] [dim]· network diagnostics[/dim]")
            console.print()

        test_start = time.time()
        with console.status("[dim]Looking up your ISP and measuring latency...[/dim]", spinner="dots"):
            with ThreadPoolExecutor(max_workers=3) as ex:
                f_info = ex.submit(get_ip_info)
                f_dns  = ex.submit(measure_dns, SERVER["host"])
                f_ping = ex.submit(ping, SERVER["host"], SERVER["port"])
                info = f_info.result()
                dns_ms = f_dns.result()
                ping_ms, loss_pct, jitter_ms = f_ping.result()

        download_mbps = run_download(duration_s, streams, quiet=(output == "json"))

        upload_mbps = None
        if test_upload:
            upload_mbps = run_upload(UPLOAD_MAX_BYTES, quiet=(output == "json"))

        bufferbloat = None
        if test_extras:
            with console.status("[dim]Probing bufferbloat (saturating link)...[/dim]", spinner="dots"):
                bufferbloat = measure_bufferbloat()

        regions = []
        if test_extras:
            with console.status("[dim]Pinging regional servers...[/dim]", spinner="dots"):
                regions = ping_regions()

        test_duration = round(time.time() - test_start)
        result = {
            "name": SERVER["name"],
            "ping_ms": ping_ms,
            "packet_loss": loss_pct,
            "jitter_ms": jitter_ms,
            "download_mbps": download_mbps,
            "upload_mbps": upload_mbps,
            "error": None,
        }
        summary = analyze(result, bufferbloat=bufferbloat)

        if output == "json":
            print(json.dumps({
                "info": info,
                "dns_ms": dns_ms,
                "started_at": datetime.fromtimestamp(test_start).strftime("%Y-%m-%d %H:%M:%S"),
                "duration_s": test_duration,
                "result": result,
                "bufferbloat": bufferbloat,
                "regions": regions,
                "summary": summary,
            }, indent=2))
            return

        render(info, dns_ms, result, bufferbloat, regions, summary, test_start, test_duration)


_DIVIDER = "[dim]" + "─" * 56 + "[/dim]"

def bar(value: float, max_value: float, width: int = 20, filled: str = "▰", empty: str = "▱") -> str:
    if max_value <= 0:
        return empty * width
    ratio = min(value, max_value) / max_value
    n = int(round(ratio * width))
    return filled * n + empty * (width - n)

def section(title: str) -> None:
    console.print(f"  [bold cyan]{title}[/bold cyan]")
    console.print(f"  {_DIVIDER}")


def render(info, dns_ms, r, bb, regions, summary, test_start: float, test_duration: int):
    render_connection(info, dns_ms, test_start, test_duration)
    render_speed(r)

    if bb is not None:
        render_bufferbloat(bb)

    if regions:
        render_regions(regions)

    render_verdict(summary["status"], summary["summary"])


def render_connection(info: dict, dns_ms: float | None, test_start: float, test_duration: int) -> None:
    """Print the connection summary (ISP, location, edge PoP, IP, DNS, timestamp).

    Args:
        info: Dict from `info.get_ip_info` with optional keys `ip`, `isp`,
            `asn`, `city`, `country`, `colo`, `colo_city`.
        dns_ms: DNS lookup time in milliseconds, or None to render a red
            "DNS failed" indicator instead of a value.
        test_start: Test start time as a UNIX timestamp (for display).
        test_duration: Total wall-clock duration of the test, in seconds.
    """
    isp       = info.get("isp")       or "unknown"
    asn       = info.get("asn")       or ""
    city      = info.get("city")      or "?"
    country   = info.get("country")   or "?"
    colo      = info.get("colo")      or "?"
    colo_city = info.get("colo_city")
    ip        = info.get("ip")        or "?"

    if dns_ms is None:
        dns_segment = "[red]DNS failed[/red]"
    else:
        dns_color = "dim" if dns_ms < 50 else ("yellow" if dns_ms < 150 else "red")
        dns_segment = f"[dim]·  DNS[/dim] [{dns_color}]{dns_ms} ms[/{dns_color}]"
    edge = f"Cloudflare [bold]{colo}[/bold]" + (f" [dim]({colo_city})[/dim]" if colo_city else "")
    timestamp = datetime.fromtimestamp(test_start).strftime("%Y-%m-%d %H:%M:%S")

    console.print(f"  [dim]ISP    [/dim]  [bold]{isp}[/bold]   [dim]{asn}[/dim]")
    console.print(f"  [dim]Where  [/dim]  {city}, {country}  [dim]→[/dim]  {edge}")
    console.print(f"  [dim]IP     [/dim]  {ip}   {dns_segment}")
    console.print(f"  [dim]Tested [/dim]  [dim]{timestamp}   ·  {test_duration}s[/dim]")
    console.print()


def render_speed(r: dict) -> None:
    """Print the speed section (download, upload, ratio, ping, jitter, loss).

    Args:
        r: Result dict with keys `download_mbps`, `upload_mbps` (may be
            None when upload was skipped), `ping_ms`, `jitter_ms`,
            `packet_loss`. The "loss" indicator labels the connect-
            failure rate honestly as "conn. fail".
    """
    section("Speed")

    dl = r.get("download_mbps") or 0.0
    ul = r.get("upload_mbps") or 0.0
    ping = r.get("ping_ms") or 0.0
    jitter = r.get("jitter_ms") or 0.0
    loss = r.get("packet_loss") or 0.0

    scale = max(dl, ul, 100.0)

    def fmt_speed(mbps: float) -> str:
        if mbps >= 1000:
            return f"[bold]{mbps / 1000:>7.2f}[/bold] [dim]Gbps[/dim]"
        return f"[bold]{mbps:>7.2f}[/bold] [dim]Mbps[/dim]"

    console.print(f"   [dim]Download[/dim]  [cyan]{bar(dl, scale)}[/cyan]   {fmt_speed(dl)}")
    if r.get("upload_mbps") is not None:
        ratio = ul / dl if dl > 0 else 0.0
        ratio_str = f"   [dim]↑/↓ {ratio:.2f}x[/dim]"
        console.print(f"   [dim]Upload  [/dim]  [cyan]{bar(ul, scale)}[/cyan]   {fmt_speed(ul)}{ratio_str}")
    loss_part = f"[bold red]· {loss}% conn. fail[/bold red]" if loss > 0 else "[green]· 0% conn. fail[/green]"
    console.print(f"   [dim]Ping    [/dim]  [bold]{ping}[/bold] [dim]ms[/dim]   {loss_part}")
    console.print(f"   [dim]Jitter  [/dim]  [bold]{jitter}[/bold] [dim]ms[/dim]")
    console.print()


_GRADE_COLOR = {
    "A+": "green", "A": "green",
    "B": "cyan",
    "C": "yellow", "D": "yellow",
    "F": "red", "?": "dim",
}


def render_bufferbloat(bb: dict) -> None:
    section("Bufferbloat")
    grade = bb["grade"]
    color = _GRADE_COLOR.get(grade, "dim")
    console.print(f"   [dim]Idle  [/dim]  [bold]{bb['idle_ms']}[/bold] [dim]ms[/dim]")
    console.print(
        f"   [dim]Loaded[/dim]  [bold]{bb['loaded_ms']}[/bold] [dim]ms[/dim]"
        f"   [dim]Δ[/dim] [bold]+{bb['delta_ms']}[/bold] [dim]ms[/dim]"
        f"   [dim]Grade[/dim] [{color}][bold]{grade}[/bold][/{color}]"
    )
    console.print()


def render_regions(regions: list[dict]) -> None:
    section("Regional latency")
    reachable = [r for r in regions if r["ms"] > 0]
    scale = max((r["ms"] for r in reachable), default=200.0)

    ordered = sorted(regions, key=lambda r: r["ms"] if r["ms"] > 0 else 1e9)
    for r in ordered:
        ms = r["ms"]
        name = r["city"]
        city_part, _, region_part = name.partition(" (")
        region_part = region_part.rstrip(")")

        if ms == 0:
            bar_str = "[dim]" + "▱" * 12 + "[/dim]"
            ms_str = "[dim]timeout[/dim]"
        else:
            color = "cyan" if ms < 80 else ("yellow" if ms < 180 else "red")
            bar_str = f"[{color}]{bar(ms, scale, width=12)}[/{color}]"
            ms_str = f"[bold]{ms:>6.0f}[/bold] [dim]ms[/dim]"
        console.print(
            f"   [dim]{r['code']}[/dim]  {city_part:<16}  [dim]{region_part:<14}[/dim]  {bar_str}  {ms_str}"
        )
    console.print()


_STATUS_MARK_COLOR = {
    "healthy": ("✔", "green"),
    "low_bandwidth": ("⚠", "yellow"),
}


def render_verdict(status: str, message: str) -> None:
    """Print the final verdict line: a status mark plus the diagnosis message.

    Args:
        status: One of "healthy" (✔ green), "low_bandwidth" (⚠ yellow),
            or anything else (✘ red).
        message: Human-readable diagnosis from `verdict.analyze`.
    """
    mark, color = _STATUS_MARK_COLOR.get(status, ("✘", "red"))
    console.print(f"  [{color}]{mark}[/{color}]  [bold]{message}[/bold]")
    console.print()
