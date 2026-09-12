"""Local web dashboard: configure providers, run tasks from a browser, and watch the
planner/builder/verifier tiers work in real time over a WebSocket. Everything here runs
on localhost only — there's no auth because there's no network exposure by default."""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .. import config as config_mod
from ..engines.factory import build_engine, EngineConfigError, KNOWN_PLATFORMS
from ..orchestrator import Orchestrator
from ..router import Router, TokenBudget

app = FastAPI(title="Relay Dashboard")

STATIC_DIR = Path(__file__).parent / "static"

_clients = []
_loop = None
_history = []  # in-memory run history for this dashboard session, newest first

SECRET_FIELDS = {"api_key"}


def _redact(cfg_piece):
    """Deep-copy a config fragment with secret fields masked, so the browser never
    receives raw API keys back from a GET (only echoes of what it already knows)."""
    if isinstance(cfg_piece, dict):
        out = {}
        for k, v in cfg_piece.items():
            if k in SECRET_FIELDS and v:
                out[k] = "•" * 8 + str(v)[-4:] if len(str(v)) > 4 else "••••"
            else:
                out[k] = _redact(v)
        return out
    if isinstance(cfg_piece, list):
        return [_redact(v) for v in cfg_piece]
    return cfg_piece


class RunRequest(BaseModel):
    task: str
    project: str = "."
    demo: bool = False


class ConfigUpdate(BaseModel):
    engines: dict | None = None
    router: dict | None = None
    connections: list | None = None


class ConnectionTest(BaseModel):
    provider: str
    model: str
    base_url: str | None = None
    api_key: str | None = None
    workspace_id: str | None = None
    connection_id: str | None = None


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


# ---------------------------------------------------------------------------
# Settings: read/write engines + router + saved connections
# ---------------------------------------------------------------------------

@app.get("/api/config")
async def api_get_config():
    cfg = config_mod.load_config()
    return {
        "engines": _redact(cfg.get("engines", {})),
        "router": _redact(cfg.get("router", {})),
        "connections": _redact(cfg.get("connections", [])),
        "known_platforms": KNOWN_PLATFORMS,
    }


@app.post("/api/config")
async def api_update_config(update: ConfigUpdate):
    cfg = config_mod.load_config()
    path = config_mod.DEFAULT_CONFIG_PATH

    # Merge rather than replace, and never let a redacted "••••1234" placeholder
    # overwrite a real stored key — only replace api_key fields the browser actually
    # changed (i.e. that don't look like our own redaction marker).
    def merge_engine(existing: dict, incoming: dict) -> dict:
        merged = dict(existing or {})
        for k, v in (incoming or {}).items():
            if k == "api_key" and isinstance(v, str) and v.startswith("•"):
                continue
            merged[k] = v
        return merged

    if update.engines:
        for tier, incoming in update.engines.items():
            cfg.setdefault("engines", {})[tier] = merge_engine(cfg.get("engines", {}).get(tier), incoming)

    if update.router:
        router_cfg = cfg.setdefault("router", {})
        for k, v in update.router.items():
            if k == "rungs":
                existing_rungs = router_cfg.setdefault("rungs", {})
                for rung_name, rung_val in (v or {}).items():
                    if rung_val is None:
                        existing_rungs[rung_name] = None
                    else:
                        existing_rungs[rung_name] = merge_engine(existing_rungs.get(rung_name), rung_val)
            else:
                router_cfg[k] = v

    if update.connections is not None:
        merged_conns = []
        existing_by_id = {c.get("id"): c for c in cfg.get("connections", [])}
        for incoming in update.connections:
            existing = existing_by_id.get(incoming.get("id"))
            merged_conns.append(merge_engine(existing, incoming) if existing else incoming)
        cfg["connections"] = merged_conns

    path.parent.mkdir(parents=True, exist_ok=True)
    import yaml

    with open(path, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)

    return {
        "engines": _redact(cfg.get("engines", {})),
        "router": _redact(cfg.get("router", {})),
        "connections": _redact(cfg.get("connections", [])),
    }


