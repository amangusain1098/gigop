from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


class PageSpeedConnector:
    API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

    def __init__(self, api_key: str | None = None, timeout_seconds: int = 20) -> None:
        self.api_key = str(api_key if api_key is not None else os.getenv("GOOGLE_PAGESPEED_API_KEY", "")).strip()
        self.timeout_seconds = max(5, int(timeout_seconds or 20))

    def fetch(self, url: str) -> dict[str, Any]:
        target_url = str(url or "").strip()
        if not self.api_key:
            return {"error": "no_api_key", "performance_score": None}
        if not target_url:
            return {"error": "missing_url", "performance_score": None}

        query = urlencode(
            {
                "url": target_url,
                "strategy": "mobile",
                "key": self.api_key,
            }
        )
        request_url = f"{self.API_URL}?{query}"
        try:
            with urlopen(request_url, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            return {
                "error": f"request_failed:{exc}",
                "performance_score": None,
            }
        lighthouse = payload.get("lighthouseResult") or {}
        categories = lighthouse.get("categories") or {}
        audits = lighthouse.get("audits") or {}
        performance_score = self._score(categories.get("performance"))
        seo_score = self._score(categories.get("seo"))
        accessibility_score = self._score(categories.get("accessibility"))
        recommendations = self._recommendations(audits)
        return {
            "lcp": self._seconds(self._audit_value(audits, "largest-contentful-paint")),
            "cls": self._float(self._audit_value(audits, "cumulative-layout-shift")),
            "fid": self._milliseconds(
                self._audit_value(audits, "max-potential-fid")
                or self._audit_value(audits, "first-input-delay")
                or self._audit_value(audits, "interaction-to-next-paint")
            ),
            "performance_score": performance_score,
            "seo_score": seo_score,
            "accessibility_score": accessibility_score,
            "recommendations": recommendations,
        }

    def _audit_value(self, audits: dict[str, Any], key: str) -> Any:
        audit = audits.get(key) or {}
        return audit.get("numericValue")

    def _score(self, category: Any) -> int | None:
        if not isinstance(category, dict):
            return None
        raw = category.get("score")
        if raw is None:
            return None
        try:
            return int(round(float(raw) * 100))
        except (TypeError, ValueError):
            return None

    def _seconds(self, value: Any) -> float | None:
        numeric = self._float(value)
        if numeric is None:
            return None
        return round(numeric / 1000.0, 2)

    def _milliseconds(self, value: Any) -> float | None:
        numeric = self._float(value)
        if numeric is None:
            return None
        return round(numeric, 2)

    def _float(self, value: Any) -> float | None:
        try:
            return round(float(value), 3)
        except (TypeError, ValueError):
            return None

    def _recommendations(self, audits: dict[str, Any]) -> list[str]:
        ranked: list[tuple[float, str]] = []
        for audit in audits.values():
            if not isinstance(audit, dict):
                continue
            details = audit.get("details") or {}
            if details.get("type") != "opportunity":
                continue
            title = str(audit.get("title", "")).strip()
            description = str(audit.get("description", "")).strip()
            if not title:
                continue
            savings = audit.get("numericValue")
            try:
                score = float(savings)
            except (TypeError, ValueError):
                score = 0.0
            if description:
                ranked.append((score, f"{title}: {description}"))
            else:
                ranked.append((score, title))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in ranked[:5]]
