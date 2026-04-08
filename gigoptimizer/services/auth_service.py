from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any

from fastapi import Request, WebSocket

from ..config import GigOptimizerConfig


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("utf-8").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


@dataclass(slots=True)
class AuthSession:
    username: str
    expires_at: int
    csrf_token: str


class AuthService:
    COOKIE_NAME = "gigoptimizer_session"
    PASSWORD_SCHEME = "pbkdf2_sha256"
    PASSWORD_ITERATIONS = 390000

    def __init__(self, config: GigOptimizerConfig) -> None:
        self.config = config
        self._session_secret = (config.app_session_secret or secrets.token_urlsafe(32)).encode("utf-8")
        self._password_hash = config.app_admin_password_hash.strip()
        if not self._password_hash and config.app_admin_password:
            self._password_hash = self.hash_password(config.app_admin_password)

    @property
    def auth_enabled(self) -> bool:
        return self.config.app_auth_enabled or bool(self._password_hash)

    @property
    def admin_username(self) -> str:
        return self.config.app_admin_username

    def hash_password(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            self.PASSWORD_ITERATIONS,
        )
        return "$".join(
            [
                self.PASSWORD_SCHEME,
                str(self.PASSWORD_ITERATIONS),
                _b64encode(salt),
                _b64encode(derived),
            ]
        )

    def verify_password(self, password: str) -> bool:
        if not self._password_hash:
            return False
        try:
            scheme, iterations, salt_encoded, digest_encoded = self._password_hash.split("$", 3)
        except ValueError:
            return False
        if scheme != self.PASSWORD_SCHEME:
            return False
        try:
            iterations_int = int(iterations)
        except ValueError:
            return False

        salt = _b64decode(salt_encoded)
        expected = _b64decode(digest_encoded)
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations_int,
        )
        return hmac.compare_digest(actual, expected)

    def authenticate(self, username: str, password: str) -> bool:
        return username == self.admin_username and self.verify_password(password)

    def build_login_client_key(
        self,
        *,
        client_id: str = "",
        remote_addr: str = "",
        user_agent: str = "",
    ) -> str:
        seed = str(client_id).strip() or f"{str(remote_addr).strip()}|{str(user_agent).strip()[:180]}"
        return hashlib.sha256(f"gigoptimizer-login:{seed}".encode("utf-8")).hexdigest()

    def validate_runtime(self) -> tuple[list[str], list[str]]:
        errors: list[str] = []
        warnings: list[str] = []

        if self.auth_enabled and not self._password_hash:
            errors.append("Authentication is enabled but no admin password or password hash is configured.")

        if self.auth_enabled and not self.config.app_session_secret:
            message = "APP_SESSION_SECRET is not set. Sessions will be invalidated on every restart."
            if self.config.is_production:
                errors.append(message)
            else:
                warnings.append(message)

        if self.config.is_production:
            if not self.auth_enabled:
                errors.append("Production mode requires APP_AUTH_ENABLED=true and a configured admin password hash.")
            if not self.config.app_cookie_secure:
                errors.append("Production mode requires APP_COOKIE_SECURE=true.")
            if not self.config.app_force_https:
                warnings.append("APP_FORCE_HTTPS is off. Keep HTTPS termination enabled at the reverse proxy.")
            if not self.config.app_base_url:
                warnings.append("APP_BASE_URL is not set. Use your public HTTPS URL for stronger origin validation.")
            if not self.config.trusted_hosts_list:
                warnings.append("APP_TRUSTED_HOSTS is empty. Set it to your public hostname and localhost values.")
        return errors, warnings

    def create_session_token(self, username: str) -> str:
        expires_at = int(time.time()) + (self.config.app_session_ttl_minutes * 60)
        csrf_token = secrets.token_urlsafe(24)
        payload = json.dumps(
            {
                "username": username,
                "expires_at": expires_at,
                "csrf_token": csrf_token,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        signature = hmac.new(self._session_secret, payload, hashlib.sha256).digest()
        return f"{_b64encode(payload)}.{_b64encode(signature)}"

    def get_session(self, token: str | None) -> AuthSession | None:
        if not token:
            return None
        try:
            payload_encoded, signature_encoded = token.split(".", 1)
            payload = _b64decode(payload_encoded)
            signature = _b64decode(signature_encoded)
        except ValueError:
            return None

        expected_signature = hmac.new(self._session_secret, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected_signature):
            return None

        try:
            data = json.loads(payload.decode("utf-8"))
            session = AuthSession(
                username=str(data["username"]),
                expires_at=int(data["expires_at"]),
                csrf_token=str(data["csrf_token"]),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return None

        if session.expires_at < int(time.time()):
            return None
        if session.username != self.admin_username:
            return None
        return session

    def get_request_session(self, request: Request) -> AuthSession | None:
        return self.get_session(request.cookies.get(self.COOKIE_NAME))

    def get_websocket_session(self, websocket: WebSocket) -> AuthSession | None:
        return self.get_session(websocket.cookies.get(self.COOKIE_NAME))

    def get_auth_state(self, session: AuthSession | None) -> dict[str, Any]:
        return {
            "enabled": self.auth_enabled,
            "authenticated": session is not None or not self.auth_enabled,
            "username": session.username if session else (self.admin_username if not self.auth_enabled else ""),
            "csrf_token": session.csrf_token if session is not None else "",
        }
