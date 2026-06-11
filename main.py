"""
main.py — entrypoint. Initializes the DB, starts the background
scheduler (which runs health checks), and starts the FastAPI server.

Run with: python main.py
Then visit:
    http://localhost:8000/status
    http://localhost:8000/page
    http://localhost:8000/docs   (Swagger UI)

For the live terminal dashboard, run separately in another terminal:
    python -m app.cli
"""

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from app.db import init_db
from app.scheduler import start_scheduler
from app.api import app as api_app


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    print("Scheduler started. Checks are running in the background.")
    yield


api_app.router.lifespan_context = lifespan
app = api_app


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
