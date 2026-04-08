# GigOptimizer Pro

GigOptimizer Pro is a standalone MVP for the Fiverr gig optimization system you described for the WordPress Insights and Page Speed niche.

It is intentionally honest about scope:

- It implements the seven agent layers as deterministic Python modules.
- It turns a gig snapshot into a structured optimization report.
- It includes a local FastAPI dashboard with live browser updates over WebSocket.
- It now includes a React + Vite blueprint dashboard at `/dashboard`.
- It keeps the previous HTML dashboard available at `/dashboard-legacy`.
- It includes a HITL approval queue, weekly report export, and scheduled Sunday runs.
- It supports hosted-dashboard authentication with signed session cookies.
- It includes protected Slack and WhatsApp notification settings with test actions.
- It now supports SMTP email alerts, installable mobile PWA access, public Fiverr competitor scraping, and an optional low-cost AI operations overview.
- It now includes a SQLAlchemy-backed persistence layer, a Redis/RQ-ready job abstraction, deep health checks, and Browserless-ready scraping config.
- It does not pretend to scrape Fiverr or bypass platform rules out of the box.
- It is designed so live connectors can be added later for approved APIs, browser automation, and scheduled jobs.

## What It Does

Given a JSON snapshot of your Fiverr gig, competitors, analytics, reviews, and buyer messages, the system will:

- analyze keyword coverage and competitor gaps
- segment likely buyer personas
- generate title variants and content recommendations
- audit conversion metrics
- compare your pricing with competitor benchmarks
- extract social-proof language from reviews
- suggest external traffic plays and weekly action priorities
- optionally enrich the run with Google Trends, SEMrush, and Fiverr seller metrics connectors

## Architecture

The code mirrors the seven-layer architecture:

1. `BuyerIntelligenceAgent`
2. `GigContentOptimizerAgent`
3. `PersonaSegmentationAgent`
4. `CROAgent`
5. `PricingIntelligenceAgent`
6. `ReviewSocialProofAgent`
7. `ExternalTrafficAgent`

`GigOptimizerOrchestrator` runs all seven and returns one consolidated report.

## Blueprint Architecture

The app now supports the production-style split described in the blueprint:

- Browser frontend: React + Vite + WebSocket on `/dashboard`
- Legacy frontend: server-rendered dashboard on `/dashboard-legacy`
- Optional browser extension import endpoint on `/api/extension/import`
- Application server: FastAPI
- Persistence: SQLAlchemy with PostgreSQL-ready `DATABASE_URL`
- Jobs: Redis/RQ-ready queue abstraction with local thread fallback on Windows/dev
- Reports and market watch: background job entry points plus scheduled execution hooks
- Reverse proxy deployment: Nginx + Certbot in Docker Compose

On Windows and local development, the queue runs in a background-thread compatibility mode because RQ is intended for the Linux production host.

## Project Layout

```text
D:\gigoptimizer-pro
  gigoptimizer/
    agents/
    cli.py
    models.py
    orchestrator.py
  examples/
    wordpress_speed_snapshot.json
  tests/
    test_orchestrator.py
  README.md
  pyproject.toml
```

## Quick Start

From `D:\gigoptimizer-pro`:

```powershell
pip install -e .
python -m unittest discover -s tests -v
python -m gigoptimizer.cli --input examples\wordpress_speed_snapshot.json
```

To enable live connectors:

```powershell
pip install -e .[live]
playwright install chromium
copy .env.example .env
python -m gigoptimizer.cli --show-connector-status --input examples\wordpress_speed_snapshot.json
python -m gigoptimizer.cli --input examples\wordpress_speed_snapshot.json --use-live-connectors
```

## Blueprint Dashboard

Build the React dashboard:

```powershell
cd D:\gigoptimizer-pro\frontend
npm install
npm run build
```

The Vite build now uses chunk splitting for `react-core`, `charts`, and `vendor`, so the blueprint dashboard no longer ships as one oversized production bundle.

Run the backend:

```powershell
cd D:\gigoptimizer-pro
python -m gigoptimizer.api.main
```

Open:

- `http://127.0.0.1:8001/dashboard`
- `http://127.0.0.1:8001/dashboard-legacy`

