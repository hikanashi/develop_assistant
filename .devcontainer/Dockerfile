FROM python:3.13-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/home/vscode/.local/bin:$PATH

RUN apt-get update \
    && apt-get install --no-install-recommends -y git build-essential libpq-dev postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 vscode \
    && useradd --uid 1000 --gid vscode --create-home --shell /bin/bash vscode \
    && install -d -o vscode -g vscode /workspace

WORKDIR /workspace
USER vscode
