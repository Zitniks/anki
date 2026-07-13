#!/bin/sh
set -eu

echo "Running goose migrations..."
./goose -dir ./migrations postgres "$DATABASE_URL" up

echo "Starting server..."
exec ./server
