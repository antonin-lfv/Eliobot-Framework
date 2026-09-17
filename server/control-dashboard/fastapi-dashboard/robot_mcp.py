"""Outils MCP du robot : les commandes réutilisent le contrôle du dashboard."""
import asyncio
import math
import time
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import httpx
from fastapi import HTTPException
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field


MAX_TURN_SECONDS = 30


class LiveAPI:
    def __init__(self, namespace):
        self.namespace = namespace

    def __getattr__(self, name):
        return self.namespace[name]


class RobotActions:
    def __init__(self, api):
        self.api = api
        self.generation = 0
        self.owned_revision = None
        self.moving = False

    def invalidate(self, stop_owned=False):
        """Synchrone : toute réponse tardive perd son droit d'agir avant le prochain await."""
        with self.api._lock:
            self.generation += 1
            if self.owned_revision == self.api._state["control"]["revision"]:
                if self.moving:
                    self.api._publish("elio/command/move", "stop")
                if stop_owned:
                    self.api._set_active("idle", reason="Action de l’assistant interrompue.")
            self.owned_revision = None
            self.moving = False

    def check(self, generation):
        if generation != self.generation:
            raise ValueError("Action périmée : le contrôle du robot a changé. Ne pas la rejouer.")

    async def state(self):
        snapshot = self.api._snapshot()
        snapshot.pop("steps", None)
        snapshot.pop("fly", None)
        with self.api._lock:
            snapshot["telemetry_age_seconds"] = round(time.monotonic() - self.api._state["last_seen_mono"], 1) if self.api._state["last_seen_mono"] else None
            snapshot["robot_online"] = bool(self.api._state["connected"] and
                time.monotonic() - self.api._state["last_seen_mono"] <= 3)
            snapshot["generation"] = self.generation
        return snapshot

    async def move(self, generation, direction, duration, speed):
        # Vérification aussi ici pour les appels internes et les valeurs non finies.
        if direction not in ("forward", "backward", "left", "right") or not 0.1 <= duration <= 3 or not 1 <= speed <= 70:
            raise ValueError("Mouvement limité à 0,1–3 secondes et une vitesse de 1–70 %.")
        return await self._run_movement(generation, direction, duration, speed)

    async def _run_movement(self, generation, direction, duration, speed):
        """Exécuter une durée déjà validée, avec les mêmes contrôles à chaque commande."""
        with self.api._lock:
            self.check(generation)
            if self.moving:
                raise ValueError("Un mouvement est déjà en cours.")
            try:
                self.api._manual_access()  # Conserve la confirmation de reprise depuis une autonomie.
            except HTTPException as exc:
                if isinstance(exc.detail, dict) and exc.detail.get("confirmation_required"):
                    raise ValueError("Une autonomie est en cours. Reprendre la main dans le dashboard avant de demander un déplacement.") from exc
                raise ValueError(str(exc.detail)) from exc
            revision = self.api._state["control"]["revision"]
            self.owned_revision = revision
            self.moving = True
        try:
            await self.api.cmd_speed(self.api.SpeedCmd(speed=speed))
            deadline = time.monotonic() + duration
            while time.monotonic() < deadline:
                with self.api._lock:
                    self.check(generation)
                    await self.api.cmd_move(self.api.MoveCmd(direction=direction, revision=revision))
                await asyncio.sleep(min(.15, max(0, deadline - time.monotonic())))
            return {"ok": True, "transmitted": True, "physical_completion_confirmed": False,
                    "message": "Commandes transmises pendant la durée demandée, puis arrêt envoyé.", "duration": duration}
        finally:
            with self.api._lock:
                # Un ancien finally ne doit jamais arrêter un nouveau pilote.
                if generation == self.generation:
                    self.moving = False
                    if self.api._state["control"]["revision"] == revision:
                        self.api._publish("elio/command/move", "stop")

    async def autonomy(self, generation, mode, action):
        with self.api._lock:
            self.check(generation)
            if self.moving:
                raise ValueError("Attendre la fin du mouvement avant de changer d’autonomie.")
            result = await self.api.autonomy(self.api.AutonomyCmd(mode=mode, action=action))
            self.owned_revision = self.api._state["control"]["revision"]
        return {**result, "message": "Commande transmise ; consulter l’état pour vérifier le mode observé."}

    async def turn(self, generation, direction, degrees, speed):
        if direction not in ("left", "right") or not 1 <= degrees <= 360 or not 15 <= speed <= 70:
            raise ValueError("Rotation de 1 à 360 degrés, à gauche ou à droite, à une vitesse de 15–70 %.")
        with self.api._lock:
            self.check(generation)
            battery = self.api._state["battery_v"]
            factor = self.api._state["status"].get("turn_factor")
        # Même estimation que Motors.repetition_per_second / l'exploration embarquée.
        # Les anciens firmwares ne transmettent pas encore le facteur de calibration.
        battery_source = "telemetry" if battery is not None else "nominal"
        factor_source = "robot_config" if factor is not None else "default"
        battery = 3.7 if battery is None else battery
        factor = 1.0 if factor is None else factor
        if (type(battery) not in (int, float) or not math.isfinite(battery) or not 2 <= battery <= 5
                or type(factor) not in (int, float) or not math.isfinite(factor) or not .1 <= factor <= 5):
            raise ValueError("Batterie ou calibration de rotation invalide. Vérifier les mesures du robot.")
        pwm = int(speed / 100 * 65535) / 65535
        rps = 20.3 * battery / 60 * pwm
        duration = degrees / (360 * rps) * (77.5 / 33.5) * factor
        if not .1 <= duration <= MAX_TURN_SECONDS:
            raise ValueError(f"La durée estimée de cette rotation ({duration:.1f} s) sort de la limite de 0,1–{MAX_TURN_SECONDS} secondes. Vérifier l’angle, la vitesse et la calibration.")
        result = await self._run_movement(generation, direction, duration, speed)
        return {**result, "requested_degrees": degrees, "direction": direction, "approximate": True,
                "duration": round(duration, 3), "turn_factor": factor, "calibration_source": factor_source,
                "battery_v": battery, "battery_source": battery_source,
                "message": "Commande de rotation approximative transmise, puis arrêt envoyé. L’angle réel n’est pas mesuré."}

    async def speed(self, generation, speed):
        with self.api._lock:
            self.check(generation)
            if not 0 <= speed <= 70:
                raise ValueError("La vitesse de l’assistant est limitée à 70 %.")
            self.api._require_robot()
            return await self.api.cmd_speed(self.api.SpeedCmd(speed=speed))

    async def stop(self):
        self.invalidate()
        return await self.api.stop()


