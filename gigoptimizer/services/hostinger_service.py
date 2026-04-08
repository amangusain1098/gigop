from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from ..config import GigOptimizerConfig
from .settings_service import SettingsService


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class HostingerService:
    def __init__(self, config: GigOptimizerConfig, settings_service: SettingsService) -> None:
        self.config = config
        self.settings_service = settings_service

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
        }
        if not settings.enabled:
            base_payload["error_message"] = "Hostinger monitoring is disabled."
            return base_payload
        if not settings.api_token:
            base_payload["status"] = "warning"
            base_payload["error_message"] = "Hostinger API token is not configured."
            return base_payload

        try:
            return self.fetch_snapshot()
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
                    metrics = self._safe_get(
                        client,
                        f"/api/vps/v1/virtual-machines/{vm_id}/metrics",
                    )

            project_logs: list[dict[str, Any]] = []
            if settings.project_name:
                logs_payload = self._safe_get(
                    client,
                    f"/api/billing/v1/projects/{settings.project_name}/projects-logs",
                )
                project_logs = self._extract_items(logs_payload)[:8]

            domain_portfolio: list[dict[str, Any]] = []
            if settings.domain:
                domains_payload = self._safe_get(client, "/api/domains/v1/portfolio")
                domain_portfolio = [
                    item
                    for item in self._extract_items(domains_payload)
                    if settings.domain.lower() in str(item.get("domain") or item.get("name") or "").lower()
                ]

        return {
            "status": "ok",
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
        }

    def _safe_get(self, client: httpx.Client, path: str) -> Any:
        response = client.get(path)
        response.raise_for_status()
        return response.json()

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
