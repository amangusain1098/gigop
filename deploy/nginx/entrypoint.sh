#!/bin/sh
set -eu

CERT_DIR="/etc/letsencrypt/live/${APP_DOMAIN}"
TARGET="/etc/nginx/templates/default.conf.template"

if [ -f "${CERT_DIR}/fullchain.pem" ] && [ -f "${CERT_DIR}/privkey.pem" ]; then
  cp /etc/nginx/custom-templates/app.https.conf.template "${TARGET}"
else
  cp /etc/nginx/custom-templates/app.http.conf.template "${TARGET}"
fi

exec /docker-entrypoint.sh nginx -g 'daemon off;'
