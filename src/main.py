"""HTTP layer: routes, auth and body validation, all taken from the active profile."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from src import profile
from src.config import TEAM_TOKEN
from src.demo_page import DEMO_HTML
from src.protocol import error_response, process_message
from src.state import ledger

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

ALL_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]


@app.get("/demo", response_class=HTMLResponse)
@app.get("/demo/", response_class=HTMLResponse)
async def demo_dashboard() -> HTMLResponse:
    return HTMLResponse(content=DEMO_HTML)


def _json(result) -> Response:
    status, body = result
    return JSONResponse(status_code=status, content=body)


def check_auth(request: Request) -> Optional[Response]:
    if not TEAM_TOKEN:
        return None
    auth = profile.get()["http"]["auth"]
    if request.headers.get("Authorization") != f"{auth['scheme']} {TEAM_TOKEN}":
        return _json(error_response(auth["error"]))
    return None


def _find_route(method: str, path: str) -> Optional[Dict[str, Any]]:
    for route in profile.get()["http"]["routes"]:
        if route["method"] == method and route["path"] == "/" + path:
            return route
    return None


async def _message(request: Request) -> Response:
    http = profile.get()["http"]
    raw_body = await request.body()
    max_body = profile.get().get("max_body_bytes")
    if max_body is not None and len(raw_body) > max_body:
        return _json(error_response("E101"))
    if raw_body.startswith(b"\xef\xbb\xbf"):
        return _json(error_response(http["invalid_json_error"]))

    invalid = object()  # sentinel: a JSON `null` body is valid JSON, not invalid
    try:
        body = json.loads(raw_body) if raw_body else invalid
    except Exception:
        body = invalid
    if body is invalid:
        return _json(error_response(http["invalid_json_error"]))
    field = http["message_field"]
    if not isinstance(body, dict) or not isinstance(body.get(field), str):
        return _json(error_response(http["missing_message_error"]))
    return _json(process_message(body[field]))


# One catch-all dispatcher: unknown routes answer before auth is evaluated.
@app.api_route("/{path_name:path}", methods=ALL_METHODS)
async def dispatch(request: Request, path_name: str) -> Response:
    route = _find_route(request.method, path_name)
    if route is None:
        return _json(error_response(profile.get()["http"]["unknown_route_error"]))
    auth_err = check_auth(request)
    if auth_err:
        return auth_err
    if route["kind"] == "message":
        return await _message(request)
    if route["kind"] == "reset":
        ledger.reset()
    return JSONResponse(status_code=route["status"], content=route["body"])
