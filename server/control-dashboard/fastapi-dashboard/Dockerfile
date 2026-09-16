FROM python:3.12-slim

WORKDIR /app

# Copier uv depuis son image officielle
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Installer les dépendances en premier (couche cachée)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
ENV PATH="/app/.venv/bin:$PATH"

# Copier le code source
COPY . .

EXPOSE 8000

HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
