"""Local web dashboard: run tasks from a browser and watch the planner/builder/verifier
tiers work in real time over a WebSocket. Everything here runs on localhost only —
there's no auth because there's no network exposure by default."""

import asyncio
import json
import threading
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .. import config as config_mod
from ..engines.factory import build_engine
from ..orchestrator import Orchestrator

app = FastAPI(title="Relay Dashboard")

STATIC_DIR = Path(__file__).parent / "static"

_clients = []
_loop = None


class RunRequest(BaseModel):
    task: str
    project: str = "."
    demo: bool = False


def _broadcast(message: str) -> None:
    if _loop is None:
        return
    for ws in list(_clients):
        asyncio.run_coroutine_threadsafe(_safe_send(ws, message), _loop)


async def _safe_send(ws: WebSocket, message: str) -> None:
    try:
        await ws.send_text(message)
    except Exception:
        pass


@app.on_event("startup")
async def _startup():
    global _loop
    _loop = asyncio.get_event_loop()


@app.get("/", response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "dashboard.html").read_text()


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    _clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _clients.remove(websocket)


@app.post("/api/run")
async def api_run(req: RunRequest):
    def work():
        cfg = config_mod.load_config()
        if req.demo:
            for tier in cfg["engines"]:
                cfg["engines"][tier] = {"provider": "mock"}
        try:
            planner = build_engine(cfg["engines"]["planner"])
            builder = build_engine(cfg["engines"]["builder"])
            verifier = build_engine(cfg["engines"]["verifier"])
        except Exception as e:
            _broadcast(json.dumps({"type": "error", "message": str(e)}))
            return

        orch = Orchestrator(
            planner,
            builder,
            verifier,
            safety_cfg=cfg["safety"],
            verification_cfg=cfg["verification"],
            project_dir=req.project,
            logger=lambda msg: _broadcast(json.dumps({"type": "log", "message": str(msg)})),
            confirm_shell=lambda cmd: True,
        )
        _broadcast(json.dumps({"type": "start", "task": req.task}))
        try:
            report = orch.run(req.task)
            _broadcast(json.dumps({"type": "done", "report": report}))
        except Exception as e:
            _broadcast(json.dumps({"type": "error", "message": str(e)}))

    threading.Thread(target=work, daemon=True).start()
    return {"status": "started"}
