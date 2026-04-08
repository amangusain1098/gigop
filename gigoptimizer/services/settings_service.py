from __future__ import annotations

import json
from dataclasses import asdict

from ..config import GigOptimizerConfig
from ..models import (
    AISettings,
    EmailSettings,
    HostingerSettings,
    MarketplaceSettings,
    NotificationEvents,
    NotificationSettings,
    SlackSettings,
    WhatsAppSettings,
)


class SettingsService:
    def __init__(self, config: GigOptimizerConfig) -> None:
        self.config = config
        self.path = config.integration_settings_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write(self._default_settings())

    def get_settings(self) -> NotificationSettings:
        stored = self._read()
        return NotificationSettings(
            events=NotificationEvents(**stored.get("events", {})),
            email=EmailSettings(
                enabled=bool(stored.get("email", {}).get("enabled", False)),
                smtp_host=self.config.email_smtp_host or str(stored.get("email", {}).get("smtp_host", "smtp.gmail.com")).strip(),
                smtp_port=int(stored.get("email", {}).get("smtp_port", self.config.email_smtp_port)),
                smtp_username=self.config.email_smtp_username or str(stored.get("email", {}).get("smtp_username", "")).strip(),
                smtp_password=self.config.email_smtp_password or str(stored.get("email", {}).get("smtp_password", "")).strip(),
                from_address=self.config.email_from_address or str(stored.get("email", {}).get("from_address", "")).strip(),
                to_addresses=self._parse_list(self.config.email_to_addresses) or self._parse_list(stored.get("email", {}).get("to_addresses", [])),
                use_tls=self.config.email_use_tls if self.config.email_smtp_username or self.config.email_to_addresses else bool(stored.get("email", {}).get("use_tls", True)),
            ),
            slack=SlackSettings(
                enabled=bool(stored.get("slack", {}).get("enabled", False)),
                webhook_url=self.config.slack_webhook_url or str(stored.get("slack", {}).get("webhook_url", "")).strip(),
            ),
            whatsapp=WhatsAppSettings(
                enabled=bool(stored.get("whatsapp", {}).get("enabled", False)),
                access_token=self.config.whatsapp_access_token or str(stored.get("whatsapp", {}).get("access_token", "")).strip(),
                phone_number_id=self.config.whatsapp_phone_number_id or str(stored.get("whatsapp", {}).get("phone_number_id", "")).strip(),
                recipient_number=self.config.whatsapp_recipient_number or str(stored.get("whatsapp", {}).get("recipient_number", "")).strip(),
                api_version=self.config.whatsapp_api_version or str(stored.get("whatsapp", {}).get("api_version", "v23.0")).strip(),
            ),
            ai=AISettings(
                enabled=bool(stored.get("ai", {}).get("enabled", False)),
                provider=self.config.ai_provider or str(stored.get("ai", {}).get("provider", "openai")).strip(),
                model=self.config.ai_model or str(stored.get("ai", {}).get("model", "gpt-5.4-mini")).strip(),
                api_key=self.config.ai_api_key or str(stored.get("ai", {}).get("api_key", "")).strip(),
                api_base_url=self.config.ai_api_base_url or str(stored.get("ai", {}).get("api_base_url", "https://api.openai.com/v1")).strip(),
            ),
            hostinger=HostingerSettings(
                enabled=self.config.hostinger_enabled or bool(stored.get("hostinger", {}).get("enabled", False)),
                api_base_url=(
                    self.config.hostinger_api_base_url
                    or str(stored.get("hostinger", {}).get("api_base_url", "https://developers.hostinger.com")).strip()
                    or "https://developers.hostinger.com"
                ),
                api_token=self.config.hostinger_api_token or str(stored.get("hostinger", {}).get("api_token", "")).strip(),
                virtual_machine_id=(
                    self.config.hostinger_virtual_machine_id
                    or str(stored.get("hostinger", {}).get("virtual_machine_id", "")).strip()
                ),
                project_name=(
                    self.config.hostinger_project_name
                    or str(stored.get("hostinger", {}).get("project_name", "")).strip()
                ),
                domain=self.config.hostinger_domain or str(stored.get("hostinger", {}).get("domain", "")).strip(),
                metrics_window_minutes=max(
                    5,
                    int(stored.get("hostinger", {}).get("metrics_window_minutes", self.config.hostinger_metrics_window_minutes) or self.config.hostinger_metrics_window_minutes),
                ),
            ),
            marketplace=MarketplaceSettings(
                enabled=self.config.marketplace_enabled or bool(stored.get("marketplace", {}).get("enabled", False)),
                search_terms=self._parse_list(self.config.marketplace_search_terms) or self._parse_list(stored.get("marketplace", {}).get("search_terms", [])),
                max_results=int(stored.get("marketplace", {}).get("max_results", self.config.fiverr_marketplace_max_results)),
                search_url_template=self.config.fiverr_marketplace_search_url_template or str(stored.get("marketplace", {}).get("search_url_template", "https://www.fiverr.com/search/gigs?query={query}")).strip(),
                reader_enabled=bool(stored.get("marketplace", {}).get("reader_enabled", self.config.marketplace_reader_enabled)),
                reader_base_url=(
                    str(stored.get("marketplace", {}).get("reader_base_url", self.config.marketplace_reader_base_url)).strip()
                    or self.config.marketplace_reader_base_url
                ),
                my_gig_url=self.config.marketplace_my_gig_url or str(stored.get("marketplace", {}).get("my_gig_url", "")).strip(),
                auto_compare_enabled=bool(stored.get("marketplace", {}).get("auto_compare_enabled", False)),
                auto_compare_interval_minutes=max(
                    5,
                    int(stored.get("marketplace", {}).get("auto_compare_interval_minutes", 5) or 5),
                ),
                serpapi_api_key=self.config.serpapi_api_key or str(stored.get("marketplace", {}).get("serpapi_api_key", "")).strip(),
                serpapi_engine=str(stored.get("marketplace", {}).get("serpapi_engine", self.config.serpapi_engine)).strip() or self.config.serpapi_engine,
                serpapi_num_results=max(
                    1,
                    int(stored.get("marketplace", {}).get("serpapi_num_results", self.config.serpapi_num_results) or self.config.serpapi_num_results),
                ),
            ),
        )

    def get_public_settings(self) -> dict:
        settings = self.get_settings()
        return {
            "events": asdict(settings.events),
            "email": {
                "enabled": settings.email.enabled,
                "configured": bool(
                    settings.email.smtp_host
                    and settings.email.smtp_username
                    and settings.email.from_address
                    and settings.email.to_addresses
                ),
                "smtp_host": settings.email.smtp_host,
                "smtp_port": settings.email.smtp_port,
                "smtp_username": settings.email.smtp_username,
                "from_address": settings.email.from_address,
                "to_addresses": settings.email.to_addresses,
                "use_tls": settings.email.use_tls,
            },
            "slack": {
                "enabled": settings.slack.enabled,
                "configured": bool(settings.slack.webhook_url),
            },
            "whatsapp": {
                "enabled": settings.whatsapp.enabled,
                "configured": bool(
                    settings.whatsapp.access_token
                    and settings.whatsapp.phone_number_id
                    and settings.whatsapp.recipient_number
                ),
                "api_version": settings.whatsapp.api_version,
                "phone_number_id": settings.whatsapp.phone_number_id,
                "recipient_number": settings.whatsapp.recipient_number,
            },
            "ai": {
                "enabled": settings.ai.enabled,
                "configured": self._ai_is_configured(settings.ai),
                "provider": settings.ai.provider,
                "model": settings.ai.model,
                "api_base_url": settings.ai.api_base_url,
            },
            "hostinger": {
                "enabled": settings.hostinger.enabled,
                "configured": bool(settings.hostinger.api_token),
                "api_base_url": settings.hostinger.api_base_url,
                "virtual_machine_id": settings.hostinger.virtual_machine_id,
                "project_name": settings.hostinger.project_name,
                "domain": settings.hostinger.domain,
                "metrics_window_minutes": settings.hostinger.metrics_window_minutes,
            },
            "marketplace": {
                "enabled": settings.marketplace.enabled,
                "search_terms": settings.marketplace.search_terms,
                "max_results": settings.marketplace.max_results,
                "search_url_template": settings.marketplace.search_url_template,
                "reader_enabled": settings.marketplace.reader_enabled,
                "reader_base_url": settings.marketplace.reader_base_url,
                "my_gig_url": settings.marketplace.my_gig_url,
                "auto_compare_enabled": settings.marketplace.auto_compare_enabled,
                "auto_compare_interval_minutes": settings.marketplace.auto_compare_interval_minutes,
                "serpapi_configured": bool(settings.marketplace.serpapi_api_key),
                "serpapi_engine": settings.marketplace.serpapi_engine,
                "serpapi_num_results": settings.marketplace.serpapi_num_results,
            },
        }

    def update_settings(self, payload: dict) -> dict:
        current = self.get_settings()

        events_payload = payload.get("events") or {}
        for field_name in asdict(current.events).keys():
            if field_name in events_payload:
                setattr(current.events, field_name, bool(events_payload[field_name]))

        email_payload = payload.get("email") or {}
        if "enabled" in email_payload:
            current.email.enabled = bool(email_payload["enabled"])
        if "smtp_host" in email_payload:
            current.email.smtp_host = str(email_payload.get("smtp_host", "")).strip() or current.email.smtp_host
        if "smtp_port" in email_payload:
            current.email.smtp_port = int(email_payload.get("smtp_port") or current.email.smtp_port)
        if "smtp_username" in email_payload:
            current.email.smtp_username = str(email_payload.get("smtp_username", "")).strip()
        if "smtp_password" in email_payload and str(email_payload.get("smtp_password", "")).strip():
            current.email.smtp_password = str(email_payload.get("smtp_password", "")).strip()
        if "from_address" in email_payload:
            current.email.from_address = str(email_payload.get("from_address", "")).strip()
        if "to_addresses" in email_payload:
            current.email.to_addresses = self._parse_list(email_payload.get("to_addresses", []))
        if "use_tls" in email_payload:
            current.email.use_tls = bool(email_payload["use_tls"])

        slack_payload = payload.get("slack") or {}
        if "enabled" in slack_payload:
            current.slack.enabled = bool(slack_payload["enabled"])
        if "webhook_url" in slack_payload and str(slack_payload.get("webhook_url", "")).strip():
            current.slack.webhook_url = str(slack_payload.get("webhook_url", "")).strip()

        whatsapp_payload = payload.get("whatsapp") or {}
        if "enabled" in whatsapp_payload:
            current.whatsapp.enabled = bool(whatsapp_payload["enabled"])
        if "access_token" in whatsapp_payload and str(whatsapp_payload.get("access_token", "")).strip():
            current.whatsapp.access_token = str(whatsapp_payload.get("access_token", "")).strip()
        if "phone_number_id" in whatsapp_payload:
            current.whatsapp.phone_number_id = str(whatsapp_payload.get("phone_number_id", "")).strip()
        if "recipient_number" in whatsapp_payload:
            current.whatsapp.recipient_number = str(whatsapp_payload.get("recipient_number", "")).strip()
        if "api_version" in whatsapp_payload:
            current.whatsapp.api_version = str(whatsapp_payload.get("api_version", "v23.0")).strip() or "v23.0"

        ai_payload = payload.get("ai") or {}
        if "enabled" in ai_payload:
            current.ai.enabled = bool(ai_payload["enabled"])
        if "provider" in ai_payload:
            current.ai.provider = str(ai_payload.get("provider", current.ai.provider)).strip() or current.ai.provider
        if "model" in ai_payload:
            current.ai.model = str(ai_payload.get("model", current.ai.model)).strip() or current.ai.model
        if "api_base_url" in ai_payload:
            current.ai.api_base_url = str(ai_payload.get("api_base_url", current.ai.api_base_url)).strip() or current.ai.api_base_url
        if "api_key" in ai_payload and str(ai_payload.get("api_key", "")).strip():
            current.ai.api_key = str(ai_payload.get("api_key", "")).strip()

        hostinger_payload = payload.get("hostinger") or {}
        if "enabled" in hostinger_payload:
            current.hostinger.enabled = bool(hostinger_payload["enabled"])
        if "api_base_url" in hostinger_payload:
            current.hostinger.api_base_url = (
                str(hostinger_payload.get("api_base_url", current.hostinger.api_base_url)).strip()
                or current.hostinger.api_base_url
            )
        if "api_token" in hostinger_payload and str(hostinger_payload.get("api_token", "")).strip():
            current.hostinger.api_token = str(hostinger_payload.get("api_token", "")).strip()
        if "virtual_machine_id" in hostinger_payload:
            current.hostinger.virtual_machine_id = str(hostinger_payload.get("virtual_machine_id", "")).strip()
        if "project_name" in hostinger_payload:
            current.hostinger.project_name = str(hostinger_payload.get("project_name", "")).strip()
        if "domain" in hostinger_payload:
            current.hostinger.domain = str(hostinger_payload.get("domain", "")).strip()
        if "metrics_window_minutes" in hostinger_payload:
            current.hostinger.metrics_window_minutes = max(
                5,
                int(hostinger_payload.get("metrics_window_minutes") or current.hostinger.metrics_window_minutes),
            )

        marketplace_payload = payload.get("marketplace") or {}
        if "enabled" in marketplace_payload:
            current.marketplace.enabled = bool(marketplace_payload["enabled"])
        if "search_terms" in marketplace_payload:
            current.marketplace.search_terms = self._parse_list(marketplace_payload.get("search_terms", []))
        if "max_results" in marketplace_payload:
            current.marketplace.max_results = int(marketplace_payload.get("max_results") or current.marketplace.max_results)
        if "search_url_template" in marketplace_payload:
            current.marketplace.search_url_template = (
                str(marketplace_payload.get("search_url_template", current.marketplace.search_url_template)).strip()
                or current.marketplace.search_url_template
            )
        if "reader_enabled" in marketplace_payload:
            current.marketplace.reader_enabled = bool(marketplace_payload["reader_enabled"])
        if "reader_base_url" in marketplace_payload:
            current.marketplace.reader_base_url = (
                str(marketplace_payload.get("reader_base_url", current.marketplace.reader_base_url)).strip()
                or current.marketplace.reader_base_url
            )
        if "my_gig_url" in marketplace_payload:
            current.marketplace.my_gig_url = str(marketplace_payload.get("my_gig_url", "")).strip()
        if "auto_compare_enabled" in marketplace_payload:
            current.marketplace.auto_compare_enabled = bool(marketplace_payload["auto_compare_enabled"])
        if "auto_compare_interval_minutes" in marketplace_payload:
            current.marketplace.auto_compare_interval_minutes = max(
                5,
                int(marketplace_payload.get("auto_compare_interval_minutes") or current.marketplace.auto_compare_interval_minutes),
            )
        if "serpapi_api_key" in marketplace_payload and str(marketplace_payload.get("serpapi_api_key", "")).strip():
            current.marketplace.serpapi_api_key = str(marketplace_payload.get("serpapi_api_key", "")).strip()
        if "serpapi_engine" in marketplace_payload:
            current.marketplace.serpapi_engine = (
                str(marketplace_payload.get("serpapi_engine", current.marketplace.serpapi_engine)).strip()
                or current.marketplace.serpapi_engine
            )
        if "serpapi_num_results" in marketplace_payload:
            current.marketplace.serpapi_num_results = max(
                1,
                int(marketplace_payload.get("serpapi_num_results") or current.marketplace.serpapi_num_results),
            )

        self._write(current)
        return self.get_public_settings()

    def _default_settings(self) -> NotificationSettings:
        return NotificationSettings(
            events=NotificationEvents(),
            email=EmailSettings(
                enabled=False,
                smtp_host=self.config.email_smtp_host,
                smtp_port=self.config.email_smtp_port,
                smtp_username=self.config.email_smtp_username,
                smtp_password=self.config.email_smtp_password,
                from_address=self.config.email_from_address,
                to_addresses=self._parse_list(self.config.email_to_addresses),
                use_tls=self.config.email_use_tls,
            ),
            slack=SlackSettings(enabled=False, webhook_url=self.config.slack_webhook_url),
            whatsapp=WhatsAppSettings(
                enabled=False,
                access_token=self.config.whatsapp_access_token,
                phone_number_id=self.config.whatsapp_phone_number_id,
                recipient_number=self.config.whatsapp_recipient_number,
                api_version=self.config.whatsapp_api_version,
            ),
            ai=AISettings(
                enabled=False,
                provider=self.config.ai_provider,
                model=self.config.ai_model,
                api_key=self.config.ai_api_key,
                api_base_url=self.config.ai_api_base_url,
            ),
            hostinger=HostingerSettings(
                enabled=self.config.hostinger_enabled,
                api_base_url=self.config.hostinger_api_base_url,
                api_token=self.config.hostinger_api_token,
                virtual_machine_id=self.config.hostinger_virtual_machine_id,
                project_name=self.config.hostinger_project_name,
                domain=self.config.hostinger_domain,
                metrics_window_minutes=self.config.hostinger_metrics_window_minutes,
            ),
            marketplace=MarketplaceSettings(
                enabled=self.config.marketplace_enabled,
                search_terms=self._parse_list(self.config.marketplace_search_terms),
                max_results=self.config.fiverr_marketplace_max_results,
                search_url_template=self.config.fiverr_marketplace_search_url_template,
                reader_enabled=self.config.marketplace_reader_enabled,
                reader_base_url=self.config.marketplace_reader_base_url,
                my_gig_url=self.config.marketplace_my_gig_url,
                auto_compare_enabled=False,
                auto_compare_interval_minutes=5,
                serpapi_api_key=self.config.serpapi_api_key,
                serpapi_engine=self.config.serpapi_engine,
                serpapi_num_results=self.config.serpapi_num_results,
            ),
        )

    def _ai_is_configured(self, settings: AISettings) -> bool:
        if settings.provider == "n8n":
            return bool(settings.api_base_url)
        if settings.provider == "openai":
            return bool(settings.api_key)
        return bool(settings.api_base_url or settings.api_key)

    def _parse_list(self, value) -> list[str]:
        if not value:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [item.strip() for item in str(value).split(",") if item.strip()]

    def _read(self) -> dict:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, settings: NotificationSettings) -> None:
        self.path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
