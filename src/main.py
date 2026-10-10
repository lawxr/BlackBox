from __future__ import annotations
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
import json

from src.config import TEAM_TOKEN
from src.state import ledger
from src.protocol import parse_message, dispatch_command

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


from typing import Optional

def check_auth(request: Request) -> Optional[Response]:
    if not TEAM_TOKEN:
        return None
    auth_header = request.headers.get("Authorization")
    if auth_header != f"Bearer {TEAM_TOKEN}":
        return JSONResponse(status_code=401, content={"error": "E001", "mensaje": "no autorizado"})
    return None


@app.get("/health")
async def health(request: Request) -> Response:
    auth_err = check_auth(request)
    if auth_err:
        return auth_err
    return JSONResponse(status_code=200, content={"ok": True})


@app.post("/__reset")
async def reset(request: Request) -> Response:
    auth_err = check_auth(request)
    if auth_err:
        return auth_err
    ledger.reset()
    return JSONResponse(status_code=200, content={"ok": True})


@app.post("/msg")
async def handle_msg(request: Request) -> Response:
    auth_err = check_auth(request)
    if auth_err:
        return auth_err

    try:
        raw_body = await request.body()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "E100", "mensaje": "json inválido"})

    if not raw_body:
        return JSONResponse(status_code=400, content={"error": "E100", "mensaje": "json inválido"})

    try:
        body = json.loads(raw_body)
    except Exception:
        return JSONResponse(status_code=400, content={"error": "E100", "mensaje": "json inválido"})

    if not isinstance(body, dict) or "m" not in body or not isinstance(body["m"], str):
        return JSONResponse(status_code=400, content={"error": "E102", "mensaje": "falta m"})

    parts = parse_message(body["m"])
    status_code, response_data = dispatch_command(parts)
    return JSONResponse(status_code=status_code, content=response_data)


# Fallback catch-all route for any undefined path/method
@app.api_route("/{path_name:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def catch_all(request: Request, path_name: str) -> Response:
    return JSONResponse(status_code=404, content={"error": "E404", "mensaje": "ruta desconocida"})
