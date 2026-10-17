#!/usr/bin/env bash
set -euo pipefail

# psql 用の接続情報を、.env 由来の環境変数から組み立てる (値はファイルに書き込まない)
if ! grep -q "# das-psql" ~/.bashrc 2>/dev/null; then
    cat >> ~/.bashrc <<'BASHRC'

# das-psql: .env の POSTGRES_* を psql 用の環境変数に反映する
export PGHOST="${POSTGRES_HOST:-db}" PGUSER="$POSTGRES_USER" PGPASSWORD="$POSTGRES_PASSWORD" PGDATABASE="$POSTGRES_DB"
BASHRC
fi

cd "$(dirname "$0")/../backend"
pip install --no-cache-dir -e ".[dev]"
alembic upgrade head
python -m app.cli seed

cd ../web
if [ -f package.json ]; then
    npm install --no-audit --no-fund
fi
