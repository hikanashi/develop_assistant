#!/bin/sh
set -eu

if [ ! -f .env ]; then
    cp .env.example .env
    chmod 600 .env
fi

