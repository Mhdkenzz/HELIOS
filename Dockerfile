FROM python:3.11-slim AS base
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    git inotify-tools curl gnupg \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y nodejs \
 && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]"
COPY . .
RUN cd web && npm install && npm run build
EXPOSE 6767
CMD ["uvicorn", "helios.cli:app", "--host", "0.0.0.0", "--port", "6767"]