def build_mcp(actions):
    mcp = FastMCP("ElioBot", instructions="Contrôle local d'ElioBot. Lire l'état avant d'agir.",
                  stateless_http=True, json_response=True, streamable_http_path="/",
                  transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))

    @mcp.tool()
    async def get_robot_state() -> dict:
        """Lire les dernières mesures, leur date, la connexion et la génération de contrôle."""
        return await actions.state()

    @mcp.tool()
    async def move_robot(generation: int, direction: Literal["forward", "backward", "left", "right"],
                         duration: Annotated[float, Field(ge=.1, le=3)],
                         speed: Annotated[int, Field(ge=1, le=70)] = 35) -> dict:
        """Déplacer brièvement le robot. Durée en secondes. Refuse de reprendre une autonomie en cours."""
        return await actions.move(generation, direction, duration, speed)

    @mcp.tool()
    async def turn_robot(generation: int, direction: Literal["left", "right"],
                         degrees: Annotated[float, Field(ge=1, le=360)],
                         speed: Annotated[int, Field(ge=15, le=70)] = 35) -> dict:
        """Tourner d'un angle APPROXIMATIF en degrés (ex. 70 à droite). Calcule la durée avec la batterie et le facteur du robot, sinon des valeurs nominales. Pas de mesure d'angle. Un tour complet correspond à 360 degrés. Durée calculée limitée à 30 secondes, commandes renouvelées toutes les 150 ms et arrêt interruptible. Refuse si une autonomie est en cours."""
        return await actions.turn(generation, direction, degrees, speed)

    @mcp.tool()
    async def set_robot_speed(generation: int, speed: Annotated[int, Field(ge=0, le=70)]) -> dict:
        """Régler la vitesse manuelle en pourcentage (maximum 70). Ne démarre aucun mouvement."""
        return await actions.speed(generation, speed)

    @mcp.tool()
    async def set_autonomy(generation: int, mode: Literal["exploration", "fly"], action: Literal["start", "pause"]) -> dict:
        """Démarrer ou suspendre l'exploration ou la mouche. La mouche doit être déjà chargée."""
        return await actions.autonomy(generation, mode, action)

    @mcp.tool()
    async def stop_robot() -> dict:
        """Arrêter le robot dans tous les modes et invalider les commandes antérieures."""
        return await actions.stop()

    return mcp


@asynccontextmanager
async def local_mcp_client(mcp_app):
    """Vrai protocole MCP via HTTP ASGI en mémoire, sans ouvrir de port supplémentaire."""
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mcp_app), timeout=MAX_TURN_SECONDS + 10) as http:
        async with streamable_http_client("http://elio.local/", http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
