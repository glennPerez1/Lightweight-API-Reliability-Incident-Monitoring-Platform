"""
api.py — FastAPI app exposing the monitoring data over HTTP.

Endpoints:
- GET  /status                      -> current status of all monitors
- GET  /monitors/{id}/history       -> time-series of checks for one monitor
- GET  /monitors/{id}/uptime        -> uptime % + latency stats for one monitor
- GET  /incidents                   -> all incidents (optionally filter by monitor_id)
- POST /monitors                    -> add a new monitor
- GET  /page                        -> HTML status page (Jinja2)
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, HttpUrl

from app.db import get_connection, get_or_create_monitor
from app.stats import get_current_status, get_history, get_uptime_stats, get_incidents

app = FastAPI(title="API Health Monitor")

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


class MonitorCreate(BaseModel):
    name: str
    url: HttpUrl
    interval_sec: int = 60
    timeout_sec: int = 5
    fail_threshold: int = 3


@app.get("/status")
def status():
    """
    Current status of every monitor: latest check result and whether
    it currently has an open incident.
    """
    conn = get_connection()
    result = get_current_status(conn)
    conn.close()
    return {"monitors": result}


@app.get("/monitors/{monitor_id}/history")
def history(monitor_id: int, hours: int = Query(24, ge=1, le=168)):
    """
    Time-series of raw checks for a monitor over the last `hours`
    (default 24, max 168 = 1 week). Useful for plotting a latency graph.
    """
    conn = get_connection()
    monitor = conn.execute("SELECT id FROM monitors WHERE id = ?", (monitor_id,)).fetchone()
    if not monitor:
        conn.close()
        raise HTTPException(status_code=404, detail="Monitor not found")

    result = get_history(conn, monitor_id, hours)
    conn.close()
    return {"monitor_id": monitor_id, "hours": hours, "checks": result}


@app.get("/monitors/{monitor_id}/uptime")
def uptime(monitor_id: int, hours: int = Query(24, ge=1, le=168)):
    """
    Uptime % and latency stats (avg, p95) for a monitor over the last `hours`.
    """
    conn = get_connection()
    monitor = conn.execute("SELECT id FROM monitors WHERE id = ?", (monitor_id,)).fetchone()
    if not monitor:
        conn.close()
        raise HTTPException(status_code=404, detail="Monitor not found")

    result = get_uptime_stats(conn, monitor_id, hours)
    conn.close()
    return {"monitor_id": monitor_id, "hours": hours, **result}


@app.get("/incidents")
def incidents(monitor_id: int | None = Query(None)):
    """
    List incidents, optionally filtered to a single monitor.
    Each incident includes duration_sec (None if still open).
    """
    conn = get_connection()
    if monitor_id is not None:
        monitor = conn.execute("SELECT id FROM monitors WHERE id = ?", (monitor_id,)).fetchone()
        if not monitor:
            conn.close()
            raise HTTPException(status_code=404, detail="Monitor not found")

    result = get_incidents(conn, monitor_id)
    conn.close()
    return {"incidents": result}


@app.post("/monitors", status_code=201)
def create_monitor(monitor: MonitorCreate):
    """
    Add a new monitor. Note: this only adds it to the database — to
    actually start scheduling checks for it, the app needs a restart
    (the scheduler reads monitors.json + DB at startup). For the
    2-day version, this is an acceptable known limitation worth
    mentioning in your README as a "future improvement".
    """
    conn = get_connection()
    monitor_id = get_or_create_monitor(
        conn,
        name=monitor.name,
        url=str(monitor.url),
        interval_sec=monitor.interval_sec,
        timeout_sec=monitor.timeout_sec,
        fail_threshold=monitor.fail_threshold,
    )
    conn.close()
    return {"id": monitor_id, "name": monitor.name, "url": str(monitor.url)}


@app.get("/page", response_class=HTMLResponse)
def status_page(request: Request):
    """
    Renders a simple public status page showing all monitors as
    colored cards (green = up, red = down).
    """
    conn = get_connection()
    monitors = get_current_status(conn)
    for m in monitors:
        m["uptime"] = get_uptime_stats(conn, m["id"], hours=24)
    conn.close()

    return templates.TemplateResponse(
        "status.html", {"request": request, "monitors": monitors}
    )
