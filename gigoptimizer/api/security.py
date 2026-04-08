from __future__ import annotations

from urllib.parse import urlparse

from fastapi import HTTPException, Request, WebSocket
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import GigOptimizerConfig


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, config: GigOptimizerConfig) -> None:
        super().__init__(app)
        self._config = config
        dev_origin = ""
        if not config.is_production and config.frontend_dev_url:
            parsed = urlparse(config.frontend_dev_url)
            if parsed.scheme and parsed.netloc:
                dev_origin = f" {parsed.scheme}://{parsed.netloc}"
        self._csp = (
            "default-src 'self'; "
            f"script-src 'self' https://cdn.jsdelivr.net{dev_origin} 'unsafe-inline'; "
            f"style-src 'self'{dev_origin} 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            f"connect-src 'self' ws: wss:{dev_origin}; "
            "manifest-src 'self'; "
            "worker-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", self._csp)
        if self._config.app_cookie_secure or request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response


def is_allowed_origin(origin: str | None, config: GigOptimizerConfig, host_header: str | None = None) -> bool:
    if not origin:
        return True

    parsed = urlparse(origin)
    if not parsed.hostname:
        return False

    allowed_hosts = set(config.trusted_hosts_list)
    if config.app_base_url:
        base = urlparse(config.app_base_url)
        if base.hostname:
            allowed_hosts.add(base.hostname)
    if host_header:
        for raw_host in host_header.split(","):
            candidate = raw_host.strip()
            if not candidate:
                continue
            allowed_hosts.add(candidate.split(":", 1)[0].strip())
    allowed_hosts.update({"127.0.0.1", "localhost"})
    return parsed.hostname in allowed_hosts


def require_csrf(request: Request) -> None:
    auth_service = request.app.state.auth_service
    if not auth_service.auth_enabled:
        return

    session = auth_service.get_request_session(request)
    if session is None:
        raise HTTPException(status_code=401, detail="Authentication required.")

    csrf_token = request.headers.get("X-CSRF-Token", "").strip()
    if not csrf_token or csrf_token != session.csrf_token:
        raise HTTPException(status_code=403, detail="Invalid or missing CSRF token.")


def verify_websocket_origin(websocket: WebSocket, config: GigOptimizerConfig) -> bool:
    host_hint = (
        websocket.headers.get("x-forwarded-host")
        or websocket.headers.get("x-original-host")
        or websocket.headers.get("host")
    )
    return is_allowed_origin(websocket.headers.get("origin"), config, host_hint)
