FROM python:3.11-slim AS base
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git inotify-tools && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"
COPY . .
EXPOSE 6767 5173
CMD ["bash", "-c", "cd web && npm run dev & uvicorn helios.cli:app --reload --host 0.0.0.0 --port 6767"]