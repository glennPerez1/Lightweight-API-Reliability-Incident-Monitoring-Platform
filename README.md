# API Health Monitor

A lightweight, self-hosted tool that watches a list of websites/APIs,
records their uptime and response time history, and automatically detects
incidents (sustained outages) — similar in spirit to UptimeRobot or
Pingdom, but small enough to run on your own laptop.

It's built entirely in Python with FastAPI, SQLite, and APScheduler — no
external services or accounts required to get started.

---

## What it does

- **Pings** each configured URL on its own schedule (e.g. every 30 or 60
  seconds)
- **Records** every check (status code, response time, success/failure) in
  a local SQLite database
- **Detects incidents**: if a URL fails 3 times in a row, an "incident" is
  opened. When it recovers, the incident is automatically closed and its
  duration is recorded
- **Reports**: uptime percentage and p95 latency over the last 24 hours,
  via a REST API, a live terminal dashboard, and a simple HTML status page
- **Alerts** (optional): sends a message to a Discord webhook when a
  service goes down or recovers

---

## Project structure

```
api-health-monitor/
├── monitors.json       # Configure which URLs to watch
├── requirements.txt     # Python dependencies
├── main.py                # Entry point — run this to start everything
├── app/
│   ├── db.py               # Database setup
│   ├── checker.py            # Pings URLs and records results
│   ├── incidents.py           # Incident detection logic
│   ├── alerts.py                # Sends Discord alerts
│   ├── stats.py                  # Uptime % and latency calculations
│   ├── scheduler.py               # Schedules checks in the background
│   ├── cli.py                      # Live terminal dashboard
│   └── api.py                       # FastAPI web server
└── templates/
    └── status.html                  # HTML status page
```

---

## Requirements

- Python 3.10 or newer
- pip (comes with Python)

---

## Setup — running it on your own laptop

These steps work the same on Windows (using Git Bash), macOS, and Linux.

### 1. Clone the repository

```bash
git clone git@github.com:glennPerez1/Lightweight-API-Reliability-Incident-Monitoring-Platform.git
git clone https://github.com/glennPerez1/Lightweight-API-Reliability-Incident-Monitoring-Platform.git
cd api-health-monitor
```

### 2. Create a virtual environment

A virtual environment keeps this project's dependencies separate from
everything else on your system.

```bash
python -m venv venv
```

If `python` doesn't work, try `python3` or (on Windows) `py`.

### 3. Activate the virtual environment

**On Windows (Git Bash):**
```bash
source venv/Scripts/activate
```

**On Windows (Command Prompt):**
```cmd
venv\Scripts\activate.bat
```

**On macOS / Linux:**
```bash
source venv/bin/activate
```

You'll know it worked when you see `(venv)` at the start of your terminal
prompt.

### 4. Install dependencies

```bash
pip install -r requirements.txt
```

### 5. (Optional) Configure monitors and alerts

Open `monitors.json` and edit the list of URLs you want to monitor:

```json
{
  "monitors": [
    {
      "name": "GitHub API",
      "url": "https://api.github.com",
      "interval_sec": 30,
      "timeout_sec": 5,
      "fail_threshold": 3
    }
  ],
  "alerting": {
    "discord_webhook_url": "",
    "enabled": false
  }
}
```

- `interval_sec` — how often (in seconds) this URL is checked
- `timeout_sec` — how long to wait before treating the request as failed
- `fail_threshold` — how many consecutive failures count as an "incident"

To enable Discord alerts: create a webhook in your Discord server
(Server Settings → Integrations → Webhooks → New Webhook → Copy URL),
paste the URL into `discord_webhook_url`, and set `"enabled": true`.

If you skip this, the app still works — alerts are simply printed to the
terminal instead.

### 6. Run the app

```bash
python main.py
```

You should see output like:

```
Scheduler started. Checks are running in the background.
[GitHub API] UP - 142ms - status=200
INFO:     Uvicorn running on http://0.0.0.0:8000
```

Leave this running — it's both your background monitor and your web
server.

---

## Using the project

While `main.py` is running, open these in your browser:

| URL | What it shows |
|---|---|
| `http://localhost:8000/docs` | Interactive API docs (Swagger UI) — try every endpoint here |
| `http://localhost:8000/status` | Raw JSON: current status of all monitors |
| `http://localhost:8000/page` | A simple visual status page (green/red cards) |
| `http://localhost:8000/incidents` | List of past and ongoing incidents |

### Live terminal dashboard

Open a **second terminal**, activate the virtual environment again, and
run:

```bash
source venv/Scripts/activate   # or venv/bin/activate on Mac/Linux
python -m app.cli
```

This shows a live, auto-refreshing table with current status, uptime %,
and latency for every monitor.

### Stopping the app

Press `Ctrl + C` in each terminal.

---

## Testing that everything works

### 1. Check the terminal output
You should see a new line every 30-60 seconds, like:
```
[GitHub API] UP - 142ms - status=200
```

### 2. Check `/status`
Visit `http://localhost:8000/status`. Each monitor should have a
`latest_check` with a real `status_code` and `success: 1`.

### 3. Check `/page`
Visit `http://localhost:8000/page`. You should see a green card with "UP"
and an uptime percentage for each monitor.

### 4. Check the database directly
With the app running, open a third terminal (venv activated) and run:

```bash
python -c "
from app.db import get_connection
conn = get_connection()
rows = conn.execute('SELECT * FROM checks ORDER BY id DESC LIMIT 5').fetchall()
for r in rows:
    print(dict(r))
"
```

You should see real rows with timestamps and latencies.

### 5. Test incident detection
Add a URL that doesn't exist to `monitors.json`:

```json
{
  "name": "Broken endpoint",
  "url": "https://this-does-not-exist-abc123xyz.com",
  "interval_sec": 15,
  "timeout_sec": 5,
  "fail_threshold": 3
}
```

Restart `python main.py`, wait about 45-60 seconds, then check
`http://localhost:8000/incidents`. You should see an entry with
`"cause": "3 consecutive failed checks"` and `"resolved_at": null`.
You'll also see `[ALERT - not sent, alerting disabled] 🔴 DOWN: ...` printed
in the terminal.

Remove this entry from `monitors.json` once you're done testing.

---

## Resetting the database

The database (`monitor.db`) is created automatically on first run. To start
completely fresh, stop the app and delete it:

```bash
rm monitor.db
```

(On Windows Command Prompt: `del monitor.db`)

---

## Known limitations / possible improvements

- Adding a monitor via `POST /monitors` requires an app restart to start
  scheduling checks for it
- p95 latency can be noisy with very few data points (small sample sizes)
- SQLite is suitable for low/moderate write volume — a high-traffic
  deployment with hundreds of monitors checking every second would benefit
  from PostgreSQL
- No authentication on the API — fine for local/personal use, would need
  an API key or login for a public deployment

---

## Tech stack

- **Python 3** — core language
- **FastAPI** — REST API and web server
- **SQLite** — local database (zero setup required)
- **APScheduler** — background job scheduling
- **httpx** — making HTTP requests to monitored endpoints
- **Rich** — live terminal dashboard
- **Jinja2** — HTML templating for the status page
