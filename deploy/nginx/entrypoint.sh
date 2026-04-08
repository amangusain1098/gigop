#!/bin/sh
set -eu

CERT_DIR="/etc/letsencrypt/live/${APP_DOMAIN}"
TARGET="/etc/nginx/conf.d/default.conf"

if [ -f "${CERT_DIR}/fullchain.pem" ] && [ -f "${CERT_DIR}/privkey.pem" ]; then
  envsubst '${APP_DOMAIN}' < /etc/nginx/custom-templates/app.https.conf.template > "${TARGET}"
else
  envsubst '${APP_DOMAIN}' < /etc/nginx/custom-templates/app.http.conf.template > "${TARGET}"
fi

exec nginx -g 'daemon off;'
