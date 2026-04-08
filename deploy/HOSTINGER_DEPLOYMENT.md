# Hostinger VPS Deployment

## 1. Prepare the server

Use the copy-paste commands in [HOSTINGER_UBUNTU_COMMANDS.md](/D:/gigoptimizer-pro/deploy/HOSTINGER_UBUNTU_COMMANDS.md).

## 2. Fill production environment variables

```bash
cp .env.production.example .env.production
nano .env.production
```

Required values:

- `APP_DOMAIN`
- `SSL_EMAIL`
- `APP_SESSION_SECRET`
- `APP_ADMIN_PASSWORD_HASH`
- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `REDIS_URL`

Optional but recommended:

- `SENTRY_DSN`
- `BROWSERLESS_WS_URL`
- `BROWSERLESS_API_TOKEN`
- `AI_API_KEY`
- `SLACK_WEBHOOK_URL`
- `EMAIL_*`
- `WHATSAPP_*`

## 3. Start the stack

```bash
docker compose --env-file .env.production -f deploy/docker-compose.prod.yml build
docker compose --env-file .env.production -f deploy/docker-compose.prod.yml up -d postgres redis app worker scheduler nginx certbot
```

## 4. Issue SSL certificates

Point your DNS to the VPS first, then run:

```bash
docker compose --env-file .env.production -f deploy/docker-compose.prod.yml run --rm certbot certonly --webroot -w /var/www/certbot -d animha.co.in --email you@example.com --agree-tos --no-eff-email
docker compose --env-file .env.production -f deploy/docker-compose.prod.yml restart nginx
```

The nginx entrypoint automatically switches from the HTTP template to the HTTPS template once certificates are present.

## 5. Rolling restart command

```bash
bash deploy/restart-stack.sh
```

## 6. Health check

```bash
curl -fsSL https://animha.co.in/api/health
```

## 7. Worker commands

```bash
docker compose --env-file .env.production -f deploy/docker-compose.prod.yml logs -f worker
docker compose --env-file .env.production -f deploy/docker-compose.prod.yml logs -f scheduler
docker compose --env-file .env.production -f deploy/docker-compose.prod.yml ps
```
