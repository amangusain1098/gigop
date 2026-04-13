from __future__ import annotations

import json
import re
from pathlib import Path

from ..config import GigOptimizerConfig
from ..models import ConnectorStatus, GigAnalytics


class FiverrSellerConnector:
    name = "fiverr"

    def __init__(self, config: GigOptimizerConfig) -> None:
        self.config = config

    def fetch_seller_metrics(self) -> tuple[GigAnalytics | None, ConnectorStatus]:
        # DEPRECATED: We are moving to a manual-entry / screenshot-parsing model.
        # Playwright auto-login to private Fiverr dashboards is too fragile for production.
        return None, ConnectorStatus(
            connector=self.name,
            status="skipped",
            detail="Private seller metric scraping is deprecated. Use manual entry or AI screenshot parsing instead.",
        )

    def debug_selectors(self, output_path: str | Path | None = None) -> ConnectorStatus:
        if not self.config.fiverr_analytics_url:
            return ConnectorStatus(
                connector=self.name,
                status="skipped",
                detail="Set FIVERR_ANALYTICS_URL in .env before running selector debug.",
            )

        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        except ImportError:
            return ConnectorStatus(
                connector=self.name,
                status="skipped",
                detail="Install the optional 'live' dependencies to enable selector debugging.",
            )

        target = Path(output_path) if output_path else Path("debug") / "fiverr-selector-debug.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        metadata_path = target.with_suffix(".json")

        try:
            with self._open_analytics_page() as page:
                html = page.content()
                target.write_text(html, encoding="utf-8")
                selector_report = {
                    "impressions": self._selector_debug_entry(page, self.config.fiverr_impressions_selector),
                    "clicks": self._selector_debug_entry(page, self.config.fiverr_clicks_selector),
                    "orders": self._selector_debug_entry(page, self.config.fiverr_orders_selector),
                    "saves": self._selector_debug_entry(page, self.config.fiverr_saves_selector),
                    "response_time": self._selector_debug_entry(page, self.config.fiverr_response_time_selector),
                }
                metadata_path.write_text(json.dumps(selector_report, indent=2), encoding="utf-8")
        except PlaywrightTimeoutError as exc:
            return ConnectorStatus(
                connector=self.name,
                status="error",
                detail=f"Fiverr selector debug timed out: {exc}",
            )
        except Exception as exc:
            return ConnectorStatus(
                connector=self.name,
                status="error",
                detail=f"Fiverr selector debug failed: {exc}",
            )

        return ConnectorStatus(
            connector=self.name,
            status="ok",
            detail=f"Saved raw dashboard HTML to {target} and selector metadata to {metadata_path}.",
        )

    def _login(self, page) -> None:
        page.goto(self.config.fiverr_login_url, wait_until="domcontentloaded")
        page.locator(self.config.fiverr_email_selector).first.fill(self.config.fiverr_email)
        page.locator(self.config.fiverr_password_selector).first.fill(self.config.fiverr_password)
        page.locator(self.config.fiverr_submit_selector).first.click()
        page.wait_for_load_state("networkidle")

    def _open_analytics_page(self):
        from contextlib import contextmanager

        from playwright.sync_api import sync_playwright

        @contextmanager
        def _session():
            storage_state_path = Path(self.config.fiverr_storage_state_path)
            storage_state_path.parent.mkdir(parents=True, exist_ok=True)
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=self.config.fiverr_headless)
                context_kwargs = {}
                if storage_state_path.exists():
                    context_kwargs["storage_state"] = str(storage_state_path)
                context = browser.new_context(**context_kwargs)
                page = context.new_page()

                if not storage_state_path.exists():
                    if not (self.config.fiverr_email and self.config.fiverr_password):
                        browser.close()
                        raise RuntimeError(
                            "Provide FIVERR_EMAIL and FIVERR_PASSWORD or a saved storage state file."
                        )
                    self._login(page)
                    context.storage_state(path=str(storage_state_path))

                page.goto(self.config.fiverr_analytics_url, wait_until="domcontentloaded")
                page.wait_for_load_state("networkidle")
                try:
                    yield page
                finally:
                    browser.close()

        return _session()

    def _read_int_metric(self, page, selector: str) -> int:
        text = self._read_text(page, selector)
        number = self._extract_number(text)
        return int(number) if number is not None else 0

    def _read_float_metric(self, page, selector: str) -> float | None:
        text = self._read_text(page, selector)
        number = self._extract_number(text)
        return float(number) if number is not None else None

    def _read_text(self, page, selector: str) -> str:
        locator = page.locator(selector).first
        return (locator.inner_text(timeout=10000) or "").strip()

    def _selector_debug_entry(self, page, selector: str) -> dict[str, str | int]:
        locator = page.locator(selector)
        count = locator.count()
        sample_text = ""
        if count:
            sample_text = (locator.first.inner_text(timeout=10000) or "").strip()
        return {
            "selector": selector,
            "match_count": count,
            "sample_text": sample_text,
        }

    def _extract_number(self, text: str) -> float | None:
        cleaned = text.replace(",", "").strip().lower()
        match = re.search(r"(\d+(?:\.\d+)?)", cleaned)
        if not match:
            return None
        value = float(match.group(1))
        if "min" in cleaned:
            return round(value / 60, 2)
        return value
