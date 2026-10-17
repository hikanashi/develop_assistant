#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../backend"
pip install --no-cache-dir -e ".[dev]"
alembic upgrade head
python -m app.cli seed

cd ../web
if [ -f package.json ]; then
    npm install --no-audit --no-fund
fi
