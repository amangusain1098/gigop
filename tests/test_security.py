from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from gigoptimizer.api.security import is_allowed_origin
from gigoptimizer.api.security import SecurityHeadersMiddleware
from gigoptimizer.config import GigOptimizerConfig


class SecurityOriginTests(unittest.TestCase):
    def test_forwarded_host_allows_public_websocket_origin(self) -> None:
        config = GigOptimizerConfig(app_base_url="", app_trusted_hosts="")
        allowed = is_allowed_origin(
            "https://theatre-spell-territories-yang.trycloudflare.com",
            config,
            "theatre-spell-territories-yang.trycloudflare.com, 127.0.0.1:8001",
        )
        self.assertTrue(allowed)

    def test_production_headers_exclude_dev_origin_and_allow_same_origin_camera(self) -> None:
        config = GigOptimizerConfig(
            app_env="production",
            frontend_dev_url="http://127.0.0.1:5173",
            app_cookie_secure=True,
        )
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/ping")
        async def ping() -> dict[str, str]:
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/ping")
        csp = response.headers["content-security-policy"]
        permissions = response.headers["permissions-policy"]

        self.assertNotIn("127.0.0.1:5173", csp)
        self.assertIn("camera=(self)", permissions)
        self.assertNotIn("camera=()", permissions)

    def test_development_headers_include_dev_origin_for_vite(self) -> None:
        config = GigOptimizerConfig(
            app_env="development",
            frontend_dev_url="http://127.0.0.1:5173",
        )
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware, config=config)

        @app.get("/ping")
        async def ping() -> dict[str, str]:
            return {"status": "ok"}

        client = TestClient(app)
        response = client.get("/ping")
        csp = response.headers["content-security-policy"]

        self.assertIn("http://127.0.0.1:5173", csp)


if __name__ == "__main__":
    unittest.main()
