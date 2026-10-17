FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app

WORKDIR /app
COPY design/requiments/enviroment.md /design/requiments/enviroment.md
COPY backend/ /app/
RUN pip install --no-cache-dir . \
    && python -c 'import os; from app.config import LOCALDATA_DIR; LOCALDATA_DIR.mkdir(parents=True, exist_ok=True); os.chown(LOCALDATA_DIR, 10001, 10001)'
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
