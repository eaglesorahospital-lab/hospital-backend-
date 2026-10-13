# ==============================================================================
# Celery Worker & Beat Containerfile (Phase 17 — Production Deployment)
# ==============================================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies for PostgreSQL client and build libraries
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend codebase
COPY . /app/

# Default command for celery worker (can be overridden in docker-compose.yml for beat)
CMD ["celery", "-A", "config", "worker", "--loglevel=info"]
