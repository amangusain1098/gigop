from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


def _ensure_list(value: Any) -> list[Any]:
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [value]


@dataclass(slots=True)
class GigFAQ:
    question: str
    answer: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GigFAQ":
        return cls(
            question=str(data.get("question", "")).strip(),
            answer=str(data.get("answer", "")).strip(),
        )


@dataclass(slots=True)
class GigPackage:
    name: str
    price: float
    delivery_days: int | None = None
    revisions: int | None = None
    highlights: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GigPackage":
        return cls(
            name=str(data.get("name", "")).strip(),
            price=float(data.get("price", 0) or 0),
            delivery_days=data.get("delivery_days"),
            revisions=data.get("revisions"),
            highlights=[str(item).strip() for item in _ensure_list(data.get("highlights")) if str(item).strip()],
        )


@dataclass(slots=True)
class GigAnalytics:
    impressions: int = 0
    clicks: int = 0
    orders: int = 0
    saves: int = 0
    average_response_time_hours: float | None = None
    package_mix: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "GigAnalytics":
        if not data:
            return cls()
        package_mix = {
            str(key): int(value)
            for key, value in (data.get("package_mix") or {}).items()
        }
        return cls(
            impressions=int(data.get("impressions", 0) or 0),
            clicks=int(data.get("clicks", 0) or 0),
            orders=int(data.get("orders", 0) or 0),
            saves=int(data.get("saves", 0) or 0),
            average_response_time_hours=(
                float(data["average_response_time_hours"])
                if data.get("average_response_time_hours") is not None
                else None
            ),
            package_mix=package_mix,
        )


@dataclass(slots=True)
class CompetitorGig:
    title: str
    starting_price: float | None = None
    tags: list[str] = field(default_factory=list)
    rating: float | None = None
    reviews_count: int | None = None
    description_excerpt: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CompetitorGig":
        return cls(
            title=str(data.get("title", "")).strip(),
            starting_price=float(data["starting_price"]) if data.get("starting_price") is not None else None,
            tags=[str(item).strip() for item in _ensure_list(data.get("tags")) if str(item).strip()],
            rating=float(data["rating"]) if data.get("rating") is not None else None,
            reviews_count=int(data["reviews_count"]) if data.get("reviews_count") is not None else None,
            description_excerpt=str(data.get("description_excerpt", "")).strip(),
        )


@dataclass(slots=True)
class ReviewSnippet:
    text: str
    rating: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReviewSnippet":
        rating = data.get("rating")
        return cls(
            text=str(data.get("text", "")).strip(),
            rating=int(rating) if rating is not None else None,
        )


@dataclass(slots=True)
class GigSnapshot:
    niche: str
    title: str
    description: str
    tags: list[str] = field(default_factory=list)
    faq: list[GigFAQ] = field(default_factory=list)
    packages: list[GigPackage] = field(default_factory=list)
    analytics: GigAnalytics = field(default_factory=GigAnalytics)
    competitors: list[CompetitorGig] = field(default_factory=list)
    reviews: list[ReviewSnippet] = field(default_factory=list)
    buyer_messages: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GigSnapshot":
        return cls(
            niche=str(data.get("niche", "WordPress Insights & Page Speed")).strip(),
            title=str(data.get("title", "")).strip(),
            description=str(data.get("description", "")).strip(),
            tags=[str(item).strip() for item in _ensure_list(data.get("tags")) if str(item).strip()],
            faq=[GigFAQ.from_dict(item) for item in _ensure_list(data.get("faq")) if isinstance(item, dict)],
            packages=[GigPackage.from_dict(item) for item in _ensure_list(data.get("packages")) if isinstance(item, dict)],
            analytics=GigAnalytics.from_dict(data.get("analytics")),
            competitors=[
                CompetitorGig.from_dict(item)
                for item in _ensure_list(data.get("competitors"))
                if isinstance(item, dict)
            ],
            reviews=[
                ReviewSnippet.from_dict(item)
                for item in _ensure_list(data.get("reviews"))
                if isinstance(item, dict)
            ],
            buyer_messages=[str(item).strip() for item in _ensure_list(data.get("buyer_messages")) if str(item).strip()],
            goals=[str(item).strip() for item in _ensure_list(data.get("goals")) if str(item).strip()],
        )


