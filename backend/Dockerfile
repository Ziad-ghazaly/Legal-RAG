FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl build-essential libpq-dev \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 fonts-noto-core \
    && rm -rf /var/lib/apt/lists/*

COPY backend/pyproject.toml /app/pyproject.toml
RUN pip install --upgrade pip && pip install ".[dev]"

COPY backend/app /app/app
COPY backend/workers /app/workers
COPY backend/tests /app/tests
COPY backend/alembic.ini /app/alembic.ini

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
