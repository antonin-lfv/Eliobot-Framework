"""Gestion restreinte d'UNE instance Ollama, sans commande shell ni nom fourni par le client.

Seul ce service privé monte le socket Docker. Le dashboard n'y a jamais accès.
Les labels et l'identité persistante sont vérifiés avant toute modification.
"""
import asyncio
import hmac
import json
import os
import secrets
from pathlib import Path

import docker
from docker.errors import DockerException, NotFound
from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from typing import Literal

DATA = Path(os.getenv("MANAGER_DATA_DIR", "/run/elio"))
DATA.mkdir(parents=True, exist_ok=True, mode=0o700)
TOKEN_PATH = DATA / "manager-token"
if not TOKEN_PATH.exists():
    fd = os.open(TOKEN_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(secrets.token_urlsafe(32))
TOKEN = TOKEN_PATH.read_text().strip()
OWNER_PATH = DATA / "owner-id"
if not OWNER_PATH.exists():
    OWNER_PATH.write_text(secrets.token_hex(16))
OWNER = OWNER_PATH.read_text().strip()
LABEL = "fr.eliobot.ollama-owner"
NAME = "eliobot-ollama-" + OWNER[:12]
VOLUME = NAME + "-models"
IMAGE = "ollama/ollama:latest"


async def authorize(request: Request):
    if not hmac.compare_digest(request.headers.get("authorization", ""), "Bearer " + TOKEN):
        raise HTTPException(401, "Accès au gestionnaire refusé.")


app = FastAPI(title="Gestion locale Ollama", dependencies=[Depends(authorize)], docs_url=None, redoc_url=None)
lock = asyncio.Lock()


class Operation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gpu: Literal["cpu", "nvidia"] = "cpu"
    erase_data: bool = False
    confirm: bool = False


def owned(resource):
    labels = resource.attrs.get("Labels") or resource.attrs.get("Config", {}).get("Labels") or {}
    if labels.get(LABEL) != OWNER:
        raise HTTPException(409, "Cette ressource Docker n’appartient pas à ElioBot. Aucune modification effectuée.")
    return resource


def lookup(collection, name):
    try:
        return owned(collection.get(name))
    except NotFound:
        return None


def host_info():
    try:
        return json.loads((DATA / "host.json").read_text())
    except (OSError, ValueError):
        return {"system": "unknown", "message": "Exécuter setup.py sur la machine hôte pour identifier son système."}


def operate(action, operation=None):
    client = docker.from_env(timeout=150)
    try:
        container = lookup(client.containers, NAME)
        volume = lookup(client.volumes, VOLUME)
        if action == "info":
            engine = client.info()
            # La taille Docker est parfois indisponible ; ne pas annoncer zéro à sa place.
            size = None
            if volume:
                with_size = next((v for v in client.df().get("Volumes", []) if v["Name"] == VOLUME), {})
                measured = with_size.get("UsageData", {}).get("Size")
                size = measured if measured is not None and measured >= 0 else None
            return {"available": True, "host": host_info(), "status": container.status if container else "not_installed",
                    "managed": bool(container or volume), "data_bytes": size,
                    "docker_memory_bytes": engine.get("MemTotal"), "docker_architecture": engine.get("Architecture"),
                    "nvidia_available": "nvidia" in engine.get("Runtimes", {}),
                    "message": "Le service géré n’est accessible que sur le réseau interne ElioBot."}
        if action == "start":
            if container:
                container.start()
                return {"ok": True, "message": "Ollama démarré. Les réglages GPU existants sont conservés."}
            # Aucun montage de fichiers hôtes ni publication de ports.
            this_container = client.containers.get(os.environ["HOSTNAME"])
            networks = this_container.attrs["NetworkSettings"]["Networks"]
            network = next((name for name in networks if name.endswith("elio-net")), None)
            if not network:
                raise HTTPException(503, "Réseau ElioBot introuvable.")
            client.images.pull(IMAGE)
            if not volume:
                client.volumes.create(VOLUME, labels={LABEL: OWNER})
            gpu = [docker.types.DeviceRequest(count=-1, capabilities=[["gpu"]])] if operation.gpu == "nvidia" else []
            container = client.containers.create(IMAGE, name=NAME, detach=True, labels={LABEL: OWNER},
                volumes={VOLUME: {"bind": "/root/.ollama", "mode": "rw"}},
                environment={"OLLAMA_NUM_PARALLEL": "1", "OLLAMA_MAX_LOADED_MODELS": "1", "OLLAMA_NO_CLOUD": "1"},
                restart_policy={"Name": "unless-stopped"}, device_requests=gpu,
                network=network, networking_config=client.api.create_networking_config({
                    network: client.api.create_endpoint_config(aliases=["ollama"])}))
            container.start()
            return {"ok": True, "message": "Ollama installé et démarré. Télécharger ensuite un modèle."}
        if action == "stop":
            if container:
                container.stop(timeout=10)
            return {"ok": True, "message": "Ollama arrêté. Les modèles sont conservés."}
        if action == "uninstall":
            if not operation.confirm:
                raise HTTPException(422, "Confirmation requise.")
            if container:
                container.stop(timeout=10)
                container.remove()
            if operation.erase_data and volume:
                volume.remove()  # Sans force : refuser un volume encore utilisé ailleurs.
            return {"ok": True, "message": "Ollama désinstallé. " + (
                "Les modèles gérés ont été supprimés." if operation.erase_data else "Les modèles sont conservés pour une réinstallation.")}
        raise HTTPException(404, "Opération inconnue.")
    except DockerException as exc:
        # Ne pas exposer les informations internes du daemon Docker.
        raise HTTPException(503, "Opération Docker impossible. Vérifier le moteur, l’espace disque et les pilotes GPU.") from exc
    finally:
        client.close()


@app.get("/info")
async def info():
    return await asyncio.to_thread(operate, "info")


@app.post("/{action}")
async def manage(action: Literal["start", "stop", "uninstall"], operation: Operation):
    if lock.locked():
        raise HTTPException(409, "Une opération est déjà en cours.")
    async with lock:
        return await asyncio.to_thread(operate, action, operation)
