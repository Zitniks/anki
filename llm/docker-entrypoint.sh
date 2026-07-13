#!/bin/sh
set -eu

cd /app
echo "Running alembic migrations..."
uv run alembic upgrade head

echo "Seeding admin/service account..."
uv run python scripts/seed_admin.py

cd /app/src
echo "Starting server..."
exec uv run python -O main.py
