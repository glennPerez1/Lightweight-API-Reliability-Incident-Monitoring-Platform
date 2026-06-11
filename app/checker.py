"""
checker.py — the core "check and record" function.

This is the heart of the whole project. Everything else (scheduler, CLI,
API stats) builds on top of the rows this function writes.

Functions:
- check_endpoint()    -> pings a URL, returns a result dict (pure, no DB access)
- record_check()       -> writes a result dict to the checks table
- run_check_cycle()     -> combines the two above + triggers incident detection
"""

import time
import sqlite3
import httpx

from app.incidents import evaluate_incident_state


def check_endpoint(url: str, timeout_sec: int) -> dict:
    """
    Make a single HTTP GET request to `url` and measure the result.

    Returns a dict with:
        status_code : int | None   (None if the request raised an exception)
        response_ms : int          (time taken, in milliseconds)
        success     : bool         (True if status_code is in 200-399 range)
        error       : str | None   (exception message, if any)

    This function is intentionally "pure" with respect to the database —
    it has no side effects, which makes it trivial to unit test:
    you can mock httpx and assert on the returned dict directly.
    """
    start = time.monotonic()
    try:
        response = httpx.get(url, timeout=timeout_sec, follow_redirects=True)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "status_code": response.status_code,
            "response_ms": elapsed_ms,
            "success": 200 <= response.status_code < 400,
            "error": None,
        }
    except httpx.TimeoutException:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "status_code": None,
            "response_ms": elapsed_ms,
            "success": False,
            "error": "timeout",
        }
    except httpx.RequestError as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "status_code": None,
            "response_ms": elapsed_ms,
            "success": False,
            "error": str(exc),
        }


def record_check(conn: sqlite3.Connection, monitor_id: int, result: dict) -> int:
    """
    Insert a check result into the `checks` table.
    Returns the id of the inserted row.
    """
    cursor = conn.execute(
        """INSERT INTO checks (monitor_id, status_code, response_ms, success, error)
           VALUES (?, ?, ?, ?, ?)""",
        (
            monitor_id,
            result["status_code"],
            result["response_ms"],
            1 if result["success"] else 0,
            result["error"],
        ),
    )
    conn.commit()
    return cursor.lastrowid


def run_check_cycle(conn: sqlite3.Connection, monitor: sqlite3.Row) -> dict:
    """
    Full cycle for one monitor: check -> record -> evaluate incident state.

    `monitor` is a row from the monitors table (has id, url, timeout_sec,
    fail_threshold, etc).

    Returns the result dict from check_endpoint(), so callers (CLI,
    scheduler logs) can print it immediately without a second DB query.
    """
    result = check_endpoint(monitor["url"], monitor["timeout_sec"])
    record_check(conn, monitor["id"], result)

    # After recording, check whether this changes the incident state
    # (opens a new incident, or resolves an existing one)
    evaluate_incident_state(conn, monitor)

    return result
