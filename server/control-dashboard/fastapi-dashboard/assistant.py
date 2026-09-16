"""Chat ElioBot, historique par navigateur et orchestration des outils MCP."""
import asyncio
import contextlib
import json
import os
import re
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from assistant_config import ConfigStore
from assistant_providers import ModelConversation, ProviderError, check_response
from robot_mcp import RobotActions, build_mcp, local_mcp_client


class Assistant:
    def __init__(self, api, config=None):
        self.config = config or ConfigStore()
        self.actions = RobotActions(api)
        self.mcp = build_mcp(self.actions)
        self.mcp_app = self.mcp.streamable_http_app()
        self.router = APIRouter(prefix="/assistant")
        self.sessions = {}
        self.task = None
        self.active_session = None
        self.maintenance_lock = asyncio.Lock()
        self.model_job = {"status": "idle"}
        self.model_task = None
        self.register_routes()

    @property
    def busy(self):
        return self.task is not None and not self.task.done()

    def interrupt(self, stop_owned=False):
        self.actions.invalidate(stop_owned=stop_owned)
        if self.busy:
            self.task.cancel()

    async def close(self):
        self.interrupt(stop_owned=True)
        for task in (self.task, self.model_task):
            if task and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    async def body(self, request):
        try:
            raw = await request.body()
            if len(raw) > 16384:
                raise HTTPException(413, "Requête trop volumineuse.")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(422, "Requête JSON invalide.")

    def history(self, session):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{16,80}", session):
            raise HTTPException(422, "Identifiant de conversation invalide.")
        if session not in self.sessions:
            if len(self.sessions) >= 32:
                oldest = next((key for key in self.sessions if key != self.active_session), None)
                if oldest:
                    del self.sessions[oldest]
            self.sessions[session] = []
        return self.sessions[session]

    async def run(self, session, message, queue, generation):
        history = self.history(session)
        history.append({"role": "user", "text": message})
        del history[:-40]
        conversation = None
        completed_actions = []
        final = ""
        failure = {}
        provider = self.config.settings.provider
        def emit(kind, **data):
            queue.put_nowait({"type": kind, **data})
        def report_error(exc):
            nonlocal failure
            failure = {"code": getattr(exc, "code", "assistant_error"), "provider": provider}
            if failure["code"] == "quota_exceeded" and provider == "gemini":
                failure["suggested_provider"] = "ollama"
            emit("error", text=final, **failure)
        try:
            emit("status", text="Connexion au modèle…")
            async with local_mcp_client(self.mcp_app) as client:
                tools = (await client.list_tools()).tools
                allowed = {tool.name for tool in tools}
                context = [{"role": item["role"], "text": item["text"] + (
                    "\nRésultats déjà obtenus (ne pas rejouer) : " + json.dumps(item["actions"], ensure_ascii=False)
                    if item.get("actions") else "")} for item in history]
                conversation = ModelConversation(self.config.settings.model_copy(), self.config.api_key, context, tools)
                async with asyncio.timeout(180):
                    for _ in range(8):
                        self.actions.check(generation)
                        revision = self.actions.api._state["control"]["revision"]
                        text, calls = await conversation.next()
                        self.actions.check(generation)
                        if revision != self.actions.api._state["control"]["revision"]:
                            raise ProviderError("Le mode du robot a changé pendant la réponse. Demande annulée.")
                        if not calls:
                            final = text or "Je n’ai pas reçu de réponse exploitable. Reformule ta demande."
                            break
                        results = []
                        for call in calls:
                            self.actions.check(generation)
                            if call["name"] not in allowed:
                                raise ProviderError("Le modèle a demandé un outil inconnu. Aucune action supplémentaire exécutée.")
                            arguments = {**call["arguments"]}
                            arguments.pop("generation", None)
                            if "generation" in next(t.inputSchema.get("properties", {}) for t in tools if t.name == call["name"]):
                                arguments["generation"] = generation
                            emit("action", name=call["name"], arguments=call["arguments"], status="running")
                            result = await client.call_tool(call["name"], arguments)
                            payload = result.structuredContent
                            if payload is None:
                                raw = "\n".join(getattr(part, "text", "") for part in result.content)
                                try:
                                    payload = json.loads(raw)
                                    if not isinstance(payload, dict):
                                        payload = {"message": raw}
                                except ValueError:
                                    payload = {"message": raw}
                            payload = {**payload, "error": bool(result.isError)}
                            emit("action", name=call["name"], result=payload, status="error" if result.isError else "done")
                            completed_actions.append({"tool": call["name"], "result": payload})
                            results.append((call, payload))
                            # Un refus ne doit pas être contourné par un autre outil.
                            if result.isError:
                                final = "Action refusée : " + str(payload.get("message", "vérifier l’état du robot et les paramètres."))
                                break
                            if call["name"] == "stop_robot":
                                final = "Commande d’arrêt envoyée au robot."
                                break
                        if final:
                            break
                        conversation.results(results)
                        emit("status", text="Lecture du résultat…")
                    else:
                        final = "Limite d’actions atteinte pour ce message. Les actions déjà envoyées figurent ci-dessus."
        except asyncio.CancelledError:
            final = "Demande interrompue. Les commandes restantes ont été annulées."
        except (ProviderError, ValueError) as exc:
            final = str(exc)
            report_error(exc)
        except TimeoutError:
            final = "Délai de réponse dépassé. Les commandes restantes ont été annulées."
            self.actions.invalidate(stop_owned=True)
            report_error(None)
        except Exception as exc:
            # AnyIO regroupe aussi les erreurs applicatives levées dans une session MCP.
            errors = [exc]
            while any(isinstance(error, BaseExceptionGroup) for error in errors):
                errors = [child for error in errors for child in (error.exceptions if isinstance(error, BaseExceptionGroup) else [error])]
            known = next((error for error in errors if isinstance(error, (ProviderError, ValueError))), None)
            final = str(known) if known else "L’assistant a rencontré une erreur. Vérifier le moteur et réessayer."
            self.actions.invalidate(stop_owned=True)
            report_error(known)
        finally:
            if conversation:
                with contextlib.suppress(Exception):
                    await conversation.close()
            # Les résultats réels accompagnent le texte dans le contexte des messages suivants.
            record = {"role": "assistant", "text": final, "actions": completed_actions}
            if failure:
                record["error"] = failure
            history.append(record)
            emit("message", **record)
            emit("done")

    async def manager(self, method, path, body=None):
        token_path = Path(os.getenv("ELIO_MANAGER_TOKEN_FILE", "/run/elio/manager-token"))
        try:
            token = token_path.read_text().strip()
        except OSError:
            raise HTTPException(503, "Gestion locale indisponible. Relancer l’installation ElioBot ou connecter une instance Ollama existante.")
        try:
            async with httpx.AsyncClient(timeout=180, trust_env=False) as client:
                response = await client.request(method, os.getenv("ELIO_MANAGER_URL", "http://ollama-manager:8090") + path,
                                                headers={"Authorization": f"Bearer {token}"}, json=body)
            if response.is_error:
                detail = response.json().get("detail", "Opération Ollama impossible.")
                raise HTTPException(response.status_code, detail)
            return response.json()
        except httpx.HTTPError:
            raise HTTPException(503, "Le gestionnaire Ollama est indisponible. Vérifier Docker et l’installation du serveur.")

    async def model_operation(self, action, model):
        self.model_job = {"status": "running", "action": action, "model": model, "message": "Connexion à Ollama…"}
        try:
            url = self.config.settings.ollama_url
            async with httpx.AsyncClient(timeout=httpx.Timeout(900, connect=8), trust_env=False) as client:
                if action == "pull":
                    async with client.stream("POST", url + "/api/pull", json={"model": model, "stream": True}) as response:
                        check_response(response)
                        async for line in response.aiter_lines():
                            if not line:
                                continue
                            update = json.loads(line)
                            if "error" in update:
                                raise ProviderError("Téléchargement refusé par Ollama. Vérifier le nom du modèle et l’espace disque.")
                            self.model_job.update(message=update.get("status", "Téléchargement…"),
                                                  total=update.get("total"), completed=update.get("completed"))
                else:
                    response = await client.request("DELETE", url + "/api/delete", json={"model": model})
                    check_response(response)
            self.model_job.update(status="done", message="Modèle téléchargé." if action == "pull" else "Modèle supprimé.")
        except asyncio.CancelledError:
            self.model_job.update(status="error", message="Opération interrompue ; vérifier l’état des modèles dans Ollama.")
            raise
        except Exception:
            self.model_job.update(status="error", message="Opération impossible. Vérifier le nom, la connexion et l’espace disponible.")

    def register_routes(self):
        router = self.router

        @router.get("/config")
        async def get_config():
            return {**self.config.public(), "busy": self.busy,
                    "mcp": {"endpoint": "/mcp/", "external_enabled": bool(os.getenv("ELIO_MCP_TOKEN"))}}

        @router.post("/config")
        async def set_config(request: Request):
            values = await self.body(request)
            if self.busy or (self.model_task and not self.model_task.done()) or self.maintenance_lock.locked():
                raise HTTPException(409, "Attendre la fin de l’opération ou interrompre la demande avant de changer de moteur.")
            try:
                if not isinstance(values, dict):
                    raise ValueError()
                return self.config.update(values)
            except (ValidationError, ValueError, TypeError):
                raise HTTPException(422, "Configuration invalide. Vérifier les champs et l’adresse du moteur.")

        @router.get("/history/{session}")
        async def get_history(session: str):
            return {"messages": self.history(session), "busy": self.busy and self.active_session == session}

        @router.post("/switch-to-ollama")
        async def switch_to_ollama():
            if self.busy or (self.model_task and not self.model_task.done()) or self.maintenance_lock.locked():
                raise HTTPException(409, "Attendre la fin de l’opération avant de changer de moteur.")
            async with self.maintenance_lock:
                settings = self.config.settings
                if not settings.ollama_enabled:
                    raise HTTPException(409, "Ollama est déconnecté. Le reconnecter dans les réglages avant de basculer.")
                try:
                    # Vérifier le modèle sans inférence, téléchargement ou reprise de commande.
                    async with httpx.AsyncClient(timeout=8, trust_env=False, follow_redirects=False) as client:
                        response = await client.post(settings.ollama_url + "/api/show", json={"model": settings.ollama_model})
                    if response.status_code == 404:
                        raise HTTPException(409, "Le modèle Ollama choisi n’est pas installé. Le télécharger dans les réglages.")
                    check_response(response)
                    info = response.json()
                    capabilities = info.get("capabilities") if isinstance(info, dict) else None
                    if not isinstance(capabilities, list) or "tools" not in capabilities:
                        raise HTTPException(409, "Ce modèle Ollama ne déclare pas la prise en charge des actions. Choisir un modèle compatible dans les réglages.")
                    if info.get("remote_host") or info.get("remote_model"):
                        raise HTTPException(409, "Ce modèle Ollama utilise le cloud. Choisir un modèle téléchargé pour continuer en local.")
                except (httpx.HTTPError, ProviderError, ValueError):
                    raise HTTPException(503, "Ollama est indisponible. Le démarrer ou vérifier son adresse dans les réglages.")
                return {"config": self.config.update({"provider": "ollama"}),
                        "message": "Ollama est sélectionné. La conversation est conservée. Envoyez une nouvelle demande pour continuer ; les actions précédentes ne sont pas relancées."}

        @router.delete("/history/{session}")
        async def clear_history(session: str):
            if self.busy and self.active_session == session:
                raise HTTPException(409, "Interrompre la demande avant d’effacer la conversation.")
            self.history(session).clear()
            return {"ok": True}

        @router.post("/cancel")
        async def cancel():
            self.interrupt(stop_owned=True)
            return {"ok": True}

        @router.post("/chat")
        async def chat(request: Request):
            data = await self.body(request)
            if not isinstance(data, dict):
                raise HTTPException(422, "Message invalide.")
            session, message = data.get("session", ""), data.get("message", "")
            if not isinstance(session, str) or not isinstance(message, str) or not 1 <= len(message.strip()) <= 2000:
                raise HTTPException(422, "Le message doit contenir entre 1 et 2 000 caractères.")
            self.history(session)
            # Une commande d'arrêt explicite ne dépend jamais du modèle ou de son quota.
            if message.strip().lower().rstrip(".! ") in ("stop", "arrête", "arrete", "arrête-toi", "tout arrêter", "arrête le robot"):
                self.interrupt(stop_owned=True)
                await self.actions.api.stop()
                self.history(session).extend([{"role": "user", "text": message},
                                              {"role": "assistant", "text": "Commande d’arrêt envoyée au robot."}])
                return {"stopped": True, "text": "Commande d’arrêt envoyée au robot."}
            if self.busy or self.maintenance_lock.locked() or (self.model_task and not self.model_task.done()):
                raise HTTPException(409, "Une opération est déjà en cours. Attendre ou interrompre la demande.")
            if self.config.settings.provider == "gemini" and not self.config.api_key:
                raise HTTPException(409, "Configurer la clé Gemini ou choisir Ollama dans les réglages.")
            if self.config.settings.provider == "ollama" and not self.config.settings.ollama_enabled:
                raise HTTPException(409, "Ollama est déconnecté. Reconnecter une instance dans les réglages.")
            queue = asyncio.Queue()
            generation = self.actions.generation
            self.active_session = session
            task = self.task = asyncio.create_task(self.run(session, message.strip(), queue, generation))

            async def events():
                try:
                    while True:
                        try:
                            event = await asyncio.wait_for(queue.get(), 10)
                        except TimeoutError:
                            event = {"type": "ping"}
                        yield json.dumps(event, ensure_ascii=False) + "\n"
                        if event["type"] == "done":
                            break
                finally:
                    if not task.done():
                        self.interrupt(stop_owned=True)
                        with contextlib.suppress(asyncio.CancelledError):
                            await task
            return StreamingResponse(events(), media_type="application/x-ndjson", headers={"X-Accel-Buffering": "no"})

        @router.get("/models")
        async def models():
            settings = self.config.settings
            try:
                async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
                    if settings.provider == "gemini":
                        if not self.config.api_key:
                            raise ProviderError("Clé Gemini absente.")
                        response = await client.get("https://generativelanguage.googleapis.com/v1beta/models",
                                                    headers={"x-goog-api-key": self.config.api_key}, params={"pageSize": 1000})
                        check_response(response)
                        result = [{"name": model["name"].removeprefix("models/"), "label": model.get("displayName", model["name"])}
                                  for model in response.json().get("models", [])
                                  if "generateContent" in model.get("supportedGenerationMethods", [])]
                    else:
                        response = await client.get(settings.ollama_url + "/api/tags")
                        check_response(response)
                        result = [{"name": model["name"], "size": model.get("size", 0)} for model in response.json().get("models", [])]
                return {"models": result, "message": "Connexion établie. La disponibilité et les quotas seront vérifiés lors de l’utilisation."}
            except ProviderError as exc:
                raise HTTPException(503, str(exc))
            except (httpx.HTTPError, ValueError, KeyError):
                raise HTTPException(503, "Impossible de joindre le moteur ou de lire ses modèles.")

        @router.get("/installation")
        async def installation():
            try:
                info = await self.manager("GET", "/info")
            except HTTPException as exc:
                info = {"available": False, "message": exc.detail, "host": {"system": "unknown"}}
            return {**info, "model_job": self.model_job, "kind": self.config.settings.ollama_kind}

        @router.post("/ollama/{action}")
        async def manage(action: str, request: Request):
            if action not in ("start", "stop", "uninstall", "disconnect", "pull", "delete"):
                raise HTTPException(404, "Opération inconnue.")
            data = await self.body(request)
            if self.maintenance_lock.locked() or (self.model_task and not self.model_task.done()):
                raise HTTPException(409, "Une opération Ollama est déjà en cours.")
            if not isinstance(data, dict):
                raise HTTPException(422, "Paramètres invalides.")
            if action in ("delete", "uninstall") and data.get("confirm") is not True:
                raise HTTPException(422, "Confirmer la suppression dans l’interface.")
            if action in ("start", "stop", "uninstall") and self.config.settings.ollama_kind != "managed":
                raise HTTPException(409, "Cette installation n’est pas gérée par ElioBot. Utiliser la procédure de sa machine hôte.")
            async with self.maintenance_lock:
                self.interrupt(stop_owned=True)
                if self.task:
                    with contextlib.suppress(asyncio.CancelledError):
                        await self.task
                if action == "disconnect":
                    # Aucun basculement cloud implicite, aucune suppression de logiciel.
                    self.config.update({"ollama_enabled": False})
                    return {"ok": True, "message": "Instance déconnectée. Reconfigurer son adresse avant de l’utiliser."}
                if action in ("pull", "delete"):
                    model = data.get("model", "")
                    if not isinstance(model, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,150}", model) or ".." in model:
                        raise HTTPException(422, "Nom de modèle invalide.")
                    if self.config.settings.ollama_kind != "managed" and data.get("confirm_external") is not True:
                        raise HTTPException(422, "Confirmer la modification de cette instance Ollama externe.")
                    self.model_task = asyncio.create_task(self.model_operation(action, model))
                    return {"accepted": True}
                result = await self.manager("POST", "/" + action, {
                    "gpu": data.get("gpu", "cpu"), "erase_data": data.get("erase_data") is True,
                    "confirm": data.get("confirm") is True,
                })
                self.config.update({"ollama_enabled": action == "start"})
                return result
