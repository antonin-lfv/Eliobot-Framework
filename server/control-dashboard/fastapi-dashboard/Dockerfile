FROM python:3.12-slim

WORKDIR /app

# Copier uv depuis son image officielle
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Installer les dépendances en premier (couche cachée)
COPY pyproject.toml ./
RUN uv pip install --system \
    "fastapi>=0.111.0" \
    "uvicorn[standard]>=0.29.0" \
    "paho-mqtt>=2.1.0" \
    "aiofiles>=23.0.0"

# Copier le code source
COPY . .

EXPOSE 8000

HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
