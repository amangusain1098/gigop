#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/deploy/docker-compose.prod.yml"
ENV_FILE="${ROOT_DIR}/.env.production"

cd "${ROOT_DIR}"

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" build app worker scheduler
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d postgres redis n8n

if docker ps --format '{{.Names}}' | grep -q '^traefik-'; then
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" rm -sf nginx certbot >/dev/null 2>&1 || true
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d app worker scheduler
else
  docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d app worker scheduler nginx certbot
fi

attempt=0
until docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T app python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/api/health', timeout=5).read()" >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "${attempt}" -ge 30 ]; then
    docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" logs --tail=200 app worker scheduler nginx
    exit 1
  fi
  sleep 5
done

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" ps
docker image prune -f
