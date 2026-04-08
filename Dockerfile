FROM node:24-alpine AS frontend-builder

WORKDIR /frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend ./
RUN npm run build


FROM mcr.microsoft.com/playwright/python:v1.52.0-noble

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY gigoptimizer ./gigoptimizer
COPY extensions ./extensions
COPY examples ./examples
COPY scripts ./scripts

RUN pip install --upgrade pip \
    && pip install .[live]

COPY --from=frontend-builder /frontend/dist ./frontend/dist

EXPOSE 8001

CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "--threads", "4", "-b", "0.0.0.0:8001", "--timeout", "120", "--graceful-timeout", "30", "gigoptimizer.api.main:app"]
