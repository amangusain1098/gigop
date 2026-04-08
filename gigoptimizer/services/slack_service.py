from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..models import NotificationDeliveryResult
from .settings_service import SettingsService


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SlackService:
    def __init__(
        self,
        settings_service: SettingsService,
        *,
        timeout_seconds: int = 10,
        max_attempts: int = 3,
        retry_delays: tuple[float, ...] = (0.5, 1.5, 3.0),
    ) -> None:
        self.settings_service = settings_service
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, max_attempts)
        self.retry_delays = retry_delays

    def send_slack_message(self, event_type: str, payload: dict[str, Any]) -> NotificationDeliveryResult:
        settings = self.settings_service.get_settings().slack
        webhook_url = settings.webhook_url.strip()
        force_enabled = bool(self.settings_service.config.slack_webhook_url.strip())
        if not webhook_url:
            return NotificationDeliveryResult(
                channel="slack",
                ok=False,
                detail="Slack webhook URL is not configured.",
            )
        if not settings.enabled and not force_enabled:
            return NotificationDeliveryResult(
                channel="slack",
                ok=False,
                detail="Slack notifications are disabled.",
            )

        request_payload = self._build_message_payload(event_type=event_type, payload=payload)
        return self._post_payload(webhook_url=webhook_url, payload=request_payload)

    def send_plain_text(self, title: str, lines: list[str]) -> NotificationDeliveryResult:
        payload = {
            "title": title,
            "lines": lines,
            "generated_at": utc_now_iso(),
        }
        return self.send_slack_message("generic_notification", payload)

    def _post_payload(self, *, webhook_url: str, payload: dict[str, Any]) -> NotificationDeliveryResult:
        encoded_payload = json.dumps(payload).encode("utf-8")
        request = Request(
            webhook_url,
            data=encoded_payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        last_error = "Slack delivery failed."
        for attempt in range(1, self.max_attempts + 1):
            try:
                with urlopen(request, timeout=self.timeout_seconds) as response:
                    status = getattr(response, "status", 200)
                    detail = f"Slack notification sent ({status})."
                    return NotificationDeliveryResult(
                        channel="slack",
                        ok=200 <= status < 300,
                        detail=detail,
                    )
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else str(exc)
                last_error = body or str(exc)
                if exc.code < 500:
                    break
            except URLError as exc:
                last_error = str(exc.reason)
            except Exception as exc:  # pragma: no cover - defensive fallback
                last_error = str(exc)
            if attempt < self.max_attempts:
                time.sleep(self.retry_delays[min(attempt - 1, len(self.retry_delays) - 1)])
        return NotificationDeliveryResult(channel="slack", ok=False, detail=last_error)

    def _build_message_payload(self, *, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = (event_type or "generic_notification").strip().lower()
        if normalized == "comparison_complete":
            return self._comparison_complete_payload(payload)
        if normalized == "high_impact_action":
            return self._high_impact_action_payload(payload)
        if normalized == "system_error":
            return self._system_error_payload(payload)
        if normalized == "weekly_report":
            return self._weekly_report_payload(payload)
        return self._generic_payload(payload)

    def _comparison_complete_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        recommended_title = self._truncate(str(payload.get("recommended_title", "")).strip(), 110)
        top_action = self._truncate(str(payload.get("top_action", "")).strip(), 140)
        top_gain = payload.get("top_action_expected_gain")
        score = payload.get("optimization_score", "--")
        gig_url = str(payload.get("gig_url", "")).strip()
        market_count = payload.get("competitor_count", 0)
        text = (
            f"Comparison complete for {gig_url or 'configured gig'} | "
            f"score {score} | title: {recommended_title or 'not generated'}"
        )
        return {
            "text": text,
            "blocks": [
                self._header_block("Comparison Complete"),
                self._section_block(
                    [
                        f"*Gig URL*\n{gig_url or 'Not provided'}",
                        f"*Optimization Score*\n{score}",
                        f"*Competitors Compared*\n{market_count}",
                    ]
                ),
                self._section_block(
                    [f"*Top Recommended Title*\n{recommended_title or 'No title generated yet.'}"]
                ),
                self._section_block(
                    [
                        "*Do This First*\n"
                        + (top_action or "No top action was generated for this run.")
                        + (f"\nExpected gain: {top_gain}%" if top_gain is not None else "")
                    ]
                ),
                self._context_block([f"Generated at {utc_now_iso()}"]),
            ],
        }

    def _high_impact_action_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = self._truncate(str(payload.get("action_text", "")).strip(), 180)
        expected_gain = payload.get("expected_gain", "--")
        confidence_score = payload.get("confidence_score", "--")
        impact_score = str(payload.get("impact_score", "high")).strip().title()
        return {
            "text": f"High-impact action ready: {action or 'No action text'}",
            "blocks": [
                self._header_block("High-Impact Action"),
                self._section_block(
                    [
                        f"*Action*\n{action or 'No action text'}",
                        f"*Expected Gain*\n{expected_gain}%",
                        f"*Confidence*\n{confidence_score}/100",
                        f"*Impact*\n{impact_score}",
                    ]
                ),
                self._context_block([f"Generated at {utc_now_iso()}"]),
            ],
        }

    def _system_error_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        error_message = self._truncate(str(payload.get("error_message", "")).strip(), 220)
        job_id = str(payload.get("job_id", "")).strip() or "n/a"
        stack_trace = self._truncate(str(payload.get("stack_trace", "")).strip(), 500)
        return {
            "text": f"System error in GigOptimizer job {job_id}: {error_message or 'Unknown error'}",
            "blocks": [
                self._header_block("System Error"),
                self._section_block(
                    [
                        f"*Job ID*\n{job_id}",
                        f"*Error*\n{error_message or 'Unknown error'}",
                    ]
                ),
                self._section_block([f"*Stack Trace*\n```{stack_trace or 'No stack trace captured.'}```"]),
                self._context_block([f"Generated at {utc_now_iso()}"]),
            ],
        }

    def _weekly_report_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        summary = self._truncate(str(payload.get("summary", "")).strip(), 220)
        improvements = payload.get("top_improvements") or []
        insights = payload.get("key_insights") or []
        report_path = str(payload.get("report_path", "")).strip()
        return {
            "text": f"Weekly report ready: {summary or 'summary unavailable'}",
            "blocks": [
                self._header_block("Weekly Report"),
                self._section_block([f"*Summary*\n{summary or 'No summary was generated.'}"]),
                self._section_block(
                    [f"*Top Improvements*\n{self._bulleted_text(improvements, fallback='No improvements listed.')}"]
                ),
                self._section_block(
                    [f"*Key Insights*\n{self._bulleted_text(insights, fallback='No insights listed.')}"]
                ),
                self._context_block(
                    [
                        f"Report: {report_path or 'Not available'}",
                        f"Generated at {utc_now_iso()}",
                    ]
                ),
            ],
        }

    def _generic_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        title = self._truncate(str(payload.get("title", "GigOptimizer Notification")).strip(), 120)
        lines = [self._truncate(str(item).strip(), 180) for item in payload.get("lines", []) if str(item).strip()]
        return {
            "text": title,
            "blocks": [
                self._header_block(title),
                self._section_block([self._bulleted_text(lines, fallback="No details provided.")]),
                self._context_block([f"Generated at {utc_now_iso()}"]),
            ],
        }

    def _header_block(self, text: str) -> dict[str, Any]:
        return {
            "type": "header",
            "text": {"type": "plain_text", "text": self._truncate(text, 150)},
        }

    def _section_block(self, fields: list[str]) -> dict[str, Any]:
        return {
            "type": "section",
            "fields": [{"type": "mrkdwn", "text": self._truncate(field, 1900)} for field in fields if field],
        }

    def _context_block(self, items: list[str]) -> dict[str, Any]:
        return {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": self._truncate(item, 280)} for item in items if item],
        }

    def _bulleted_text(self, items: list[Any], *, fallback: str) -> str:
        values = [f"- {self._truncate(str(item).strip(), 160)}" for item in items if str(item).strip()]
        return "\n".join(values) if values else fallback

    def _truncate(self, value: str, limit: int) -> str:
        if len(value) <= limit:
            return value
        return value[: max(0, limit - 1)].rstrip() + "…"
