#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMPOSE_FILE="${ROOT_DIR}/deploy/docker-compose.prod.yml"
ENV_FILE="${ROOT_DIR}/.env.production"
WORKFLOW_FILE="/imports/gigoptimizer-assistant-workflow.json"

cd "${ROOT_DIR}"

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" up -d n8n

attempt=0
until docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T n8n wget --spider -q http://127.0.0.1:5678/healthz >/dev/null 2>&1; do
  attempt=$((attempt + 1))
  if [ "${attempt}" -ge 30 ]; then
    docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" logs --tail=200 n8n
    exit 1
  fi
  sleep 5
done

docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" exec -T n8n n8n import:workflow --input="${WORKFLOW_FILE}"
docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" restart n8n
