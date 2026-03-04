"""
Eliobot Dashboard - FastAPI backend
WebSocket push temps réel (300ms) + REST pour commandes MQTT
"""

import asyncio
import copy
import json
import os
import random
import threading
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── Configuration ─────────────────────────────────────────────────────────────
MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
STATIC_DIR = Path(__file__).parent / "static"

# Offsets de déplacement par heading : N=0, E=1, S=2, W=3
_HDX = {0: 0, 1: 1, 2: 0, 3: -1}
_HDY = {0: 1, 1: 0, 2: -1, 3: 0}

# ── État partagé (accès thread-safe via _lock) ────────────────────────────────
_lock = threading.Lock()
_state: dict = {
    "connected": False,
    "last_seen": None,        # ISO string ou None
    "battery_v": None,
    "obstacles": {"front": False, "left": False, "right": False, "back": False},
    "mode": "idle",
    "steps": deque(maxlen=1000),
    "eyes":  {"pattern": "emotionConfused", "color": [50, 50, 50]},
    "lines":   [0, 0, 0, 0, 0],
    "visited": set(),   # cellules explorées (x, y) - cerveau exploration
}


def _snapshot() -> dict:
    """Retourne une copie sérialisable de l'état courant."""
    with _lock:
        return {
            "connected": _state["connected"],
            "last_seen": _state["last_seen"],
            "battery_v": _state["battery_v"],
            "obstacles": copy.copy(_state["obstacles"]),
            "mode":      _state["mode"],
            "steps":     list(_state["steps"]),
            "eyes":      copy.copy(_state["eyes"]),
            "lines":         list(_state["lines"]),
            "visited_count": len(_state["visited"]),
        }


# ── Client MQTT (tourne dans son propre thread via loop_start) ─────────────────
_mqttc = mqtt.Client(
    callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
    client_id="eliobot-fastapi-dashboard",
)


def _on_connect(client, userdata, flags, rc):
    with _lock:
        _state["connected"] = (rc == 0)
    if rc == 0:
        client.subscribe([
            ("elio/telemetry/battery",  0),
            ("elio/telemetry/obstacles", 0),
            ("elio/telemetry/mode",     0),
            ("elio/telemetry/step",     0),
            ("elio/telemetry/eyes",     0),
            ("elio/telemetry/lines",    0),
        ])
        print(f"[MQTT] Connecté à {MQTT_BROKER}:{MQTT_PORT}")
    else:
        print(f"[MQTT] Connexion refusée (rc={rc})")


def _on_disconnect(client, userdata, rc):
    with _lock:
        _state["connected"] = False
    print(f"[MQTT] Déconnecté (rc={rc})")


def _explore_next_step(step: dict):
    """
    Cerveau de l'exploration (architecture ROS-like).
    Reçoit l'état courant du robot, calcule la meilleure action suivante
    et la publie sur elio/command/explore_step.

    Algorithme : greedy sur cellules non visitées + tirage aléatoire
    pour briser les égalités. Mémoire illimitée côté serveur.
    """
    x       = step.get("x", 0)
    y       = step.get("y", 0)
    heading = step.get("heading", 0)
    front   = step.get("front", False)
    left    = step.get("left", False)
    right   = step.get("right", False)

    with _lock:
        if _state["mode"] != "exploration":
            return
        _state["visited"].add((x, y))
        visited = _state["visited"]

    blocked = {
        heading:           front,
        (heading + 1) % 4: right,
        (heading + 3) % 4: left,
    }

    candidates = []
    for abs_dir in range(4):
        rel = (abs_dir - heading) % 4
        if rel == 2:
            continue  # pas de demi-tour en premier passage
        if blocked.get(abs_dir, False):
            continue
        tx = x + _HDX[abs_dir]
        ty = y + _HDY[abs_dir]
        score = 0 if (tx, ty) in visited else 10
        candidates.append((score, rel))

    if not candidates:
        action = "uturn"
    else:
        best_score = max(c[0] for c in candidates)
        best_rels  = [c[1] for c in candidates if c[0] == best_score]
        rel        = random.choice(best_rels)
        action     = {0: "forward", 1: "turn_right", 3: "turn_left"}.get(rel, "uturn")

    print(f"[Exploration] ({x},{y}) h={heading} → {action} "
          f"(visités={len(visited)}, candidats={len(candidates)})")
    _publish("elio/command/explore_step", action)


