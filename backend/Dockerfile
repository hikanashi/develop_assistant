FROM python:3.13-slim-bookworm

WORKDIR /app

# 依存パッケージのみをインストールする。ソースは compose でマウントされ、editable install が参照する
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py \
    && pip install --no-cache-dir -e ".[dev]"

ENV PYTHONDONTWRITEBYTECODE=1