@dataclass(slots=True)
class PersonaInsight:
    persona: str
    score: float
    pain_point: str
    emphasis: list[str]


@dataclass(slots=True)
class KeywordSignal:
    keyword: str
    source: str
    trend_score: float | None = None
    search_volume: int | None = None
    keyword_difficulty: float | None = None
    cpc: float | None = None
    competition: float | None = None
    rising: bool = False


@dataclass(slots=True)
class ConnectorStatus:
    connector: str
    status: str
    detail: str


@dataclass(slots=True)
class MarketplaceGig:
    title: str
    url: str = ""
    seller_name: str = ""
    starting_price: float | None = None
    rating: float | None = None
    reviews_count: int | None = None
    delivery_days: int | None = None
    badges: list[str] = field(default_factory=list)
    snippet: str = ""
    matched_term: str = ""
    conversion_proxy_score: float = 0.0
    win_reasons: list[str] = field(default_factory=list)
    rank_position: int | None = None
    page_number: int | None = None
    is_first_page: bool = False
    search_url: str = ""
    why_on_page_one: list[str] = field(default_factory=list)


@dataclass(slots=True)
class GigPageOverview:
    url: str
    title: str
    seller_name: str = ""
    description_excerpt: str = ""
    starting_price: float | None = None
    rating: float | None = None
    reviews_count: int | None = None
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CompetitiveGapAnalysis:
    search_terms: list[str]
    proxy_warning: str
    title_patterns: list[str]
    top_competitors: list[MarketplaceGig]
    why_competitors_win: list[str]
    what_to_implement: list[str]
    my_advantages: list[str]


@dataclass(slots=True)
class LiveResearchBundle:
    keyword_signals: list[KeywordSignal] = field(default_factory=list)
    seller_metrics: GigAnalytics | None = None
    marketplace_gigs: list[MarketplaceGig] = field(default_factory=list)
    connector_status: list[ConnectorStatus] = field(default_factory=list)


@dataclass(slots=True)
class NichePulseReport:
    trending_queries: list[str]
    competitor_gaps: list[str]
    keyword_updates: list[str]
    notes: list[str]
    live_keyword_signals: list[KeywordSignal] = field(default_factory=list)
    data_sources: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ConversionAudit:
    impression_to_click_rate: float | None
    click_to_order_rate: float | None
    findings: list[str]
    actions: list[str]


@dataclass(slots=True)
class OptimizationReport:
    optimization_score: int
    niche_pulse: NichePulseReport
    persona_insights: list[PersonaInsight]
    title_variants: list[str]
    description_recommendations: list[str]
    faq_recommendations: list[str]
    tag_recommendations: list[str]
    conversion_audit: ConversionAudit
    pricing_recommendations: list[str]
    review_actions: list[str]
    review_follow_up_template: str
    external_traffic_actions: list[str]
    weekly_action_plan: list[str]
    caution_notes: list[str]
    competitive_gap_analysis: CompetitiveGapAnalysis | None = None
    ai_overview: dict[str, Any] | None = None
    connector_status: list[ConnectorStatus] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MetricHistoryPoint:
    timestamp: str
    impressions: int
    clicks: int
    orders: int
    ctr: float
    conversion_rate: float


@dataclass(slots=True)
class AgentHealth:
    agent_name: str
    status: str
    last_run_at: str | None = None
    last_error: str = ""
    cost_per_run: float = 0.0


@dataclass(slots=True)
class GeneratedReportFile:
    report_id: str
    generated_at: str
    json_path: str
    markdown_path: str
    html_path: str
    report_type: str = "weekly"


@dataclass(slots=True)
class ScraperActivityEntry:
    timestamp: str
    stage: str
    level: str = "info"
    term: str = ""
    url: str = ""
    message: str = ""
    result_count: int | None = None
    gig_title: str = ""
    seller_name: str = ""
    starting_price: float | None = None
    rating: float | None = None
    debug_html_path: str = ""
    debug_screenshot_path: str = ""


