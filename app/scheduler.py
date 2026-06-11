"""
scheduler.py — wires up APScheduler to run check_cycle for each monitor
on its own interval.

Functions:
- load_monitors_from_config()  -> reads monitors.json, ensures DB rows exist
- start_scheduler()              -> creates and starts a BackgroundScheduler
"""

import json
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler

from app.db import get_connection, get_or_create_monitor, get_all_monitors
from app.checker import run_check_cycle

CONFIG_PATH = Path(__file__).parent.parent / "monitors.json"


def load_monitors_from_config() -> list:
    """
    Read monitors.json and ensure each monitor has a corresponding row
    in the database (idempotent — safe to call on every startup).

    Returns the list of monitor rows from the database.
    """
    with open(CONFIG_PATH) as f:
        config = json.load(f)

    conn = get_connection()
    for m in config["monitors"]:
        get_or_create_monitor(
            conn,
            name=m["name"],
            url=m["url"],
            interval_sec=m.get("interval_sec", 60),
            timeout_sec=m.get("timeout_sec", 5),
            fail_threshold=m.get("fail_threshold", 3),
        )

    monitors = get_all_monitors(conn)
    conn.close()
    return monitors


def _job_for_monitor(monitor_id: int) -> None:
    """
    The function APScheduler actually calls. Opens its own DB connection
    (SQLite connections aren't safe to share across threads) and runs
    one check cycle for this monitor.
    """
    conn = get_connection()
    monitor = conn.execute("SELECT * FROM monitors WHERE id = ?", (monitor_id,)).fetchone()
    if monitor:
        result = run_check_cycle(conn, monitor)
        status = "UP" if result["success"] else "DOWN"
        print(f"[{monitor['name']}] {status} - {result['response_ms']}ms - status={result['status_code']}")
    conn.close()


def start_scheduler() -> BackgroundScheduler:
    """
    Create a BackgroundScheduler, register one job per monitor (each on
    its own interval from monitors.json), and start it.

    BackgroundScheduler runs in a separate thread, so this returns
    immediately and the FastAPI app can keep running in the main thread.
    """
    monitors = load_monitors_from_config()
    scheduler = BackgroundScheduler()

    for monitor in monitors:
        scheduler.add_job(
            _job_for_monitor,
            "interval",
            seconds=monitor["interval_sec"],
            args=[monitor["id"]],
            id=f"monitor-{monitor['id']}",
            next_run_time=None,  # set below to run immediately on startup
            replace_existing=True,
        )
        # run once immediately so the dashboard isn't empty on startup
        scheduler.modify_job(f"monitor-{monitor['id']}", next_run_time=datetime.now())

    scheduler.start()
    return scheduler
