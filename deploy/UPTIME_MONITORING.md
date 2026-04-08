# Uptime Monitoring Setup

Use [UptimeRobot](https://uptimerobot.com/) or your preferred monitor against:

- `https://animha.co.in/api/health`

Recommended configuration:

- Monitor type: `HTTPS`
- Friendly name: `GigOptimizer Pro Production`
- URL: `https://animha.co.in/api/health`
- Monitoring interval: `5 minutes`
- Keyword monitoring: `"status":"ok"`

What the endpoint checks:

- PostgreSQL connectivity
- Redis/pub-sub connectivity
- Worker backend status
- Frontend build availability
- Last successful job metadata

Recommended alerts:

- Email
- Slack
- WhatsApp

After the monitor is created, mirror the alerting contact channels inside the GigOptimizer settings dashboard so app-level alerts and infrastructure alerts arrive in the same places.
