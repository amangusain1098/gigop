from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx

from gigoptimizer.config import GigOptimizerConfig
from gigoptimizer.services.hostinger_service import HostingerService
from gigoptimizer.services.settings_service import SettingsService


class _FakeResponse:
    def __init__(self, path: str, status_code: int, payload):
        self.path = path
        self.status_code = status_code
        self._payload = payload
        self.request = httpx.Request("GET", f"https://developers.hostinger.com{path}")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            response = httpx.Response(self.status_code, request=self.request, json=self._payload)
            raise httpx.HTTPStatusError("request failed", request=self.request, response=response)

    def json(self):
        return self._payload


class _FakeClient:
    calls: list[tuple[str, dict | None]] = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, path: str, params: dict | None = None):
        self.__class__.calls.append((path, params))
        if path == "/api/vps/v1/virtual-machines":
            return _FakeResponse(
                path,
                200,
                [
                    {
                        "id": 1568667,
                        "hostname": "srv1568667.hstgr.cloud",
                        "state": "running",
                        "ipv4": [{"address": "187.127.148.139"}],
                    }
                ],
            )
        if path == "/api/vps/v1/virtual-machines/1568667/metrics":
            return _FakeResponse(
                path,
                200,
                {
                    "cpu_usage": {"unit": "%", "usage": {"1": 1.16}},
                    "ram_usage": {"unit": "bytes", "usage": {"1": 965156864}},
                },
            )
        if path == "/api/vps/v1/virtual-machines/1568667":
            return _FakeResponse(
                path,
                200,
                {
                    "id": 1568667,
                    "hostname": "srv1568667.hstgr.cloud",
                    "state": "running",
                    "created_at": "2026-04-08T03:51:25Z",
                },
            )
        if path == "/api/vps/v1/virtual-machines/1568667/actions":
            return _FakeResponse(path, 404, {"message": "not found"})
        if path == "/api/domains/v1/portfolio":
            return _FakeResponse(
                path,
                200,
                [{"domain": "animha.co.in", "status": "active"}],
            )
        return _FakeResponse(path, 404, {"message": "unexpected path"})


class HostingerServiceTests(unittest.TestCase):
    def test_fetch_snapshot_uses_metric_window_and_tolerates_optional_failures(self) -> None:
        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "HOSTINGER_ENABLED": "true",
                    "HOSTINGER_API_TOKEN": "token-value",
                    "HOSTINGER_DOMAIN": "animha.co.in",
                    "HOSTINGER_PROJECT_NAME": "deploy",
                    "HOSTINGER_METRICS_WINDOW_MINUTES": "60",
                },
                clear=False,
            ):
                config = GigOptimizerConfig.from_env()
                settings = SettingsService(config)
                settings.update_settings(
                    {
                        "hostinger": {
                            "enabled": True,
                            "api_token": "token-value",
                            "domain": "animha.co.in",
                            "project_name": "deploy",
                            "metrics_window_minutes": 60,
                        }
                    }
                )
                service = HostingerService(config, settings)
                _FakeClient.calls = []
                with patch("gigoptimizer.services.hostinger_service.httpx.Client", _FakeClient):
                    snapshot = service.fetch_snapshot()

        self.assertEqual(snapshot["status"], "warning")
        self.assertTrue(snapshot["virtual_machines"])
        self.assertTrue(snapshot["metrics"])
        self.assertTrue(snapshot["domain_portfolio"])
        self.assertTrue(any("virtual machine actions unavailable" in warning for warning in snapshot["warnings"]))

        metric_call = next(
            (params for path, params in _FakeClient.calls if path.endswith("/metrics")),
            None,
        )
        self.assertIsNotNone(metric_call)
        self.assertIn("date_from", metric_call)
        self.assertIn("date_to", metric_call)

    def test_get_public_status_reuses_cached_snapshot_within_ttl(self) -> None:
        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "HOSTINGER_ENABLED": "true",
                    "HOSTINGER_API_TOKEN": "token-value",
                    "HOSTINGER_DOMAIN": "animha.co.in",
                    "HOSTINGER_PROJECT_NAME": "deploy",
                },
                clear=False,
            ):
                config = GigOptimizerConfig.from_env()
                settings = SettingsService(config)
                settings.update_settings(
                    {
                        "hostinger": {
                            "enabled": True,
                            "api_token": "token-value",
                            "domain": "animha.co.in",
                            "project_name": "deploy",
                        }
                    }
                )
                service = HostingerService(config, settings)
                _FakeClient.calls = []
                with patch("gigoptimizer.services.hostinger_service.httpx.Client", _FakeClient):
                    first = service.get_public_status()
                    second = service.get_public_status()

        self.assertEqual(first["status"], second["status"])
        self.assertEqual(len(_FakeClient.calls), 5)


if __name__ == "__main__":
    unittest.main()
