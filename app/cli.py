"""
cli.py — live terminal dashboard using Rich.

Run with: python -m app.cli

Functions:
- build_table()   -> constructs a Rich Table from current status + stats
- run_dashboard()  -> live-refreshing loop (Rich Live display)
"""

import time

from rich.console import Console
from rich.live import Live
from rich.table import Table

from app.db import get_connection
from app.stats import get_current_status, get_uptime_stats

console = Console()


def build_table() -> Table:
    """
    Build a Rich Table showing, for every monitor:
    name, current status (UP/DOWN), last latency, 24h uptime %, p95 latency.

    Color coding:
    - green "UP" if last check succeeded and no open incident
    - red "DOWN" if there's an open incident
    """
    conn = get_connection()
    statuses = get_current_status(conn)

    table = Table(title="API Health Monitor — live status")
    table.add_column("Monitor", style="bold")
    table.add_column("Status")
    table.add_column("Last latency", justify="right")
    table.add_column("24h uptime", justify="right")
    table.add_column("24h p95 latency", justify="right")
    table.add_column("Last checked", justify="right")

    for s in statuses:
        if s["is_down"]:
            status_text = "[red]DOWN[/red]"
        elif s["latest_check"] is None:
            status_text = "[yellow]PENDING[/yellow]"
        elif s["latest_check"]["success"]:
            status_text = "[green]UP[/green]"
        else:
            status_text = "[yellow]DEGRADED[/yellow]"

        latency = "-"
        checked_at = "-"
        if s["latest_check"]:
            latency = f"{s['latest_check']['response_ms']} ms"
            checked_at = s["latest_check"]["checked_at"]

        stats = get_uptime_stats(conn, s["id"], hours=24)
        uptime = f"{stats['uptime_pct']}%" if stats["uptime_pct"] is not None else "-"
        p95 = f"{stats['p95_latency_ms']} ms" if stats["p95_latency_ms"] is not None else "-"

        table.add_row(s["name"], status_text, latency, uptime, p95, checked_at)

    conn.close()
    return table


def run_dashboard(refresh_sec: int = 5) -> None:
    """
    Continuously refresh the table every `refresh_sec` seconds using
    Rich's Live display, which redraws in place rather than scrolling.
    """
    with Live(build_table(), console=console, refresh_per_second=1) as live:
        while True:
            time.sleep(refresh_sec)
            live.update(build_table())


if __name__ == "__main__":
    run_dashboard()