@dataclass(slots=True)
class ScraperRunState:
    status: str = "idle"
    run_id: str = ""
    job_id: str = ""
    started_at: str = ""
    finished_at: str = ""
    search_terms: list[str] = field(default_factory=list)
    last_url: str = ""
    total_results: int = 0
    last_status_message: str = ""
    debug_html_path: str = ""
    debug_screenshot_path: str = ""
    recent_events: list[ScraperActivityEntry] = field(default_factory=list)
    recent_gigs: list[MarketplaceGig] = field(default_factory=list)


@dataclass(slots=True)
class ScraperLogEntry:
    id: int | None = None
    job_id: str = ""
    keyword: str = ""
    status: str = "queued"
    gigs_found: int = 0
    duration_ms: int | None = None
    error_msg: str = ""
    meta_json: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""


@dataclass(slots=True)
class DashboardState:
    snapshot_path: str
    latest_report: dict[str, Any] | None = None
    metrics_history: list[MetricHistoryPoint] = field(default_factory=list)
    agent_health: list[AgentHealth] = field(default_factory=list)
    recent_reports: list[GeneratedReportFile] = field(default_factory=list)
    scraper_run: ScraperRunState = field(default_factory=ScraperRunState)
    gig_comparison: dict[str, Any] | None = None
    comparison_history: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class NotificationEvents:
    pipeline_run: bool = True
    queue_pending: bool = True
    approval_decision: bool = True
    report_generated: bool = True
    error: bool = True


@dataclass(slots=True)
class SlackSettings:
    enabled: bool = False
    webhook_url: str = ""


@dataclass(slots=True)
class EmailSettings:
    enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    from_address: str = ""
    to_addresses: list[str] = field(default_factory=list)
    use_tls: bool = True


@dataclass(slots=True)
class WhatsAppSettings:
    enabled: bool = False
    access_token: str = ""
    phone_number_id: str = ""
    recipient_number: str = ""
    api_version: str = "v23.0"


@dataclass(slots=True)
class AISettings:
    enabled: bool = False
    provider: str = "n8n"
    model: str = "webhook"
    api_key: str = ""
    api_base_url: str = ""


@dataclass(slots=True)
class HostingerSettings:
    enabled: bool = False
    api_base_url: str = "https://developers.hostinger.com"
    api_token: str = ""
    virtual_machine_id: str = ""
    project_name: str = ""
    domain: str = ""
    metrics_window_minutes: int = 60


@dataclass(slots=True)
class MarketplaceSettings:
    enabled: bool = False
    search_terms: list[str] = field(default_factory=list)
    max_results: int = 12
    search_url_template: str = "https://www.fiverr.com/search/gigs?query={query}"
    reader_enabled: bool = True
    reader_base_url: str = "https://r.jina.ai/http://"
    my_gig_url: str = ""
    auto_compare_enabled: bool = False
    auto_compare_interval_minutes: int = 5
    serpapi_api_key: str = ""
    serpapi_engine: str = "google"
    serpapi_num_results: int = 10


@dataclass(slots=True)
class NotificationSettings:
    events: NotificationEvents = field(default_factory=NotificationEvents)
    email: EmailSettings = field(default_factory=EmailSettings)
    slack: SlackSettings = field(default_factory=SlackSettings)
    whatsapp: WhatsAppSettings = field(default_factory=WhatsAppSettings)
    ai: AISettings = field(default_factory=AISettings)
    hostinger: HostingerSettings = field(default_factory=HostingerSettings)
    marketplace: MarketplaceSettings = field(default_factory=MarketplaceSettings)


@dataclass(slots=True)
class NotificationDeliveryResult:
    channel: str
    ok: bool
    detail: str


@dataclass(slots=True)
class ValidationIssue:
    code: str
    message: str
    severity: str = "warning"


@dataclass(slots=True)
class ValidationResult:
    valid: bool
    confidence: int
    issues: list[ValidationIssue] = field(default_factory=list)
    sanitized_output: str = ""


@dataclass(slots=True)
class ApprovalRecord:
    id: str
    agent_name: str
    action_type: str
    current_value: str
    proposed_value: str
    confidence_score: int
    validator_issues: list[ValidationIssue] = field(default_factory=list)
    status: str = "pending"
    created_at: str = ""
    reviewed_at: str | None = None
    reviewer_notes: str = ""
