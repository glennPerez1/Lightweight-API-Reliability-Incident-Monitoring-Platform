"""
incidents.py — incident detection state machine.

State machine per monitor:
    healthy --(N consecutive failures)--> incident OPEN
    incident OPEN --(1 successful check)--> incident RESOLVED

Functions:
- get_recent_results()    -> last N success/fail flags for a monitor
- get_open_incident()      -> the currently open incident row, if any
- evaluate_incident_state() -> the main state machine, called after every check
- open_incident()           -> insert a new incident row
- resolve_incident()        -> close an existing incident row
"""

import sqlite3

from app.alerts import send_alert


def get_recent_results(conn: sqlite3.Connection, monitor_id: int, limit: int) -> list[int]:
    """
    Return the `success` values (0/1) of the last `limit` checks for this
    monitor, most recent first.
    """
    rows = conn.execute(
        """SELECT success FROM checks
           WHERE monitor_id = ?
           ORDER BY checked_at DESC, id DESC
           LIMIT ?""",
        (monitor_id, limit),
    ).fetchall()
    return [row["success"] for row in rows]


def get_open_incident(conn: sqlite3.Connection, monitor_id: int) -> sqlite3.Row | None:
    """
    Return the open incident for this monitor (resolved_at IS NULL),
    or None if there isn't one.
    """
    return conn.execute(
        """SELECT * FROM incidents
           WHERE monitor_id = ? AND resolved_at IS NULL
           ORDER BY started_at DESC LIMIT 1""",
        (monitor_id,),
    ).fetchone()


def open_incident(conn: sqlite3.Connection, monitor_id: int, cause: str) -> int:
    """Insert a new open incident row. Returns its id."""
    cursor = conn.execute(
        "INSERT INTO incidents (monitor_id, cause) VALUES (?, ?)",
        (monitor_id, cause),
    )
    conn.commit()
    return cursor.lastrowid


def resolve_incident(conn: sqlite3.Connection, incident_id: int) -> None:
    """Mark an incident as resolved (sets resolved_at to now)."""
    conn.execute(
        "UPDATE incidents SET resolved_at = datetime('now') WHERE id = ?",
        (incident_id,),
    )
    conn.commit()


def evaluate_incident_state(conn: sqlite3.Connection, monitor: sqlite3.Row) -> None:
    """
    The core state machine. Called after every check is recorded.

    Logic:
    1. Look at the most recent check.
    2. If it succeeded AND there's an open incident -> resolve it, send recovery alert.
    3. If it failed -> count how many of the last `fail_threshold` checks failed.
       If ALL of them failed AND there's no open incident -> open one, send alert.

    This "all of the last N failed" check (rather than "N total failures
    ever") is what makes it a *consecutive* failure detector — a single
    blip surrounded by successes never triggers an incident.
    """
    monitor_id = monitor["id"]
    fail_threshold = monitor["fail_threshold"]

    recent = get_recent_results(conn, monitor_id, fail_threshold)
    if not recent:
        return

    latest_success = recent[0] == 1
    open_inc = get_open_incident(conn, monitor_id)

    if latest_success:
        if open_inc:
            resolve_incident(conn, open_inc["id"])
            send_alert(
                f"✅ RESOLVED: {monitor['name']} ({monitor['url']}) is back up."
            )
        return

    # latest check failed — has it failed `fail_threshold` times in a row?
    if len(recent) == fail_threshold and all(r == 0 for r in recent) and not open_inc:
        cause = f"{fail_threshold} consecutive failed checks"
        open_incident(conn, monitor_id, cause)
        send_alert(
            f"🔴 DOWN: {monitor['name']} ({monitor['url']}) — {cause}."
        )