@app.post("/api/test-connection")
async def api_test_connection(test: ConnectionTest):
    tier_cfg = {"provider": test.provider, "model": test.model}
    if test.base_url:
        tier_cfg["base_url"] = test.base_url

    if test.workspace_id:
        tier_cfg["workspace_id"] = test.workspace_id

    if test.api_key and not test.api_key.startswith("•"):
        # A real key was typed into the "add connection" form — use it directly.
        tier_cfg["api_key"] = test.api_key
    elif test.connection_id:
        # Testing an already-saved connection: the browser only ever sees a
        # redacted "••••1234" placeholder for api_key, so look the real key up
        # server-side by id instead of trusting whatever the browser sent.
        cfg = config_mod.load_config()
        saved = next((c for c in cfg.get("connections", []) if c.get("id") == test.connection_id), None)
        if saved and saved.get("api_key"):
            tier_cfg["api_key"] = saved["api_key"]
        if saved and saved.get("workspace_id"):
            tier_cfg["workspace_id"] = saved["workspace_id"]
    try:
        engine = build_engine(tier_cfg)
        result = engine.complete(
            system="Reply with exactly one word.",
            prompt="Reply with the single word: OK",
            max_tokens=10,
        )
        return {"ok": True, "reply": result.text.strip()[:80], "model": result.model}
    except (EngineConfigError, RuntimeError) as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # noqa: BLE001 - surfacing any provider SDK error to the UI
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


@app.get("/api/history")
async def api_history():
    return {"runs": _history[:50]}


# ---------------------------------------------------------------------------
# Running tasks
# ---------------------------------------------------------------------------

@app.post("/api/run")
async def api_run(req: RunRequest):
    run_id = str(uuid.uuid4())[:8]

    def work():
        cfg = config_mod.load_config()
        if req.demo:
            for tier in cfg["engines"]:
                cfg["engines"][tier] = {"provider": "mock"}
            cfg["router"] = {"enabled": False}

        try:
            planner = build_engine(cfg["engines"]["planner"])
            builder = build_engine(cfg["engines"]["builder"])
            verifier = build_engine(cfg["engines"]["verifier"])
        except Exception as e:
            _broadcast(json.dumps({"type": "error", "message": str(e)}))
            return

        router = None
        rung_engines = {}
        router_cfg = cfg.get("router", {})
        if router_cfg.get("enabled"):
            for rung_name, rung_cfg in (router_cfg.get("rungs") or {}).items():
                if not rung_cfg:
                    continue
                try:
                    rung_engines[rung_name] = build_engine(rung_cfg)
                except Exception as e:
                    _broadcast(json.dumps({"type": "log", "message": f"[router] skipping rung '{rung_name}': {e}"}))
            if rung_engines:
                router = Router(router_cfg, budget=TokenBudget(router_cfg.get("max_tokens_per_run")))

        orch = Orchestrator(
            planner,
            builder,
            verifier,
            safety_cfg=cfg["safety"],
            verification_cfg=cfg["verification"],
            project_dir=req.project,
            logger=lambda msg: _broadcast(json.dumps({"type": "log", "message": str(msg)})),
            confirm_shell=lambda cmd: True,
            router=router,
            rung_engines=rung_engines,
        )
        started_at = time.time()
        _broadcast(json.dumps({"type": "start", "task": req.task, "run_id": run_id, "routed": router is not None}))
        try:
            report = orch.run(req.task)
            report["run_id"] = run_id
            report["duration_s"] = round(time.time() - started_at, 1)
            _history.insert(0, {
                "run_id": run_id,
                "task": req.task,
                "project": req.project,
                "passed": (report.get("verify_result") or {}).get("passed", False),
                "total_tokens": report.get("grand_total_tokens", 0),
                "routed": report.get("routed", False),
                "duration_s": report["duration_s"],
                "timestamp": time.time(),
            })
            _broadcast(json.dumps({"type": "done", "report": report}))
        except Exception as e:
            _broadcast(json.dumps({"type": "error", "message": str(e)}))

    threading.Thread(target=work, daemon=True).start()
    return {"status": "started", "run_id": run_id}
