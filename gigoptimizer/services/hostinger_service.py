from __future__ import annotations

import copy
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..config import GigOptimizerConfig
from .settings_service import SettingsService


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class HostingerService:
    CACHE_TTL_SECONDS = 30

    def __init__(self, config: GigOptimizerConfig, settings_service: SettingsService) -> None:
        self.config = config
        self.settings_service = settings_service
        self._cache_lock = threading.Lock()
        self._cache_key: tuple[Any, ...] | None = None
        self._cache_expires_at = 0.0
        self._cache_payload: dict[str, Any] | None = None

    def get_public_status(self) -> dict[str, Any]:
        settings = self.settings_service.get_settings().hostinger
        base_payload = {
            "status": "disabled",
            "enabled": settings.enabled,
            "configured": bool(settings.api_token),
            "base_url": settings.api_base_url,
            "virtual_machine_id": settings.virtual_machine_id,
            "project_name": settings.project_name,
            "domain": settings.domain,
            "metrics_window_minutes": settings.metrics_window_minutes,
            "last_checked_at": utc_now_iso(),
            "error_message": "",
            "virtual_machines": [],
            "selected_vm": None,
            "metrics": {},
            "project_logs": [],
            "domain_portfolio": [],
            "warnings": [],
        }
        if not settings.enabled:
            base_payload["error_message"] = "Hostinger monitoring is disabled."
            return base_payload
        if not settings.api_token:
            base_payload["status"] = "warning"
            base_payload["error_message"] = "Hostinger API token is not configured."
            return base_payload

        cached = self._load_cached_snapshot(settings)
        if cached is not None:
            return cached

        try:
            snapshot = self.fetch_snapshot()
            self._store_cached_snapshot(settings, snapshot)
            return snapshot
        except Exception as exc:
            base_payload["status"] = "error"
            base_payload["error_message"] = str(exc)
            return base_payload

    def fetch_snapshot(self) -> dict[str, Any]:
        settings = self.settings_service.get_settings().hostinger
        headers = {
            "Authorization": f"Bearer {settings.api_token}",
            "Accept": "application/json",
            "User-Agent": "GigOptimizer-Pro/0.5.0",
        }
        base_url = settings.api_base_url.rstrip("/")
        timeout = max(5, int(self.config.hostinger_request_timeout_seconds))
        warnings: list[str] = []

        with httpx.Client(base_url=base_url, headers=headers, timeout=timeout) as client:
            virtual_machines_payload = self._safe_get(client, "/api/vps/v1/virtual-machines")
            virtual_machines = self._extract_items(virtual_machines_payload)
            selected_vm = self._select_virtual_machine(virtual_machines, settings.virtual_machine_id)

            metrics: dict[str, Any] = {}
            if selected_vm is not None:
                vm_id = str(
                    selected_vm.get("id")
                    or selected_vm.get("virtualMachineId")
                    or selected_vm.get("identifier")
                    or settings.virtual_machine_id
                ).strip()
                if vm_id:
                    selected_vm = self._optional_get(
                        client,
                        f"/api/vps/v1/virtual-machines/{vm_id}",
                        warnings=warnings,
                        description="virtual machine details",
                    ) or selected_vm
                    metrics = self._safe_get(
                        client,
                        f"/api/vps/v1/virtual-machines/{vm_id}/metrics",
                        params=self._metrics_params(settings.metrics_window_minutes),
                    )

            project_logs: list[dict[str, Any]] = []
            if selected_vm is not None:
                vm_id = str(
                    selected_vm.get("id")
                    or selected_vm.get("virtualMachineId")
                    or selected_vm.get("identifier")
                    or settings.virtual_machine_id
                ).strip()
                logs_payload = self._optional_get(
                    client,
                    f"/api/vps/v1/virtual-machines/{vm_id}/actions",
                    warnings=warnings,
                    description="virtual machine actions",
                )
                project_logs = self._extract_items(logs_payload)[:8]

            domain_portfolio: list[dict[str, Any]] = []
            if settings.domain:
                domains_payload = self._optional_get(
                    client,
                    "/api/domains/v1/portfolio",
                    warnings=warnings,
                    description="domain portfolio",
                )
                domain_portfolio = [
                    item
                    for item in self._extract_items(domains_payload)
                    if settings.domain.lower() in str(item.get("domain") or item.get("name") or "").lower()
                ]

        return {
            "status": "warning" if warnings else "ok",
            "enabled": settings.enabled,
            "configured": True,
            "base_url": base_url,
            "virtual_machine_id": settings.virtual_machine_id,
            "project_name": settings.project_name,
            "domain": settings.domain,
            "metrics_window_minutes": settings.metrics_window_minutes,
            "last_checked_at": utc_now_iso(),
            "error_message": "",
            "virtual_machines": virtual_machines[:10],
            "selected_vm": selected_vm,
            "metrics": metrics,
            "project_logs": project_logs,
            "domain_portfolio": domain_portfolio[:5],
            "warnings": warnings,
        }

    def _settings_cache_key(self, settings) -> tuple[Any, ...]:
        return (
            settings.enabled,
            settings.api_base_url.rstrip("/"),
            bool(settings.api_token),
            settings.virtual_machine_id,
            settings.project_name,
            settings.domain,
            settings.metrics_window_minutes,
        )

    def _load_cached_snapshot(self, settings) -> dict[str, Any] | None:
        cache_key = self._settings_cache_key(settings)
        now = time.monotonic()
        with self._cache_lock:
            if self._cache_payload is None:
                return None
            if self._cache_key != cache_key:
                return None
            if now >= self._cache_expires_at:
                self._cache_payload = None
                return None
            return copy.deepcopy(self._cache_payload)

    def _store_cached_snapshot(self, settings, snapshot: dict[str, Any]) -> None:
        with self._cache_lock:
            self._cache_key = self._settings_cache_key(settings)
            self._cache_expires_at = time.monotonic() + self.CACHE_TTL_SECONDS
            self._cache_payload = copy.deepcopy(snapshot)

    def _safe_get(self, client: httpx.Client, path: str, params: dict[str, Any] | None = None) -> Any:
        response = client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    def _optional_get(
        self,
        client: httpx.Client,
        path: str,
        *,
        warnings: list[str],
        description: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        try:
            return self._safe_get(client, path, params=params)
        except httpx.HTTPStatusError as exc:
            warnings.append(f"{description} unavailable ({exc.response.status_code}).")
        except Exception as exc:
            warnings.append(f"{description} unavailable ({exc}).")
        return {}

    def _extract_items(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            for key in ("items", "data", "results", "virtualMachines", "logs", "domains"):
                value = payload.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
        return []

    def _select_virtual_machine(
        self,
        virtual_machines: list[dict[str, Any]],
        selected_id: str,
    ) -> dict[str, Any] | None:
        if not virtual_machines:
            return None
        if not selected_id:
            return virtual_machines[0]
        for item in virtual_machines:
            candidate_id = str(
                item.get("id") or item.get("virtualMachineId") or item.get("identifier") or ""
            ).strip()
            if candidate_id == selected_id:
                return item
        return virtual_machines[0]

    def _metrics_params(self, window_minutes: int) -> dict[str, str]:
        now = datetime.now(timezone.utc).replace(microsecond=0)
        start = now - timedelta(minutes=max(5, window_minutes))
        return {
            "date_from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date_to": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
