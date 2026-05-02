# Multi-stage Dockerfile
# Stage 1: build frontend
FROM node:18-alpine AS web-build
WORKDIR /src/web
COPY web/package*.json ./
COPY web/ ./
RUN npm install
RUN npm run build

# Stage 2: runtime image
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# System deps for building Python packages
RUN apt-get update \
  && apt-get install -y --no-install-recommends build-essential git curl ca-certificates \
  && rm -rf /var/lib/apt/lists/*

# Install pip and runtime Python packages
RUN pip install --upgrade pip setuptools wheel

# Install the 'uv' tool so we can run `uv sync` / `uv run` as requested
RUN pip install uv

# Copy python project files before syncing so the project itself is installed once in the image
COPY pyproject.toml ./
COPY uv.lock ./
COPY src/ ./src/
COPY config/ ./config/
COPY scripts/ ./scripts/
COPY README.md ./

# Sync dependencies during image build so runtime never downloads packages
RUN uv sync --frozen --no-dev

# Copy built frontend from the web build stage into expected location
RUN mkdir -p /app/web
COPY --from=web-build /src/web/dist /app/web/dist

EXPOSE 8000

# Run against the pre-synced environment without re-syncing at startup
CMD ["sh", "-c", "exec uv run --no-sync uvicorn src.main:app --host 0.0.0.0 --port 8000"]
