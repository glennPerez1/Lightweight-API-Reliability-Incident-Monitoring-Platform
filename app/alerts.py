"""
alerts.py — sends notifications when incidents open or resolve.

Functions:
- load_alert_config()  -> reads alerting settings from monitors.json
- send_alert()          -> posts a message to the configured Discord webhook
"""

import json
from pathlib import Path

import httpx

CONFIG_PATH = Path(__file__).parent.parent / "monitors.json"


def load_alert_config() -> dict:
    """Read the 'alerting' section from monitors.json."""
    with open(CONFIG_PATH) as f:
        config = json.load(f)
    return config.get("alerting", {"enabled": False})


def send_alert(message: str) -> None:
    """
    Send `message` to the configured Discord webhook.

    If alerting is disabled or no webhook URL is set, this just prints
    to stdout instead — so the app works out of the box without any
    external setup, and you can wire up Discord later.

    Discord webhooks accept a simple POST with JSON body {"content": "..."}.
    """
    config = load_alert_config()

    if not config.get("enabled") or not config.get("discord_webhook_url"):
        print(f"[ALERT - not sent, alerting disabled] {message}")
        return

    try:
        httpx.post(
            config["discord_webhook_url"],
            json={"content": message},
            timeout=5,
        )
    except httpx.RequestError as exc:
        # Don't let a failed alert crash the monitoring loop
        print(f"[ALERT - failed to send] {message} (error: {exc})")
