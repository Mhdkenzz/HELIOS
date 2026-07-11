FROM python:3.11-slim AS base
WORKDIR /app

FROM base AS deps
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -e ".[dev]"

FROM deps AS build-frontend
WORKDIR /app/web
COPY web/package.json web/package-lock.json* ./
RUN npm ci && npm run build

FROM base AS runtime
WORKDIR /app
COPY --from=build-frontend /app/web/dist ./helios/web
COPY --from=deps /app/helios ./helios
COPY --from=deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
ENV PATH="/usr/local/bin:${PATH}"
EXPOSE 6767
ENTRYPOINT ["python", "-m", "helios"]