from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path

from .models import ConnectorStatus

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


if load_dotenv is not None:
    load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _default_training_mirror_dir() -> str:
    configured = os.getenv("COPILOT_TRAINING_LOCAL_MIRROR_DIR")
    if configured is not None and configured.strip():
        return configured.strip()
    if os.name == "nt":
        return str((Path.home() / "GigOptimizerTraining").resolve())
    return ""


@dataclass(slots=True)
class GigOptimizerConfig:
    data_dir: Path = Path("data")
    reports_dir: Path = Path("reports")
    uploads_dir: Path = Path("data/uploads")
    frontend_dist_dir: Path = Path("frontend/dist")
    default_snapshot_path: Path = Path("examples/wordpress_speed_snapshot.json")
    dashboard_state_path: Path = Path("data/dashboard_state.json")
    metrics_history_path: Path = Path("data/metrics_history.json")
    agent_health_path: Path = Path("data/agent_health.json")
    integration_settings_path: Path = Path("data/integrations.json")
    database_url: str = "sqlite:///data/gigoptimizer_blueprint.db"
    redis_url: str = ""
    rq_queue_name: str = "gigoptimizer"
    rq_scheduler_queue_name: str = "gigoptimizer-scheduler"
    job_queue_eager: bool = True
    job_progress_channel: str = "gigoptimizer:events"
    browserless_enabled: bool = False
    browserless_ws_url: str = ""
    browserless_api_token: str = ""
    sentry_dsn: str = ""
    frontend_dev_url: str = "http://127.0.0.1:5173"
    google_trends_geo: str = ""
    google_trends_timeframe: str = "today 3-m"
    google_trends_hl: str = "en-US"
    google_trends_tz: int = 330
    google_trends_max_queries: int = 5
    semrush_api_key: str = ""
    semrush_database: str = "us"
    semrush_timeout_seconds: int = 30
    serpapi_api_key: str = ""
    serpapi_engine: str = "google"
    serpapi_num_results: int = 10
    marketplace_reader_enabled: bool = True
    marketplace_reader_base_url: str = "https://r.jina.ai/http://"
    fiverr_login_url: str = "https://www.fiverr.com/login"
    fiverr_analytics_url: str = ""
    fiverr_email: str = ""
    fiverr_password: str = ""
    fiverr_storage_state_path: Path = Path("playwright/.auth/fiverr-state.json")
    fiverr_headless: bool = True
    fiverr_email_selector: str = 'input[type="email"], input[name="username"]'
    fiverr_password_selector: str = 'input[type="password"]'
    fiverr_submit_selector: str = 'button[type="submit"]'
    fiverr_impressions_selector: str = '[data-testid="analytics-impressions"]'
    fiverr_clicks_selector: str = '[data-testid="analytics-clicks"]'
    fiverr_orders_selector: str = '[data-testid="analytics-orders"]'
    fiverr_saves_selector: str = '[data-testid="analytics-saves"]'
    fiverr_response_time_selector: str = '[data-testid="analytics-response-time"]'
    fiverr_marketplace_search_url_template: str = "https://www.fiverr.com/search/gigs?query={query}"
    fiverr_marketplace_card_selector: str = 'article'
    fiverr_marketplace_title_selector: str = 'h3, [data-testid="gig-card-title"]'
    fiverr_marketplace_price_selector: str = '[data-testid="gig-card-price"], [class*="price"]'
    fiverr_marketplace_rating_selector: str = '[data-testid="gig-card-rating"], [class*="rating"]'
    fiverr_marketplace_reviews_selector: str = '[data-testid="gig-card-reviews"], [class*="reviews"]'
    fiverr_marketplace_link_selector: str = 'a[href*="/gig/"], a[href*="/services/"]'
    fiverr_marketplace_seller_selector: str = '[data-testid="seller-name"], [class*="seller"]'
    fiverr_marketplace_badge_selector: str = '[data-testid="seller-level"], [class*="badge"], [class*="level"]'
    fiverr_marketplace_snippet_selector: str = 'p, [data-testid="gig-card-description"]'
    fiverr_marketplace_delivery_selector: str = '[data-testid="delivery-time"], [class*="delivery"]'
    fiverr_marketplace_max_results: int = 12
    fiverr_marketplace_max_retries: int = 3
    fiverr_marketplace_retry_base_delay_seconds: int = 2
    fiverr_marketplace_request_delay_ms: int = 1500
    fiverr_marketplace_profile_dir: Path = Path("playwright/.marketplace-profile")
    fiverr_marketplace_verification_timeout_seconds: int = 600
    fiverr_marketplace_headless: bool = True
    fiverr_marketplace_browser_channel: str = "auto"
    fiverr_marketplace_slow_mo_ms: int = 250
    approval_queue_db_path: Path = Path("data/approval_queue.db")
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8001
    app_base_url: str = ""
    app_force_https: bool = False
    app_trusted_hosts: str = ""
    app_forwarded_allow_ips: str = "*"
    app_auth_enabled: bool = False
    app_cookie_secure: bool = False
    app_session_ttl_minutes: int = 720
    app_session_secret: str = ""
    app_admin_username: str = "admin"
    app_admin_password: str = ""
    app_admin_password_hash: str = ""
    slack_webhook_url: str = ""
    email_smtp_host: str = "smtp.gmail.com"
    email_smtp_port: int = 587
    email_smtp_username: str = ""
    email_smtp_password: str = ""
    email_from_address: str = ""
    email_to_addresses: str = ""
    email_use_tls: bool = True
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_recipient_number: str = ""
    whatsapp_api_version: str = "v23.0"
    ai_provider: str = "n8n"
    ai_model: str = "webhook"
    ai_api_key: str = ""
    ai_api_base_url: str = ""
    n8n_webhook_secret: str = "change_me"
    google_pagespeed_api_key: str = ""
    hostinger_enabled: bool = False
    hostinger_api_base_url: str = "https://developers.hostinger.com"
    hostinger_api_token: str = ""
    hostinger_virtual_machine_id: str = ""
    hostinger_project_name: str = ""
    hostinger_domain: str = ""
    hostinger_metrics_window_minutes: int = 60
    hostinger_request_timeout_seconds: int = 20
    marketplace_enabled: bool = False
    marketplace_search_terms: str = ""
    marketplace_my_gig_url: str = ""
    manhwa_enabled: bool = True
    manhwa_auto_sync_enabled: bool = True
    manhwa_sync_interval_minutes: int = 30
    knowledge_max_upload_bytes: int = 5 * 1024 * 1024
    knowledge_chunk_chars: int = 900
    knowledge_chunk_overlap_chars: int = 150
    copilot_learning_enabled: bool = True
    copilot_learning_interval_minutes: int = 30
    copilot_training_enabled: bool = True
    copilot_training_export_interval_minutes: int = 180
    copilot_training_local_mirror_enabled: bool = False
    copilot_training_local_mirror_dir: Path | None = None
    extension_enabled: bool = True
    extension_api_token: str = ""
    extension_max_gigs_per_import: int = 25
    extension_import_ttl_seconds: int = 900
    feature_scraper_visibility: bool = True
    feature_keyword_scoring: bool = True
    feature_compare_timeline: bool = True
    feature_scraper_sse: bool = True

    @classmethod
    def from_env(cls) -> "GigOptimizerConfig":
        data_dir = Path(os.getenv("DATA_DIR", "data"))
        reports_dir = Path(os.getenv("REPORTS_DIR", "reports"))
        return cls(
            data_dir=data_dir,
            reports_dir=reports_dir,
            uploads_dir=Path(os.getenv("UPLOADS_DIR", str(data_dir / "uploads"))),
            frontend_dist_dir=Path(os.getenv("FRONTEND_DIST_DIR", "frontend/dist")),
            default_snapshot_path=Path(
                os.getenv("DEFAULT_SNAPSHOT_PATH", "examples/wordpress_speed_snapshot.json")
            ),
            dashboard_state_path=Path(
                os.getenv("DASHBOARD_STATE_PATH", str(data_dir / "dashboard_state.json"))
            ),
            metrics_history_path=Path(
                os.getenv("METRICS_HISTORY_PATH", str(data_dir / "metrics_history.json"))
            ),
            agent_health_path=Path(
                os.getenv("AGENT_HEALTH_PATH", str(data_dir / "agent_health.json"))
            ),
            integration_settings_path=Path(
                os.getenv("INTEGRATION_SETTINGS_PATH", str(data_dir / "integrations.json"))
            ),
            database_url=(
                os.getenv("DATABASE_URL", f"sqlite:///{(data_dir / 'gigoptimizer_blueprint.db').as_posix()}")
                .strip()
                or f"sqlite:///{(data_dir / 'gigoptimizer_blueprint.db').as_posix()}"
            ),
            redis_url=os.getenv("REDIS_URL", "").strip(),
            rq_queue_name=os.getenv("RQ_QUEUE_NAME", "gigoptimizer").strip() or "gigoptimizer",
            rq_scheduler_queue_name=os.getenv("RQ_SCHEDULER_QUEUE_NAME", "gigoptimizer-scheduler").strip() or "gigoptimizer-scheduler",
            job_queue_eager=_get_bool("JOB_QUEUE_EAGER", True),
            job_progress_channel=os.getenv("JOB_PROGRESS_CHANNEL", "gigoptimizer:events").strip() or "gigoptimizer:events",
            browserless_enabled=_get_bool("BROWSERLESS_ENABLED", False),
            browserless_ws_url=os.getenv("BROWSERLESS_WS_URL", "").strip(),
            browserless_api_token=os.getenv("BROWSERLESS_API_TOKEN", "").strip(),
            sentry_dsn=os.getenv("SENTRY_DSN", "").strip(),
            frontend_dev_url=os.getenv("FRONTEND_DEV_URL", "http://127.0.0.1:5173").strip() or "http://127.0.0.1:5173",
            google_trends_geo=os.getenv("GOOGLE_TRENDS_GEO", "").strip(),
            google_trends_timeframe=os.getenv("GOOGLE_TRENDS_TIMEFRAME", "today 3-m").strip(),
            google_trends_hl=os.getenv("GOOGLE_TRENDS_HL", "en-US").strip(),
            google_trends_tz=_get_int("GOOGLE_TRENDS_TZ", 330),
            google_trends_max_queries=_get_int("GOOGLE_TRENDS_MAX_QUERIES", 5),
            semrush_api_key=os.getenv("SEMRUSH_API_KEY", "").strip(),
            semrush_database=os.getenv("SEMRUSH_DATABASE", "us").strip(),
            semrush_timeout_seconds=_get_int("SEMRUSH_TIMEOUT_SECONDS", 30),
            serpapi_api_key=os.getenv("SERPAPI_API_KEY", "").strip(),
            serpapi_engine=os.getenv("SERPAPI_ENGINE", "google").strip() or "google",
            serpapi_num_results=_get_int("SERPAPI_NUM_RESULTS", 10),
            marketplace_reader_enabled=_get_bool("MARKETPLACE_READER_ENABLED", True),
            marketplace_reader_base_url=(
                os.getenv("MARKETPLACE_READER_BASE_URL", "https://r.jina.ai/http://").strip()
                or "https://r.jina.ai/http://"
            ),
            fiverr_login_url=os.getenv("FIVERR_LOGIN_URL", "https://www.fiverr.com/login").strip(),
            fiverr_analytics_url=os.getenv("FIVERR_ANALYTICS_URL", "").strip(),
            fiverr_email=os.getenv("FIVERR_EMAIL", "").strip(),
            fiverr_password=os.getenv("FIVERR_PASSWORD", "").strip(),
            fiverr_storage_state_path=Path(
                os.getenv("FIVERR_STORAGE_STATE_PATH", "playwright/.auth/fiverr-state.json")
            ),
            fiverr_headless=_get_bool("FIVERR_HEADLESS", True),
            fiverr_email_selector=os.getenv(
                "FIVERR_EMAIL_SELECTOR",
                'input[type="email"], input[name="username"]',
            ).strip(),
            fiverr_password_selector=os.getenv(
                "FIVERR_PASSWORD_SELECTOR",
                'input[type="password"]',
            ).strip(),
            fiverr_submit_selector=os.getenv(
                "FIVERR_SUBMIT_SELECTOR",
                'button[type="submit"]',
            ).strip(),
            fiverr_impressions_selector=os.getenv(
                "FIVERR_IMPRESSIONS_SELECTOR",
                '[data-testid="analytics-impressions"]',
            ).strip(),
            fiverr_clicks_selector=os.getenv(
                "FIVERR_CLICKS_SELECTOR",
                '[data-testid="analytics-clicks"]',
            ).strip(),
            fiverr_orders_selector=os.getenv(
                "FIVERR_ORDERS_SELECTOR",
                '[data-testid="analytics-orders"]',
            ).strip(),
            fiverr_saves_selector=os.getenv(
                "FIVERR_SAVES_SELECTOR",
                '[data-testid="analytics-saves"]',
            ).strip(),
            fiverr_response_time_selector=os.getenv(
                "FIVERR_RESPONSE_TIME_SELECTOR",
                '[data-testid="analytics-response-time"]',
            ).strip(),
            fiverr_marketplace_search_url_template=os.getenv(
                "FIVERR_MARKETPLACE_SEARCH_URL_TEMPLATE",
                "https://www.fiverr.com/search/gigs?query={query}",
            ).strip(),
            fiverr_marketplace_card_selector=os.getenv(
                "FIVERR_MARKETPLACE_CARD_SELECTOR",
                "article",
            ).strip(),
            fiverr_marketplace_title_selector=os.getenv(
                "FIVERR_MARKETPLACE_TITLE_SELECTOR",
                'h3, [data-testid="gig-card-title"]',
            ).strip(),
            fiverr_marketplace_price_selector=os.getenv(
                "FIVERR_MARKETPLACE_PRICE_SELECTOR",
                '[data-testid="gig-card-price"], [class*="price"]',
            ).strip(),
            fiverr_marketplace_rating_selector=os.getenv(
                "FIVERR_MARKETPLACE_RATING_SELECTOR",
                '[data-testid="gig-card-rating"], [class*="rating"]',
            ).strip(),
            fiverr_marketplace_reviews_selector=os.getenv(
                "FIVERR_MARKETPLACE_REVIEWS_SELECTOR",
                '[data-testid="gig-card-reviews"], [class*="reviews"]',
            ).strip(),
            fiverr_marketplace_link_selector=os.getenv(
                "FIVERR_MARKETPLACE_LINK_SELECTOR",
                'a[href*="/gig/"], a[href*="/services/"]',
            ).strip(),
            fiverr_marketplace_seller_selector=os.getenv(
                "FIVERR_MARKETPLACE_SELLER_SELECTOR",
                '[data-testid="seller-name"], [class*="seller"]',
            ).strip(),
            fiverr_marketplace_badge_selector=os.getenv(
                "FIVERR_MARKETPLACE_BADGE_SELECTOR",
                '[data-testid="seller-level"], [class*="badge"], [class*="level"]',
            ).strip(),
            fiverr_marketplace_snippet_selector=os.getenv(
                "FIVERR_MARKETPLACE_SNIPPET_SELECTOR",
                'p, [data-testid="gig-card-description"]',
            ).strip(),
            fiverr_marketplace_delivery_selector=os.getenv(
                "FIVERR_MARKETPLACE_DELIVERY_SELECTOR",
                '[data-testid="delivery-time"], [class*="delivery"]',
            ).strip(),
            fiverr_marketplace_max_results=_get_int("FIVERR_MARKETPLACE_MAX_RESULTS", 12),
            fiverr_marketplace_max_retries=_get_int("FIVERR_MARKETPLACE_MAX_RETRIES", 3),
            fiverr_marketplace_retry_base_delay_seconds=_get_int("FIVERR_MARKETPLACE_RETRY_BASE_DELAY_SECONDS", 2),
            fiverr_marketplace_request_delay_ms=_get_int("FIVERR_MARKETPLACE_REQUEST_DELAY_MS", 1500),
            fiverr_marketplace_profile_dir=Path(
                os.getenv("FIVERR_MARKETPLACE_PROFILE_DIR", "playwright/.marketplace-profile")
            ),
            fiverr_marketplace_verification_timeout_seconds=_get_int(
                "FIVERR_MARKETPLACE_VERIFICATION_TIMEOUT_SECONDS",
                600,
            ),
            fiverr_marketplace_headless=_get_bool("FIVERR_MARKETPLACE_HEADLESS", True),
            fiverr_marketplace_browser_channel=(
                os.getenv("FIVERR_MARKETPLACE_BROWSER_CHANNEL", "auto").strip().lower() or "auto"
            ),
            fiverr_marketplace_slow_mo_ms=_get_int("FIVERR_MARKETPLACE_SLOW_MO_MS", 250),
            approval_queue_db_path=Path(
                os.getenv("APPROVAL_QUEUE_DB_PATH", "data/approval_queue.db")
            ),
            app_env=os.getenv("APP_ENV", "development").strip().lower() or "development",
            app_host=os.getenv("APP_HOST", "127.0.0.1").strip() or "127.0.0.1",
            app_port=_get_int("APP_PORT", 8001),
            app_base_url=os.getenv("APP_BASE_URL", "").strip(),
            app_force_https=_get_bool("APP_FORCE_HTTPS", False),
            app_trusted_hosts=os.getenv("APP_TRUSTED_HOSTS", "").strip(),
            app_forwarded_allow_ips=os.getenv("APP_FORWARDED_ALLOW_IPS", "*").strip() or "*",
            app_auth_enabled=_get_bool("APP_AUTH_ENABLED", False),
            app_cookie_secure=_get_bool("APP_COOKIE_SECURE", False),
            app_session_ttl_minutes=_get_int("APP_SESSION_TTL_MINUTES", 720),
            app_session_secret=os.getenv("APP_SESSION_SECRET", "").strip(),
            app_admin_username=os.getenv("APP_ADMIN_USERNAME", "admin").strip() or "admin",
            app_admin_password=os.getenv("APP_ADMIN_PASSWORD", "").strip(),
            app_admin_password_hash=os.getenv("APP_ADMIN_PASSWORD_HASH", "").strip(),
            slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL", "").strip(),
            email_smtp_host=os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com").strip() or "smtp.gmail.com",
            email_smtp_port=_get_int("EMAIL_SMTP_PORT", 587),
            email_smtp_username=os.getenv("EMAIL_SMTP_USERNAME", "").strip(),
            email_smtp_password=os.getenv("EMAIL_SMTP_PASSWORD", "").strip(),
            email_from_address=os.getenv("EMAIL_FROM_ADDRESS", "").strip(),
            email_to_addresses=os.getenv("EMAIL_TO_ADDRESSES", "").strip(),
            email_use_tls=_get_bool("EMAIL_USE_TLS", True),
            whatsapp_access_token=os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip(),
            whatsapp_phone_number_id=os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip(),
            whatsapp_recipient_number=os.getenv("WHATSAPP_RECIPIENT_NUMBER", "").strip(),
            whatsapp_api_version=os.getenv("WHATSAPP_API_VERSION", "v23.0").strip() or "v23.0",
            ai_provider=os.getenv("AI_PROVIDER", "n8n").strip() or "n8n",
            ai_model=os.getenv("AI_MODEL", "webhook").strip() or "webhook",
            ai_api_key=os.getenv("AI_API_KEY", "").strip(),
            ai_api_base_url=os.getenv("AI_API_BASE_URL", "").strip(),
            n8n_webhook_secret=os.getenv("N8N_WEBHOOK_SECRET", "change_me").strip() or "change_me",
            google_pagespeed_api_key=os.getenv("GOOGLE_PAGESPEED_API_KEY", "").strip(),
            hostinger_enabled=_get_bool("HOSTINGER_ENABLED", False),
            hostinger_api_base_url=(
                os.getenv("HOSTINGER_API_BASE_URL", "https://developers.hostinger.com").strip()
                or "https://developers.hostinger.com"
            ),
            hostinger_api_token=os.getenv("HOSTINGER_API_TOKEN", "").strip(),
            hostinger_virtual_machine_id=os.getenv("HOSTINGER_VIRTUAL_MACHINE_ID", "").strip(),
            hostinger_project_name=os.getenv("HOSTINGER_PROJECT_NAME", "").strip(),
            hostinger_domain=os.getenv("HOSTINGER_DOMAIN", "").strip(),
            hostinger_metrics_window_minutes=_get_int("HOSTINGER_METRICS_WINDOW_MINUTES", 60),
            hostinger_request_timeout_seconds=_get_int("HOSTINGER_REQUEST_TIMEOUT_SECONDS", 20),
            marketplace_enabled=_get_bool("MARKETPLACE_ENABLED", False),
            marketplace_search_terms=os.getenv("MARKETPLACE_SEARCH_TERMS", "").strip(),
            marketplace_my_gig_url=os.getenv("MARKETPLACE_MY_GIG_URL", "").strip(),
            manhwa_enabled=_get_bool("MANHWA_ENABLED", True),
            manhwa_auto_sync_enabled=_get_bool("MANHWA_AUTO_SYNC_ENABLED", True),
            manhwa_sync_interval_minutes=_get_int("MANHWA_SYNC_INTERVAL_MINUTES", 30),
            knowledge_max_upload_bytes=_get_int("KNOWLEDGE_MAX_UPLOAD_BYTES", 5 * 1024 * 1024),
            knowledge_chunk_chars=_get_int("KNOWLEDGE_CHUNK_CHARS", 900),
            knowledge_chunk_overlap_chars=_get_int("KNOWLEDGE_CHUNK_OVERLAP_CHARS", 150),
            copilot_learning_enabled=_get_bool("COPILOT_LEARNING_ENABLED", True),
            copilot_learning_interval_minutes=_get_int("COPILOT_LEARNING_INTERVAL_MINUTES", 30),
            copilot_training_enabled=_get_bool("COPILOT_TRAINING_ENABLED", True),
            copilot_training_export_interval_minutes=_get_int("COPILOT_TRAINING_EXPORT_INTERVAL_MINUTES", 180),
            copilot_training_local_mirror_enabled=_get_bool(
                "COPILOT_TRAINING_LOCAL_MIRROR_ENABLED",
                bool(_default_training_mirror_dir()),
            ),
            copilot_training_local_mirror_dir=(
                Path(_default_training_mirror_dir()).expanduser()
                if _default_training_mirror_dir()
                else None
            ),
            extension_enabled=_get_bool("EXTENSION_ENABLED", True),
            extension_api_token=os.getenv("EXTENSION_API_TOKEN", "").strip(),
            extension_max_gigs_per_import=_get_int("EXTENSION_MAX_GIGS_PER_IMPORT", 25),
            extension_import_ttl_seconds=_get_int("EXTENSION_IMPORT_TTL_SECONDS", 900),
            feature_scraper_visibility=_get_bool("FEATURE_SCRAPER_VISIBILITY", True),
            feature_keyword_scoring=_get_bool("FEATURE_KEYWORD_SCORING", True),
            feature_compare_timeline=_get_bool("FEATURE_COMPARE_TIMELINE", True),
            feature_scraper_sse=_get_bool("FEATURE_SCRAPER_SSE", True),
        )

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def trusted_hosts_list(self) -> list[str]:
        hosts = [item.strip() for item in self.app_trusted_hosts.split(",") if item.strip()]
        if self.app_base_url:
            from urllib.parse import urlparse

            parsed = urlparse(self.app_base_url)
            if parsed.hostname and parsed.hostname not in hosts:
                hosts.append(parsed.hostname)
        return hosts

    def validate_credentials(self) -> list[ConnectorStatus]:
        return [
            self._validate_database(),
            self._validate_redis(),
            self._validate_hostinger(),
            self._validate_google_trends(),
            self._validate_semrush(),
            self._validate_serpapi(),
            self._validate_marketplace_reader(),
            self._validate_browserless(),
            self._validate_fiverr(),
            self._validate_extension_ingest(),
            self._validate_manhwa(),
            self._validate_copilot_learning(),
            self._validate_copilot_training(),
        ]

    def _validate_database(self) -> ConnectorStatus:
        if self.database_url.startswith("sqlite"):
            return ConnectorStatus(
                connector="database",
                status="active",
                detail=f"active (sqlite fallback: {self.database_url})",
            )
        if self.database_url.startswith(("postgresql://", "postgres://", "postgresql+", "postgres+")):
            return ConnectorStatus(
                connector="database",
                status="active",
                detail="active (postgresql configured)",
            )
        return ConnectorStatus(
            connector="database",
            status="warning",
            detail=f"warning (DATABASE_URL uses an unrecognized scheme: {self.database_url})",
        )

    def _validate_redis(self) -> ConnectorStatus:
        if not self.redis_url:
            return ConnectorStatus(
                connector="redis",
                status="skipped",
                detail="skipped (REDIS_URL not set, local in-process fallback will be used)",
            )
        return ConnectorStatus(
            connector="redis",
            status="active",
            detail=f"active (queue={self.rq_queue_name}, channel={self.job_progress_channel})",
        )

    def _validate_google_trends(self) -> ConnectorStatus:
        if self._module_available("pytrends.request"):
            return ConnectorStatus(
                connector="google_trends",
                status="active",
                detail="active (no key required)",
            )
        return ConnectorStatus(
            connector="google_trends",
            status="skipped",
            detail="skipped (install the optional 'live' dependencies to enable pytrends)",
        )

    def _validate_hostinger(self) -> ConnectorStatus:
        if not self.hostinger_enabled:
            return ConnectorStatus(
                connector="hostinger",
                status="skipped",
                detail="skipped (HOSTINGER_ENABLED is false)",
            )
        if not self.hostinger_api_token:
            return ConnectorStatus(
                connector="hostinger",
                status="warning",
                detail="warning (HOSTINGER_API_TOKEN not set)",
            )
        if any(char.isspace() for char in self.hostinger_api_token):
            return ConnectorStatus(
                connector="hostinger",
                status="warning",
                detail="warning (HOSTINGER_API_TOKEN contains whitespace and looks malformed)",
            )
        return ConnectorStatus(
            connector="hostinger",
            status="active",
            detail=(
                "active "
                f"(base={self.hostinger_api_base_url}, vm={self.hostinger_virtual_machine_id or 'auto'}, "
                f"project={self.hostinger_project_name or 'n/a'})"
            ),
        )

    def _validate_semrush(self) -> ConnectorStatus:
        if not self.semrush_api_key:
            return ConnectorStatus(
                connector="semrush",
                status="skipped",
                detail="skipped (SEMRUSH_API_KEY not set)",
            )
        if any(char.isspace() for char in self.semrush_api_key):
            return ConnectorStatus(
                connector="semrush",
                status="warning",
                detail="warning (SEMRUSH_API_KEY contains whitespace and looks malformed)",
            )
        if len(self.semrush_api_key) < 12:
            return ConnectorStatus(
                connector="semrush",
                status="warning",
                detail="warning (SEMRUSH_API_KEY looks unusually short; verify it before running live mode)",
            )
        return ConnectorStatus(
            connector="semrush",
            status="active",
            detail=f"active (database={self.semrush_database})",
        )

    def _validate_serpapi(self) -> ConnectorStatus:
        if not self.serpapi_api_key:
            return ConnectorStatus(
                connector="serpapi",
                status="skipped",
                detail="skipped (SERPAPI_API_KEY not set)",
            )
        if any(char.isspace() for char in self.serpapi_api_key):
            return ConnectorStatus(
                connector="serpapi",
                status="warning",
                detail="warning (SERPAPI_API_KEY contains whitespace and looks malformed)",
            )
        if len(self.serpapi_api_key) < 16:
            return ConnectorStatus(
                connector="serpapi",
                status="warning",
                detail="warning (SERPAPI_API_KEY looks unusually short; verify it before using SerpApi discovery)",
            )
        return ConnectorStatus(
            connector="serpapi",
            status="active",
            detail=f"active (engine={self.serpapi_engine}, num={self.serpapi_num_results})",
        )

    def _validate_marketplace_reader(self) -> ConnectorStatus:
        if not self.marketplace_reader_enabled:
            return ConnectorStatus(
                connector="marketplace_reader",
                status="skipped",
                detail="skipped (MARKETPLACE_READER_ENABLED is false)",
            )
        if not self.marketplace_reader_base_url:
            return ConnectorStatus(
                connector="marketplace_reader",
                status="warning",
                detail="warning (MARKETPLACE_READER_BASE_URL is blank)",
            )
        if not self.marketplace_reader_base_url.startswith("https://"):
            return ConnectorStatus(
                connector="marketplace_reader",
                status="warning",
                detail="warning (MARKETPLACE_READER_BASE_URL should use https://)",
            )
        return ConnectorStatus(
            connector="marketplace_reader",
            status="active",
            detail=f"active (reader base={self.marketplace_reader_base_url})",
        )

    def _validate_browserless(self) -> ConnectorStatus:
        if not self.browserless_enabled:
            return ConnectorStatus(
                connector="browserless",
                status="skipped",
                detail="skipped (BROWSERLESS_ENABLED is false)",
            )
        if not self.browserless_ws_url:
            return ConnectorStatus(
                connector="browserless",
                status="warning",
                detail="warning (BROWSERLESS_ENABLED is true but BROWSERLESS_WS_URL is not set)",
            )
        return ConnectorStatus(
            connector="browserless",
            status="active",
            detail="active (remote Browserless endpoint configured)",
        )

    def _validate_fiverr(self) -> ConnectorStatus:
        storage_state_exists = self.fiverr_storage_state_path.exists()
        has_email = bool(self.fiverr_email)
        has_password = bool(self.fiverr_password)

        if not self.fiverr_analytics_url:
            return ConnectorStatus(
                connector="fiverr",
                status="skipped",
                detail="skipped (FIVERR_ANALYTICS_URL not set)",
            )
        if storage_state_exists:
            return ConnectorStatus(
                connector="fiverr",
                status="active",
                detail=f"active (using saved storage state at {self.fiverr_storage_state_path})",
            )
        if has_email != has_password:
            return ConnectorStatus(
                connector="fiverr",
                status="warning",
                detail="warning (set both FIVERR_EMAIL and FIVERR_PASSWORD or use a saved storage state)",
            )
        if has_email and "@" not in self.fiverr_email:
            return ConnectorStatus(
                connector="fiverr",
                status="warning",
                detail="warning (FIVERR_EMAIL does not look valid)",
            )
        if has_email and has_password:
            return ConnectorStatus(
                connector="fiverr",
                status="active",
                detail="active (email/password login configured)",
            )
        return ConnectorStatus(
            connector="fiverr",
            status="skipped",
            detail="skipped (FIVERR_EMAIL not set and no saved storage state found)",
        )

    def _validate_extension_ingest(self) -> ConnectorStatus:
        if not self.extension_enabled:
            return ConnectorStatus(
                connector="browser_extension",
                status="skipped",
                detail="skipped (EXTENSION_ENABLED is false)",
            )
        if not self.extension_api_token:
            return ConnectorStatus(
                connector="browser_extension",
                status="warning",
                detail="warning (EXTENSION_API_TOKEN not set)",
            )
        if len(self.extension_api_token) < 16 or any(char.isspace() for char in self.extension_api_token):
            return ConnectorStatus(
                connector="browser_extension",
                status="warning",
                detail="warning (EXTENSION_API_TOKEN looks malformed; rotate or replace it before using the extension)",
            )
        return ConnectorStatus(
            connector="browser_extension",
            status="active",
            detail=f"active (imports up to {max(1, self.extension_max_gigs_per_import)} gigs per page)",
        )

    def _validate_manhwa(self) -> ConnectorStatus:
        if not self.manhwa_enabled:
            return ConnectorStatus(
                connector="manhwa_portal",
                status="skipped",
                detail="skipped (MANHWA_ENABLED is false)",
            )
        if not self.manhwa_auto_sync_enabled:
            return ConnectorStatus(
                connector="manhwa_portal",
                status="warning",
                detail="warning (MANHWA_AUTO_SYNC_ENABLED is false, manual sync only)",
            )
        return ConnectorStatus(
            connector="manhwa_portal",
            status="active",
            detail=f"active (auto sync every {max(5, self.manhwa_sync_interval_minutes)} minutes)",
        )

    def _validate_copilot_learning(self) -> ConnectorStatus:
        if not self.copilot_learning_enabled:
            return ConnectorStatus(
                connector="copilot_learning",
                status="skipped",
                detail="skipped (COPILOT_LEARNING_ENABLED is false)",
            )
        return ConnectorStatus(
            connector="copilot_learning",
            status="active",
            detail=f"active (educational feed sync every {max(5, self.copilot_learning_interval_minutes)} minutes)",
        )

    def _validate_copilot_training(self) -> ConnectorStatus:
        if not self.copilot_training_enabled:
            return ConnectorStatus(
                connector="copilot_training",
                status="skipped",
                detail="skipped (COPILOT_TRAINING_ENABLED is false)",
            )
        return ConnectorStatus(
            connector="copilot_training",
            status="active",
            detail=(
                "active "
                f"(dataset export every {max(15, self.copilot_training_export_interval_minutes)} minutes when scheduler is running"
                + (
                    f"; laptop mirror: {self.copilot_training_local_mirror_dir}"
                    if self.copilot_training_local_mirror_enabled and self.copilot_training_local_mirror_dir
                    else ""
                )
                + ")"
            ),
        )

    def _module_available(self, module_name: str) -> bool:
        try:
            return importlib.util.find_spec(module_name) is not None
        except ModuleNotFoundError:
            return False