def _on_message(client, userdata, msg):
    topic   = msg.topic
    payload = msg.payload.decode("utf-8", errors="replace")
    should_plan = False
    step        = None
    with _lock:
        _state["last_seen"] = datetime.now(timezone.utc).isoformat()
        try:
            if topic == "elio/telemetry/battery":
                _state["battery_v"] = float(payload)

            elif topic == "elio/telemetry/obstacles":
                _state["obstacles"] = json.loads(payload)

            elif topic == "elio/telemetry/mode":
                if payload in ("idle", "manual", "exploration"):
                    _state["mode"] = payload

            elif topic == "elio/telemetry/step":
                step = json.loads(payload)
                step["ts"] = datetime.now().strftime("%H:%M:%S")
                _state["steps"].append(step)
                should_plan = _state["mode"] == "exploration"

            elif topic == "elio/telemetry/eyes":
                data = json.loads(payload)
                if isinstance(data, dict):
                    _state["eyes"] = data

            elif topic == "elio/telemetry/lines":
                data = json.loads(payload)
                if isinstance(data, list) and len(data) == 5:
                    _state["lines"] = data

        except Exception as e:
            print(f"[MQTT] Erreur parsing {topic}: {e}")
            should_plan = False

    # Hors du lock : calcul + publication de la prochaine action
    if should_plan:
        _explore_next_step(step)


_mqttc.on_connect    = _on_connect
_mqttc.on_disconnect = _on_disconnect
_mqttc.on_message    = _on_message
_mqttc.reconnect_delay_set(min_delay=1, max_delay=15)


def _publish(topic: str, payload: str):
    try:
        _mqttc.publish(topic, payload, qos=0)
    except Exception as e:
        print(f"[MQTT] Erreur publish {topic}: {e}")


# ── WebSocket - gestionnaire de connexions ─────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self._connections.discard(ws) if hasattr(self._connections, 'discard') \
            else (self._connections.remove(ws) if ws in self._connections else None)

    async def broadcast(self, data: dict):
        dead = []
        for ws in list(self._connections):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self._connections:
                self._connections.remove(ws)

    @property
    def count(self) -> int:
        return len(self._connections)


manager = ConnectionManager()


# ── Broadcast loop (tâche asyncio) ────────────────────────────────────────────
async def _broadcast_loop():
    while True:
        await asyncio.sleep(0.3)
        if manager.count > 0:
            await manager.broadcast(_snapshot())


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    try:
        _mqttc.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=60)
        _mqttc.loop_start()
    except Exception as e:
        print(f"[MQTT] Connexion impossible au démarrage : {e}")

    task = asyncio.create_task(_broadcast_loop())

    yield

    # Shutdown
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    _mqttc.loop_stop()
    _mqttc.disconnect()


# ── App FastAPI ────────────────────────────────────────────────────────────────
app = FastAPI(title="Eliobot Dashboard", lifespan=lifespan)


# ── Endpoint santé ────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return JSONResponse({"status": "ok"})


# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    # Envoyer l'état initial immédiatement
    try:
        await ws.send_json(_snapshot())
    except Exception:
        manager.disconnect(ws)
        return
    try:
        while True:
            # Maintenir la connexion ouverte ; détecter la déconnexion du client
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect(ws)


# ── Modèles de commandes ──────────────────────────────────────────────────────
class ModeCmd(BaseModel):
    mode: str

class MoveCmd(BaseModel):
    direction: str

class SpeedCmd(BaseModel):
    speed: int

class MuteCmd(BaseModel):
    muted: bool


# ── Endpoints REST - commandes ────────────────────────────────────────────────
@app.post("/command/mode")
async def cmd_mode(cmd: ModeCmd):
    if cmd.mode in ("idle", "manual", "exploration"):
        _publish("elio/command/mode", cmd.mode)
    return {"ok": True}


@app.post("/command/move")
async def cmd_move(cmd: MoveCmd):
    if cmd.direction in ("forward", "backward", "left", "right", "stop"):
        _publish("elio/command/move", cmd.direction)
    return {"ok": True}


@app.post("/command/speed")
async def cmd_speed(cmd: SpeedCmd):
    if 0 <= cmd.speed <= 100:
        _publish("elio/command/speed", str(cmd.speed))
    return {"ok": True}


@app.post("/command/mute")
async def cmd_mute(cmd: MuteCmd):
    _publish("elio/command/mute", "1" if cmd.muted else "0")
    return {"ok": True}


@app.post("/command/buzzer")
async def cmd_buzzer():
    _publish("elio/command/buzzer", "1")
    return {"ok": True}


@app.post("/command/reset_map")
async def cmd_reset_map():
    with _lock:
        _state["steps"].clear()
        _state["visited"].clear()
    _publish("elio/command/reset_map", "1")
    return {"ok": True}


# ── Fichiers statiques & page principale ──────────────────────────────────────
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")