## Deployment

Production deployment files now live in:

- [Dockerfile](/D:/gigoptimizer-pro/Dockerfile)
- [docker-compose.prod.yml](/D:/gigoptimizer-pro/deploy/docker-compose.prod.yml)
- [HOSTINGER_DEPLOYMENT.md](/D:/gigoptimizer-pro/deploy/HOSTINGER_DEPLOYMENT.md)
- [HOSTINGER_UBUNTU_COMMANDS.md](/D:/gigoptimizer-pro/deploy/HOSTINGER_UBUNTU_COMMANDS.md)
- [UPTIME_MONITORING.md](/D:/gigoptimizer-pro/deploy/UPTIME_MONITORING.md)
- [deploy-hostinger.yml](/D:/gigoptimizer-pro/.github/workflows/deploy-hostinger.yml)

Optional free-tier discovery fallback:

```powershell
SERPAPI_API_KEY=your-serpapi-key
SERPAPI_ENGINE=google
SERPAPI_NUM_RESULTS=10
```

SerpApi's official free plan currently advertises `250 searches / month`, which is enough for low-volume Fiverr market discovery.

The marketplace settings panel also supports a no-key reader fallback:

```powershell
MARKETPLACE_READER_ENABLED=true
MARKETPLACE_READER_BASE_URL=https://r.jina.ai/http://
```

That free reader path is now used as the first public-page fallback for Fiverr gig URLs and search-result comparisons, so the app can still build optimization recommendations even when Fiverr serves an anti-bot challenge to normal HTTP requests.

You can also install it as an editable package later:

```powershell
pip install -e .
gigoptimizer --input examples\wordpress_speed_snapshot.json
```

## Browser Dashboard

Start the local dashboard server:

```powershell
python -m gigoptimizer.api.main
```

Then open:

