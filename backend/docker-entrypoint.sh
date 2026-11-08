#!/bin/sh
set -eu
echo "Applying database migrations..."
alembic upgrade head
if [ "${SEED_DEMO:-false}" = "true" ]; then
  echo "Loading demo seed data..."
  python -m seeds.load_csv_sa
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
