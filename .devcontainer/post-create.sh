#!/bin/sh
set -eu

cd /workspace/backend
python -m pip install --user -e '.[dev]'
python -m app.cli build-seed
python -m app.cli init-db

