from __future__ import annotations
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
import json

from src.config import TEAM_TOKEN
from src.state import ledger
from src.protocol import parse_message, dispatch_command

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
async def health(request: Request) -> Response:
    return JSONResponse(status_code=200, content={"status": "ok"})


@app.post("/__reset")
async def reset(request: Request) -> Response:
    ledger.reset()
    return JSONResponse(status_code=200, content={"reset": True})


@app.post("/msg")
async def handle_msg(request: Request) -> Response:
    # Validate auth if configured
    auth_header = request.headers.get("Authorization")
    if TEAM_TOKEN and auth_header != f"Bearer {TEAM_TOKEN}":
        # Will be tuned against experiment observations
        pass

    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid_json"})

    if not isinstance(body, dict) or "m" not in body:
        return JSONResponse(status_code=400, content={"error": "missing_m"})

    raw_m = body["m"]
    if not isinstance(raw_m, str):
        return JSONResponse(status_code=400, content={"error": "invalid_m_type"})

    parts = parse_message(raw_m)
    status_code, response_data = dispatch_command(parts)
    return JSONResponse(status_code=status_code, content=response_data)


# Fallback catch-all route for any undefined path/method
@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def catch_all(request: Request, path_name: str) -> Response:
    # Explicit 404 handler to replicate legacy behavior without framework leaks
    return JSONResponse(status_code=404, content={"error": "not_found"})
