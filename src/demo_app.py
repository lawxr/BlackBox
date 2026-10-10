"""Explanatory dashboard app, kept outside the evaluated entrypoint.

The evaluated replica (`src.main:app`) must answer every non-contract path like
the original (404 E404), so the dashboard lives in its own ASGI app: it serves
/demo and delegates every other request to the replica unchanged.

Run: uv run uvicorn src.demo_app:app --port 8001
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from src.demo_page import DEMO_HTML
from src.main import app as replica

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.api_route("/demo", methods=["GET", "HEAD"], response_class=HTMLResponse)
@app.api_route("/demo/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def demo_dashboard() -> HTMLResponse:
    return HTMLResponse(content=DEMO_HTML)


app.mount("/", replica)
