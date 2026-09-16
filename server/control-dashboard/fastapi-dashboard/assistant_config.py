"""Configuration privée de l'assistant ; aucun secret dans les réponses HTTP."""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: Literal["gemini", "ollama"] = "gemini"
    gemini_model: str = Field(default="gemini-3.1-flash-lite", pattern=r"^[a-zA-Z0-9._-]{1,100}$")
    ollama_model: str = Field(default="qwen3:4b", pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:/-]{0,150}$")
    ollama_url: str = "http://ollama:11434"
    ollama_kind: Literal["managed", "native", "remote"] = "managed"
    ollama_enabled: bool = True
    gemini_key: str = Field(default="", max_length=256, repr=False)

    @field_validator("ollama_url")
    @classmethod
    def valid_url(cls, value):
        parts = urlsplit(value.strip())
        if (parts.scheme not in ("http", "https") or not parts.hostname or parts.username
                or parts.password or parts.query or parts.fragment or parts.path not in ("", "/")):
            raise ValueError("Indiquer une adresse HTTP(S) sans identifiants ni chemin.")
        # L'adresse appartient à l'administrateur, jamais au modèle.
        _ = parts.port
        return value.strip().rstrip("/")


class ConfigStore:
    def __init__(self, directory=None):
        self.directory = Path(directory or os.getenv("ASSISTANT_DATA_DIR", str(
            Path(__file__).resolve().parent.parent / "assistant-data")))
        self.path = self.directory / "settings.json"
        self.settings = Settings()
        if self.path.exists():
            self.settings = Settings.model_validate_json(self.path.read_text())

    @property
    def api_key(self):
        return self.settings.gemini_key or os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")

    def public(self):
        result = self.settings.model_dump(exclude={"gemini_key"})
        result["gemini_key_configured"] = bool(self.api_key)
        result["gemini_key_source"] = "configuration" if self.settings.gemini_key else "environnement" if self.api_key else None
        result["configured"] = self.path.exists()
        return result

    def update(self, values):
        settings = Settings.model_validate({**self.settings.model_dump(), **values})
        if settings.ollama_kind == "managed":
            settings.ollama_url = "http://ollama:11434"
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix(".tmp")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(settings.model_dump_json(indent=2))
        temporary.replace(self.path)
        self.settings = settings
        return self.public()
