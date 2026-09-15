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
import time
from typing import Literal

from fly_brain import FlyBrain
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
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
_lock = threading.RLock()
brain = FlyBrain(os.getenv("FLY_DATA_DIR", str(Path(__file__).parent.parent / "fly-data")))
_brain_load_task = None
_probe_task = None
DASHBOARD_PROTOCOL = 3
_state: dict = {
    "connected": False,
    "last_seen_mono": 0.0,
    "fly_observation": None, "fly_seen": 0.0,
    "fly_received": 0, "fly_sent": 0, "fly_expired": 0,
    "control": {"active": "idle", "paused": None, "revision": 0, "reason": None},
    "control_changed": 0.0,
    "last_seen": None,        # ISO string ou None
    "battery_v": None,
    "obstacles": {"front": False, "left": False, "right": False, "back": False},
    "mode": "idle",
    "steps": deque(maxlen=1000),
    "eyes":  {"pattern": "emotionConfused", "color": [50, 50, 50]},
    "lines":   [0, 0, 0, 0, 0],
    "status": {"line_threshold": 30000, "position_valid": True},
    "last_step_key": None,
    "last_command": None,
    "event_id": 0,
    "visited": set(),   # cellules explorées (x, y) - cerveau exploration
}


def _snapshot() -> dict:
    """Retourne une copie sérialisable de l'état courant."""
    with _lock:
        return {
            "protocol": DASHBOARD_PROTOCOL,
            "connected": _state["connected"],
            "last_seen": _state["last_seen"],
            "battery_v": _state["battery_v"],
            "obstacles": copy.copy(_state["obstacles"]),
            "mode":      _state["mode"],
            "steps":     list(_state["steps"]),
            "eyes":      copy.copy(_state["eyes"]),
            "lines":         list(_state["lines"]),
            "visited_count": len(_state["visited"]),
            "status": dict(_state["status"]),
            "control": dict(_state["control"]),
            "fly": brain.snapshot(),
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
            ("elio/telemetry/status",   0),
            ("elio/telemetry/fly_sensors", 0),
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
    pour briser les égalités. Les cellules visitées sont conservées côté serveur.
    """
    x       = step.get("x", 0)
    y       = step.get("y", 0)
    heading = step.get("heading", 0)
    front   = step.get("front", False)
    left    = step.get("left", False)
    right   = step.get("right", False)

    with _lock:
        if _state["mode"] != "exploration" or _state["control"]["active"] != "exploration":
            return
        _state["visited"].add((x, y))
        visited = set(_state["visited"])

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
    command = json.dumps({"session": step["session"], "step_id": step["step_id"],
                          "action": action})
    with _lock:
        if (_state["mode"] != "exploration" or _state["control"]["active"] != "exploration"
                or _state["last_step_key"] != (step["session"], step["step_id"])):
            return
        _state["last_command"] = command
    _publish("elio/command/explore_step", command)


def _on_message(client, userdata, msg):
    topic   = msg.topic
    payload = msg.payload.decode("utf-8", errors="replace")
    should_plan = False
    step        = None
    retry_command = None
    with _lock:
        _state["last_seen"] = datetime.now(timezone.utc).isoformat()
        _state["last_seen_mono"] = time.monotonic()
        try:
            if topic == "elio/telemetry/battery":
                _state["battery_v"] = float(payload)

            elif topic == "elio/telemetry/obstacles":
                _state["obstacles"] = json.loads(payload)

            elif topic == "elio/telemetry/mode":
                if payload in ("idle", "manual", "exploration", "fly"):
                    _state["mode"] = payload

            elif topic == "elio/telemetry/step":
                step = json.loads(payload)
                if (not isinstance(step, dict)
                        or not isinstance(step.get("session"), str)
                        or not step["session"]
                        or type(step.get("step_id")) is not int or step["step_id"] < 1
                        or any(type(step.get(k)) is not int for k in ("x", "y", "heading"))
                        or step["heading"] not in range(4)
                        or any(type(step.get(k)) is not bool for k in ("front", "left", "right"))):
                    raise ValueError("Étape invalide ou ancien protocole : mettre à jour le robot")
                key = (step["session"], step["step_id"])
                previous = _state["last_step_key"]
                if previous == key:
                    if _state["mode"] == "exploration":
                        retry_command = _state["last_command"]
                        should_plan = retry_command is None
                elif previous and previous[0] == key[0] and key[1] < previous[1]:
                    return  # Étape ancienne : ne pas rejouer une commande.
                else:
                    if previous and previous[0] != key[0]:
                        _state["steps"].clear()
                        _state["visited"].clear()
                    _state["event_id"] += 1
                    step["event_id"] = _state["event_id"]
                    step["ts"] = datetime.now().strftime("%H:%M:%S")
                    _state["steps"].append(step)
                    _state["last_step_key"] = key
                    _state["last_command"] = None
                    should_plan = _state["mode"] == "exploration"

            elif topic == "elio/telemetry/fly_sensors":
                observation = json.loads(payload)
                if (not isinstance(observation, dict)
                        or not isinstance(observation.get("session"), str)
                        or type(observation.get("frame")) is not int
                        or any(type(observation.get(k)) is not bool for k in ("left", "front", "right", "back"))):
                    raise ValueError("Observation mouche invalide")
                _state["fly_observation"] = observation
                _state["fly_seen"] = time.monotonic()
                _state["fly_received"] += 1

            elif topic == "elio/telemetry/status":
                data = json.loads(payload)
                if (isinstance(data, dict)
                        and type(data.get("line_threshold")) is int
                        and type(data.get("position_valid")) is bool):
                    fault = data.get("last_error")
                    if isinstance(fault, dict) and fault != _state["status"].get("last_error"):
                        print(f"[Robot] Erreur embarquée : {json.dumps(fault, ensure_ascii=False)}", flush=True)
                    _state["status"] = data

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
    if retry_command is not None:
        _publish("elio/command/explore_step", retry_command)
    elif should_plan:
        _explore_next_step(step)


_mqttc.on_connect    = _on_connect
_mqttc.on_disconnect = _on_disconnect
_mqttc.on_message    = _on_message
_mqttc.reconnect_delay_set(min_delay=1, max_delay=15)


def _publish(topic: str, payload: str):
    try:
        result = _mqttc.publish(topic, payload, qos=0)
        return result.rc == mqtt.MQTT_ERR_SUCCESS
    except Exception as e:
        print(f"[MQTT] Erreur publish {topic}: {e}")
        return False


# ── Arbitrage des commandes et calcul neuronal ────────────────────────────────
def _require_robot():
    if not _state["connected"] or time.monotonic() - _state["last_seen_mono"] > 3:
        raise HTTPException(503, "Le robot doit être connecté pour démarrer un mouvement.")


def _set_active(mode, paused=None, reason=None):
    # Appelé sous _lock : mode puis commandes partent dans le même ordre MQTT.
    if reason and paused == "fly":
        observation = _state["fly_observation"]
        age = f"{time.monotonic() - _state['fly_seen']:.3f}s" if observation else "aucune"
        print(f"[Mouche] Pause : {reason} | observations={_state['fly_received']} "
              f"réponses={_state['fly_sent']} calculs_périmés={_state['fly_expired']} "
              f"dernière_trame={observation.get('frame') if observation else None} "
              f"âge={age}", flush=True)
    _state["control"] = {"active": mode, "paused": paused,
                         "revision": _state["control"]["revision"] + 1, "reason": reason}
    _state["control_changed"] = time.monotonic()
    _state["last_command"] = None
    _state["fly_observation"] = None
    if mode == "fly":
        _state["fly_seen"] = 0.0
        _state["fly_received"] = _state["fly_sent"] = _state["fly_expired"] = 0
    if not _publish("elio/command/mode", mode):
        _state["control"]["active"] = "idle"
        _state["control"]["reason"] = "La commande n’a pas pu être transmise."
        if mode != "idle":
            raise HTTPException(503, "Broker indisponible ; le mouvement n’a pas été lancé.")


def _manual_access():
    _require_robot()
    control = _state["control"]
    active = control["active"]
    # Vérifier aussi le mode observé pour les commandes émises hors du dashboard.
    autonomous = active if active in ("exploration", "fly") else _state["mode"]
    if autonomous in ("exploration", "fly") and active != "manual":
        raise HTTPException(409, {"confirmation_required": True, "active": autonomous,
                                  "revision": control["revision"]})
    if active != "manual":
        _set_active("manual", paused=control["paused"])


async def _control_loop():
    consumed = None
    while True:
        await asyncio.sleep(.04)
        with _lock:
            active = _state["control"]["active"]
            if active == "idle":
                consumed = None
                continue
            now = time.monotonic()
            if (not _state["connected"] or now - _state["last_seen_mono"] > 3
                    or (now - _state["control_changed"] > 2 and _state["mode"] != active)):
                _set_active("idle", paused=active if active in ("fly", "exploration") else None,
                            reason="Commande interrompue : connexion ou mode du robot non confirmé.")
                continue
            if active != "fly" or _state["mode"] != "fly":
                continue
            observation = _state["fly_observation"]
            revision = _state["control"]["revision"]
            seen = _state["fly_seen"]
            if not observation or now - seen > .6:
                if now - _state["control_changed"] > 2 and (not observation or now - seen > 1.5):
                    reason = ("Le robot confirme le mode mouche, mais aucune observation n’est reçue. "
                              "Vérifier la version du programme mqtt_dashboard sur le robot."
                              if not observation else
                              f"Flux des capteurs mouche interrompu depuis {now - seen:.1f} s "
                              f"(dernière trame : {observation['frame']}).")
                    _set_active("idle", paused="fly", reason=reason)
                continue
            key = (revision, observation["session"], observation["frame"])
            if key == consumed:
                continue
            consumed = key
        try:
            result = await asyncio.to_thread(brain.tick, observation)
            with _lock:
                # Une pause/reprise pendant le calcul invalide son résultat moteur.
                if (_state["control"]["active"] != "fly"
                        or _state["control"]["revision"] != revision):
                    continue
                if time.monotonic() - seen > .55:
                    _state["fly_expired"] += 1
                    continue
                command = {"session": observation["session"], "frame": observation["frame"],
                           "left": result["left"], "right": result["right"]}
                if not _publish("elio/command/fly_drive", json.dumps(command)):
                    _set_active("idle", paused="fly", reason="Transmission des roues interrompue.")
                else:
                    _state["fly_sent"] += 1
        except Exception as exc:
            with _lock:
                if _state["control"]["revision"] == revision:
                    _set_active("idle", paused="fly", reason=str(exc))


# ── WebSocket - gestionnaire de connexions ─────────────────────────────────────
def _state_delta(previous: dict, current: dict) -> dict:
    """Champs modifiés et nouvelles étapes ; remplacement lors d'un reset."""
    changed = {key: value for key, value in current.items()
               if key != "steps" and previous.get(key) != value}
    delta = {"type": "delta", "state": changed}
    old_steps, new_steps = previous.get("steps", []), current["steps"]
    if old_steps != new_steps:
        last_id = old_steps[-1]["event_id"] if old_steps else None
        ids = [step["event_id"] for step in new_steps]
        if not old_steps:
            delta["steps_append"] = new_steps
        elif last_id in ids:
            delta["steps_append"] = new_steps[ids.index(last_id) + 1:]
        else:
            changed["steps"] = new_steps
    return delta


class ConnectionManager:
    def __init__(self):
        self._connections: dict[WebSocket, dict] = {}

    async def connect(self, ws: WebSocket):
        await ws.accept()
        initial = _snapshot()
        # Inscrire la connexion après le snapshot pour éviter deux envois concurrents.
        await ws.send_json({"type": "snapshot", "state": initial})
        self._connections[ws] = initial

    def disconnect(self, ws: WebSocket):
        self._connections.pop(ws, None)

    async def broadcast(self, data: dict):
        for ws, previous in list(self._connections.items()):
            delta = _state_delta(previous, data)
            if not delta["state"] and "steps_append" not in delta:
                continue
            try:
                await asyncio.wait_for(ws.send_json(delta), timeout=1.0)
                if ws in self._connections:
                    self._connections[ws] = data
            except Exception:
                self.disconnect(ws)

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
    control_task = asyncio.create_task(_control_loop())

    yield

    # Shutdown
    with _lock:
        _set_active("idle", reason="Serveur arrêté.")
    control_task.cancel()
    try:
        await control_task
    except asyncio.CancelledError:
        pass
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    _mqttc.loop_stop()
    _mqttc.disconnect()


# ── App FastAPI ────────────────────────────────────────────────────────────────
app = FastAPI(title="Eliobot Dashboard", lifespan=lifespan)


@app.middleware("http")
async def fresh_interface(request, call_next):
    response = await call_next(request)
    # Les commandes et la page doivent provenir de la même version du serveur.
    response.headers['Cache-Control'] = 'no-store'
    return response


# ── Endpoint santé ────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    return JSONResponse({"status": "ok", "protocol": DASHBOARD_PROTOCOL})


# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    try:
        await manager.connect(ws)
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


# ── Commandes explicites, sans sélecteur de mode ──────────────────────────────
class ModeCmd(BaseModel):
    mode: Literal["idle", "manual", "exploration", "fly"]

class MoveCmd(BaseModel):
    direction: Literal["forward", "backward", "left", "right", "stop"]
    revision: int | None = None

class SpeedCmd(BaseModel):
    speed: int

class MuteCmd(BaseModel):
    muted: bool

class AutonomyCmd(BaseModel):
    mode: Literal["exploration", "fly"]
    action: Literal["start", "pause"]

class TakeoverCmd(BaseModel):
    revision: int

class ProbeCmd(BaseModel):
    stimulus: Literal["left", "front", "right"]


@app.post("/command/fly/probe")
async def probe_fly(cmd: ProbeCmd):
    global _probe_task
    with _lock:
        if brain.snapshot()['status'] != 'ready':
            raise HTTPException(409, "Charger le connectome avant une stimulation.")
        if _state['control']['active'] == 'fly':
            raise HTTPException(409, "Mettre la mouche en pause avant de tester une stimulation.")
        if _probe_task is not None and not _probe_task.done():
            raise HTTPException(409, "Une stimulation est déjà en cours de calcul.")
        sensors = {key: key == cmd.stimulus for key in ('left', 'right', 'front', 'back')}
        _probe_task = asyncio.create_task(asyncio.to_thread(brain.probe, sensors))
    try:
        frames = await asyncio.shield(_probe_task)
    except Exception as exc:
        raise HTTPException(503, f"Calcul de stimulation impossible : {exc}") from exc
    return {"source": "simulation", "stimulus": cmd.stimulus, "frames": frames}


@app.post("/command/fly/load", status_code=202)
async def load_fly():
    global _brain_load_task
    if _brain_load_task is None or _brain_load_task.done():
        _brain_load_task = asyncio.create_task(asyncio.to_thread(brain.load))
    return {"ok": True}


@app.post("/command/fly/reset")
async def reset_fly():
    with _lock:
        if _state["control"]["active"] == "fly":
            raise HTTPException(409, "Mettre la mouche en pause avant de réinitialiser son activité.")
        brain.state = {**brain.state, "status": "resetting"}
    await asyncio.to_thread(brain.reset)
    return {"ok": True}


@app.post("/command/autonomy")
async def autonomy(cmd: AutonomyCmd):
    with _lock:
        if cmd.action == "pause":
            if _state["control"]["active"] == cmd.mode:
                _set_active("idle", paused=cmd.mode)
            return {"ok": True}
        _require_robot()
        if cmd.mode == "fly":
            if _probe_task is not None and not _probe_task.done():
                raise HTTPException(409, "Attendre la fin du calcul de stimulation avant de lancer le robot.")
            if brain.snapshot()["status"] != "ready":
                raise HTTPException(409, "Charger le connectome avant de lancer la mouche.")
            if _state["status"].get("protocol", 0) < 2:
                raise HTTPException(409, "Mettre à jour le programme mqtt_dashboard du robot pour utiliser la mouche.")
        if _state["control"]["active"] != cmd.mode:
            _set_active(cmd.mode)
    return {"ok": True}


@app.post("/command/takeover")
async def takeover(cmd: TakeoverCmd):
    with _lock:
        _require_robot()
        control = _state["control"]
        if cmd.revision != control["revision"]:
            raise HTTPException(409, "Le pilotage a changé. Recommencer la demande de reprise manuelle.")
        active = control["active"]
        paused = active if active in ("exploration", "fly") else control["paused"]
        _set_active("manual", paused=paused)
    # La confirmation seule n'entraîne aucun déplacement : maintenir ensuite une direction.
    return {"ok": True}


@app.post("/command/stop")
async def stop():
    with _lock:
        active = _state["control"]["active"]
        _set_active("idle", paused=active if active in ("exploration", "fly") else _state["control"]["paused"])
    return {"ok": True}


@app.post("/command/mode")
async def cmd_mode(cmd: ModeCmd):
    # Compatibilité API ; la reprise manuelle ne contourne pas la confirmation.
    if cmd.mode in ("exploration", "fly"):
        return await autonomy(AutonomyCmd(mode=cmd.mode, action="start"))
    if cmd.mode == "idle":
        return await stop()
    with _lock:
        _manual_access()
    return {"ok": True}


@app.post("/command/move")
async def cmd_move(cmd: MoveCmd):
    with _lock:
        if cmd.revision is not None and cmd.revision != _state["control"]["revision"]:
            raise HTTPException(409, "Le pilotage a changé ; cette commande est périmée.")
        if cmd.direction != "stop":
            _manual_access()
        elif _state["control"]["active"] != "manual":
            return {"ok": True}  # Un relâchement ancien ne coupe pas une nouvelle autonomie.
        if not _publish("elio/command/move", cmd.direction):
            raise HTTPException(503, "La commande de mouvement n’a pas pu être transmise.")
        return {"ok": True, "revision": _state["control"]["revision"]}


@app.post("/command/speed")
async def cmd_speed(cmd: SpeedCmd):
    if not 0 <= cmd.speed <= 100:
        raise HTTPException(422, "La vitesse doit être comprise entre 0 et 100.")
    if not _publish("elio/command/speed", str(cmd.speed)):
        raise HTTPException(503, "Broker indisponible.")
    return {"ok": True}


@app.post("/command/mute")
async def cmd_mute(cmd: MuteCmd):
    if not _publish("elio/command/mute", "1" if cmd.muted else "0"):
        raise HTTPException(503, "Broker indisponible.")
    return {"ok": True}


@app.post("/command/buzzer")
async def cmd_buzzer():
    if not _publish("elio/command/buzzer", "1"):
        raise HTTPException(503, "Broker indisponible.")
    return {"ok": True}


@app.post("/command/reset_map")
async def cmd_reset_map():
    with _lock:
        _set_active("idle")
        if not _publish("elio/command/reset_map", "1"):
            raise HTTPException(503, "La carte du robot n’a pas pu être réinitialisée.")
        _state["steps"].clear()
        _state["visited"].clear()
    return {"ok": True}


# ── Fichiers statiques & page principale ──────────────────────────────────────
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8").replace('__PAGE__', 'control')


@app.get("/fly", response_class=HTMLResponse)
async def fly_page():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8").replace('__PAGE__', 'fly').replace(
        '<title>Elio — Console de contrôle</title>', '<title>Elio — Laboratoire mouche</title>')
