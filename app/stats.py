"""
stats.py — uptime percentage and latency statistics.

Functions:
- get_uptime_stats()   -> uptime %, avg latency, p95 latency over a time window
- get_history()         -> raw check rows over a time window (for graphs)
- get_incidents()       -> incident list for a monitor (or all monitors)
- get_current_status()  -> latest check + open incident flag, for /status
"""

import sqlite3


def get_uptime_stats(conn: sqlite3.Connection, monitor_id: int, hours: int = 24) -> dict:
    """
    Compute uptime % and latency stats for a monitor over the last `hours`.

    uptime_pct = (successful checks / total checks) * 100

    p95 latency: SQLite has no built-in PERCENTILE_CONT, so we pull all
    response_ms values for the window, sort them, and index into the
    sorted list at the 95th percentile position. This is fine for a
    24h window (typically a few hundred to a few thousand rows).
    """
    rows = conn.execute(
        """SELECT response_ms, success FROM checks
           WHERE monitor_id = ?
             AND checked_at >= datetime('now', ?)
           ORDER BY response_ms ASC""",
        (monitor_id, f"-{hours} hours"),
    ).fetchall()

    if not rows:
        return {
            "total_checks": 0,
            "uptime_pct": None,
            "avg_latency_ms": None,
            "p95_latency_ms": None,
        }

    total = len(rows)
    successes = sum(r["success"] for r in rows)
    latencies = [r["response_ms"] for r in rows if r["response_ms"] is not None]

    avg_latency = sum(latencies) / len(latencies) if latencies else None

    p95_latency = None
    if latencies:
        # index for the 95th percentile in a 0-indexed sorted list
        idx = min(int(len(latencies) * 0.95), len(latencies) - 1)
        p95_latency = latencies[idx]

    return {
        "total_checks": total,
        "uptime_pct": round((successes / total) * 100, 2),
        "avg_latency_ms": round(avg_latency, 1) if avg_latency is not None else None,
        "p95_latency_ms": p95_latency,
    }


def get_history(conn: sqlite3.Connection, monitor_id: int, hours: int = 24) -> list[dict]:
    """
    Return raw check rows for a monitor over the last `hours`,
    oldest first (good for plotting a time-series).
    """
    rows = conn.execute(
        """SELECT status_code, response_ms, success, error, checked_at
           FROM checks
           WHERE monitor_id = ?
             AND checked_at >= datetime('now', ?)
           ORDER BY checked_at ASC""",
        (monitor_id, f"-{hours} hours"),
    ).fetchall()
    return [dict(r) for r in rows]


def get_incidents(conn: sqlite3.Connection, monitor_id: int | None = None) -> list[dict]:
    """
    Return incidents, optionally filtered to a single monitor.
    Includes a computed `duration_sec` for resolved incidents.
    Open incidents (resolved_at IS NULL) have duration_sec = None.
    """
    if monitor_id is not None:
        rows = conn.execute(
            """SELECT i.*, m.name AS monitor_name, m.url AS monitor_url,
                      CAST((julianday(COALESCE(i.resolved_at, datetime('now'))) - julianday(i.started_at)) * 86400 AS INTEGER) AS duration_sec
               FROM incidents i
               JOIN monitors m ON m.id = i.monitor_id
               WHERE i.monitor_id = ?
               ORDER BY i.started_at DESC""",
            (monitor_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT i.*, m.name AS monitor_name, m.url AS monitor_url,
                      CAST((julianday(COALESCE(i.resolved_at, datetime('now'))) - julianday(i.started_at)) * 86400 AS INTEGER) AS duration_sec
               FROM incidents i
               JOIN monitors m ON m.id = i.monitor_id
               ORDER BY i.started_at DESC"""
        ).fetchall()

    return [dict(r) for r in rows]


def get_current_status(conn: sqlite3.Connection) -> list[dict]:
    """
    For every monitor, return its latest check result plus whether it
    currently has an open incident. This powers /status and the CLI dashboard.
    """
    monitors = conn.execute("SELECT * FROM monitors").fetchall()
    results = []

    for m in monitors:
        latest = conn.execute(
            """SELECT status_code, response_ms, success, error, checked_at
               FROM checks WHERE monitor_id = ?
               ORDER BY checked_at DESC, id DESC LIMIT 1""",
            (m["id"],),
        ).fetchone()

        open_incident = conn.execute(
            "SELECT id, started_at FROM incidents WHERE monitor_id = ? AND resolved_at IS NULL",
            (m["id"],),
        ).fetchone()

        results.append({
            "id": m["id"],
            "name": m["name"],
            "url": m["url"],
            "latest_check": dict(latest) if latest else None,
            "is_down": open_incident is not None,
            "incident_since": open_incident["started_at"] if open_incident else None,
        })

    return results
