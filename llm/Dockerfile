FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./

RUN pip install -U pip
RUN pip install uv
# uv.lock pins exact (CUDA-enabled) torch/nvidia-* wheel hashes, so this pulls
# several GB regardless of backend flags — that's inherent to the current
# lockfile (sentence-transformers + faster-whisper depend on torch), not
# something a Dockerfile-only change can avoid without re-resolving the lock.
# The default per-request timeout (30s) is too short for wheels this size on
# a slow link, so extend it rather than have one slow file kill the build.
ENV UV_HTTP_TIMEOUT=180
RUN uv sync

COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini ./
COPY scripts/ ./scripts/
COPY docker-entrypoint.sh ./
RUN chmod +x ./docker-entrypoint.sh

WORKDIR /app/src

# Run migrations, seed the service account, then start the app
ENTRYPOINT ["/app/docker-entrypoint.sh"]