- [http://127.0.0.1:8001/](http://127.0.0.1:8001/)

The dashboard includes:

- live gig metrics with a Chart.js line chart
- HITL approval queue with approve and reject actions
- keyword pulse cards with an `Apply to Gig` action
- agent health cards for all seven layers
- live competitor comparison with title-pattern and conversion-proxy analysis
- scraper visibility logs, keyword quality scoring, comparison timeline, and latest diff history
- protected notification settings for Slack and WhatsApp
- SMTP email settings and test delivery
- marketplace scraper and AI overview settings
- weekly report generation and HTML report links
- live browser updates over WebSocket

## Chrome Extension Import

GigOptimizer now includes a Chrome extension scaffold in [extensions/fiverr-market-capture](/D:/gigoptimizer-pro/extensions/fiverr-market-capture) so visible Fiverr page-one results can be imported directly from the user’s browser instead of relying only on server-side scraping.

Backend env for extension import:

```powershell
EXTENSION_ENABLED=true
EXTENSION_API_TOKEN=replace-with-a-long-random-secret
EXTENSION_MAX_GIGS_PER_IMPORT=25
EXTENSION_IMPORT_TTL_SECONDS=900
```

Extension flow:

1. Load the unpacked extension folder in Chrome.
2. Save the API base URL, extension API token, and your Fiverr gig URL.
3. Open a Fiverr search page.
4. Click `Capture current Fiverr page`.
5. The extension sends the visible cards to `/api/extension/import`.
6. The backend validates, normalizes, caches, compares, stores, and broadcasts the results to the dashboard and copilot.

## Verification

You can now verify a running local or hosted instance with one command.

Local verification:

```powershell
gigoptimizer-verify --base-url http://127.0.0.1:8001
```

Hosted verification:

```powershell
gigoptimizer-verify --base-url https://your-domain.example
```

If authentication is enabled on the hosted dashboard:

```powershell
gigoptimizer-verify `
  --base-url https://your-domain.example `
  --username admin `
  --password your-password
```

The verifier checks:

- `/api/health`
- the main page
- critical static assets
- authentication flow
- `/api/state`
- `/api/run`
- `/api/settings`
- `/api/reports/run`
- generated report download over HTTP

It writes a machine-readable report to:

- `artifacts/verification-report.json`

## Authentication For Hosted Use

For a hosted deployment, set these values in `.env` before starting the dashboard:

```powershell
APP_AUTH_ENABLED=true
APP_ADMIN_USERNAME=admin
APP_ADMIN_PASSWORD=change-me-now
APP_SESSION_SECRET=replace-with-a-long-random-secret
APP_COOKIE_SECURE=true
```

If you prefer a hashed password instead of storing a plaintext password in `.env`, generate one with:

```powershell
python -c "from gigoptimizer.services.auth_service import AuthService; from gigoptimizer.config import GigOptimizerConfig; print(AuthService(GigOptimizerConfig()).hash_password('change-me-now'))"
```

Then store the result in `APP_ADMIN_PASSWORD_HASH` and remove `APP_ADMIN_PASSWORD`.

## Scheduled Weekly Reports

The FastAPI app starts an in-process scheduler automatically.

- Schedule: Sunday at 08:00 local time
- Output: JSON, Markdown, and HTML
- Output folder: `reports/`

You can also trigger a report manually from the dashboard or over the API:

```powershell
Invoke-WebRequest -UseBasicParsing `
  -Method POST `
  -Uri http://127.0.0.1:8001/api/reports/run `
  -ContentType 'application/json' `
  -Body '{"use_live_connectors": false}'
```

## Example Output Areas

The report includes:

- `optimization_score`
- `niche_pulse`
- `persona_insights`
- `title_variants`
- `description_recommendations`
- `faq_recommendations`
- `tag_recommendations`
- `conversion_audit`
- `pricing_recommendations`
- `review_actions`
- `external_traffic_actions`
- `weekly_action_plan`
- `caution_notes`

## Step 2 Validation And HITL

The codebase now includes:

- `gigoptimizer/validators/hallucination_check.py`
- `gigoptimizer/validators/tos_checker.py`
- `gigoptimizer/queue/hitl_queue.py`

These modules are wired into the dashboard action flow for title and keyword proposals:

- proposed changes are validated before entering the queue
- risky or low-confidence changes can be rejected before touching the snapshot
- approved changes update the snapshot and re-run the optimizer

## Slack And WhatsApp Alerts

You can configure notifications in either of these ways:

- set secrets with environment variables in `.env`
- log into the dashboard and save them from the protected settings panel

Supported channels:

- Slack via Incoming Webhook URL
- WhatsApp via Meta WhatsApp Cloud API access token, phone number ID, and recipient number

Environment variables:

```powershell
SLACK_WEBHOOK_URL=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_RECIPIENT_NUMBER=
WHATSAPP_API_VERSION=v23.0
```

The dashboard lets you:

- enable or disable each channel
- choose which events send alerts
- send a test message before going live

## Email Alerts

The dashboard can send the same event updates over SMTP email.

Relevant `.env` values:

```powershell
EMAIL_SMTP_HOST=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USERNAME=vpnid259@gmail.com
EMAIL_SMTP_PASSWORD=
EMAIL_FROM_ADDRESS=vpnid259@gmail.com
EMAIL_TO_ADDRESSES=reveal4902k@gmail.com
EMAIL_USE_TLS=true
```

Important Gmail note:

- use a Gmail App Password, not your normal account password, when sending through Gmail SMTP
- the email fields are also editable from the protected dashboard configuration panel

## Live Competitor Scraping

Live public Fiverr competitor scraping is optional and is designed to stay honest about what public marketplace data can and cannot show.

What it does:

- scrapes public Fiverr search result cards for your chosen search terms
- compares live titles, price anchors, ratings, review counts, and delivery cues
- estimates why competitors are likely winning more clicks or conversions using visible proxy signals

What it does not do:

- it does not know competitors' real private conversion rates
- it does not bypass private dashboards or protected seller data

Key `.env` values:

```powershell
MARKETPLACE_ENABLED=false
MARKETPLACE_SEARCH_TERMS=wordpress speed,core web vitals,woocommerce speed
FIVERR_MARKETPLACE_SEARCH_URL_TEMPLATE=https://www.fiverr.com/search/gigs?query={query}
FIVERR_MARKETPLACE_MAX_RESULTS=12
```

The dashboard also exposes a protected marketplace settings panel so you can change terms without editing files.

If direct Fiverr marketplace scraping fails, the app can also fall back to SerpApi discovery and then enrich discovered Fiverr gig URLs from their public pages.

## Browser-Assisted Fiverr Import

If Fiverr blocks automated marketplace scraping, use the dashboard's browser-assisted import instead.

Flow:

1. Open real Fiverr search results in your normal browser.
2. Solve any challenge there manually.
3. In GigOptimizer, open `My Gig Vs Market`.
4. Click `Copy Fiverr Capture Script`.
5. Paste that script into the Fiverr page browser console and run it.
6. Paste the copied JSON into `Imported competitor input`.
7. Click `Analyze Imported Competitors`.

This keeps the comparison workflow usable even when Playwright is challenged.

## AI Overview Connector

The app includes a lightweight AI overview connector for executive summaries and next-step suggestions after each run.

Current provider wiring:

- `n8n` webhook mode for the floating copilot
- OpenAI-compatible `Responses` API endpoint for direct in-app summaries when you want it

Recommended low-cost setup:

- provider: `n8n`
- model: `webhook`

Relevant `.env` values:

```powershell
AI_PROVIDER=n8n
AI_MODEL=webhook
AI_API_KEY=
AI_API_BASE_URL=https://your-n8n-domain/webhook/gigoptimizer-assistant
```

You can also manage these from the protected dashboard configuration panel.

## Mobile App

The dashboard is now installable as a Progressive Web App.

To use it on your phone:

1. Host the app on your server with HTTPS enabled.
2. Open the dashboard URL in your phone browser.
3. Use “Add to Home Screen” to install it.

The mobile app connects directly to the same FastAPI backend, so you can watch live state, reports, and queue activity from your phone.

Important WhatsApp note:

- this app sends plain text Cloud API messages
- for strict production use, Meta may require an approved template outside the customer service window, so test your recipient flow before relying on WhatsApp for critical alerts
- if the AI connector is unavailable or out of quota, the dashboard now falls back to a local summary so the operations panel still stays usable

## How To Extend It

Live connectors can be added later without rewriting the optimizer core:

- Fiverr export parser or approved API adapter
- Playwright-based competitor collector
- Google Trends or SEMrush ingestion
- Airtable, Supabase, or Postgres persistence
- cron, APScheduler, n8n, or LangGraph orchestration

## Useful Commands

Run the CLI with the sample snapshot:

```powershell
python -m gigoptimizer.cli --input examples\wordpress_speed_snapshot.json
```

Show connector readiness:

```powershell
python -m gigoptimizer.cli --show-connector-status --input examples\wordpress_speed_snapshot.json
```

Run the optimizer with live connectors enabled:

```powershell
python -m gigoptimizer.cli --input examples\wordpress_speed_snapshot.json --use-live-connectors
```

Dump Fiverr selector matches for debugging:

```powershell
python -m gigoptimizer.cli --debug-selectors --selector-debug-output debug\fiverr-dashboard.html
```

## Connector Notes

- `GoogleTrendsConnector` uses `pytrends` and blends current interest plus related queries into the niche pulse.
- `SemrushConnector` enriches keywords with search volume and difficulty when `SEMRUSH_API_KEY` is set.
- `FiverrSellerConnector` uses Playwright with either saved storage state or login credentials from `.env`.
- The Fiverr analytics selectors are intentionally configurable in `.env` because marketplace DOMs change over time.
- `pytrends` is an unofficial wrapper and its upstream GitHub repository is archived, so keep this connector swappable.
- The dashboard uses signed session cookies for auth; set `APP_COOKIE_SECURE=true` when you are serving over HTTPS.
- The public Fiverr marketplace scraper now supports a persistent browser profile in `playwright/.marketplace-profile` so you can solve challenge pages once and then retry scraping from the same session.
- For verification-heavy sessions, keep `FIVERR_MARKETPLACE_HEADLESS=false` so the scraper continues in the same visible session style that cleared the challenge.

## Manual Verification

If Fiverr serves an anti-bot challenge instead of public gig cards:

1. Open the dashboard.
2. Use `Run Live Scraper`.
3. If the activity feed shows a challenge, click `Start Verification`.
4. A persistent browser window opens on your machine with the same Fiverr marketplace URL.
5. Complete the challenge there and keep that window open until the dashboard reports progress.
6. The app now continues the scrape in that same visible browser session instead of switching back to a different automation shape immediately after verification.

Helpful marketplace anti-loop settings:

```powershell
FIVERR_MARKETPLACE_HEADLESS=false
FIVERR_MARKETPLACE_BROWSER_CHANNEL=msedge
FIVERR_MARKETPLACE_SLOW_MO_MS=250
```

When Fiverr blocks the request, the dashboard also stores a debug HTML file and screenshot in `artifacts\` so you can inspect exactly what the scraper hit.

## Setup Diagnostics

Use this to confirm connector readiness without guessing:

```powershell
python -m gigoptimizer.cli --show-connector-status --input examples\wordpress_speed_snapshot.json
```

Use this to inspect the Fiverr seller dashboard HTML and current selector matches:

```powershell
python -m gigoptimizer.cli --debug-selectors --selector-debug-output debug\fiverr-dashboard.html
```

The debug flow writes the raw HTML to the target `.html` file and a sibling `.json` file containing selector match counts and sample text.

## Verification

You can verify the app locally on your computer now, and use the same flow later against your hosted server.

Start the dashboard locally:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-dashboard.ps1
```

Open the dashboard in your browser:

```text
http://127.0.0.1:8001/
```

Run the local verification suite:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-instance.ps1
```

This writes a machine-readable report to:

```text
artifacts\verification-report.json
```

If dashboard auth is enabled, include your login credentials:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-instance.ps1 -Username admin -Password your-password
```

After you host the app, verify the public URL the same way:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-instance.ps1 -BaseUrl https://your-domain.com -Username admin -Password your-password -Output artifacts\verification-report-hosted.json
```

The verifier checks:

- app health
- dashboard root page
- frontend static assets
- authentication flow
- protected state endpoint
- pipeline execution
- settings endpoint
- weekly report generation and report download

On April 7, 2026, I ran the live verifier locally against `http://127.0.0.1:8001` and it passed all 8 checks.

## Production Auth

Generate a session secret:

```powershell
python -m gigoptimizer.security_cli generate-secret
```

Generate a password hash for the admin dashboard:

```powershell
python -m gigoptimizer.security_cli hash-password
```

Use those values in `.env.production`:

```text
APP_ENV=production
APP_AUTH_ENABLED=true
APP_COOKIE_SECURE=true
APP_FORCE_HTTPS=true
APP_BASE_URL=https://your-domain.com
APP_TRUSTED_HOSTS=your-domain.com,www.your-domain.com,127.0.0.1,localhost
APP_SESSION_SECRET=...
APP_ADMIN_PASSWORD_HASH=...
```

For a quick managed setup on your current machine, the local `.env` can also keep auth enabled in development mode so the dashboard stays protected while you test.

## Docker Hosting

This repo now includes:

- [Dockerfile](D:/gigoptimizer-pro/Dockerfile)
- [docker-compose.prod.yml](D:/gigoptimizer-pro/deploy/docker-compose.prod.yml)
- [Caddyfile](D:/gigoptimizer-pro/deploy/Caddyfile)
- [.env.production.example](D:/gigoptimizer-pro/.env.production.example)

Suggested low-cost deployment flow:

1. Copy `.env.production.example` to `.env.production`.
2. Set your real domain, email, auth secret, admin password hash, and notification keys.
3. Point your domain DNS to the server.
4. Start the stack:

```powershell
docker compose --env-file .env.production -f .\deploy\docker-compose.prod.yml up -d --build
```

5. Verify the hosted URL:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify-instance.ps1 -BaseUrl https://your-domain.com -Username admin -Password your-password -Output artifacts\verification-report-hosted.json
```

## Notes

- This MVP is best for planning, prioritization, and weekly optimization loops.
- For live automation, keep platform terms, rate limits, and anti-spam rules in scope.
- External traffic suggestions are written value-first to avoid reckless promotion patterns.
- The next build step is wiring the validator and HITL queue into concrete agent recommendations before any gig-facing action is auto-approved.
