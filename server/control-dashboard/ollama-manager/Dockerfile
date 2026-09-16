FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.115,<1" "uvicorn>=0.30,<1" "docker>=7,<8"
COPY manager.py .
CMD ["uvicorn", "manager:app", "--host", "0.0.0.0", "--port", "8090"]
