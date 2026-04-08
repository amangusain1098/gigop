from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .settings_service import SettingsService


class AIOverviewService:
    def __init__(self, settings_service: SettingsService) -> None:
        self.settings_service = settings_service

    def generate_overview(self, *, report: dict) -> dict:
        settings = self.settings_service.get_settings().ai
        if not settings.enabled:
            return {
                "status": "disabled",
                "provider": settings.provider,
                "model": settings.model,
                "summary": "",
                "next_steps": [],
            }
        if settings.provider != "openai":
            return self._local_overview(
                report,
                provider=settings.provider,
                model=settings.model,
                reason="Only the OpenAI provider is wired right now, so the app generated a local fallback summary.",
            )
        if not settings.api_key:
            return self._local_overview(
                report,
                provider=settings.provider,
                model=settings.model,
                reason="AI overview is enabled but no API key is configured, so the app generated a local fallback summary.",
            )

        prompt = self._prompt(report)
        url = settings.api_base_url.rstrip("/") + "/responses"
        payload = {
            "model": settings.model,
            "input": prompt,
        }
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {settings.api_key}",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore") if hasattr(exc, "read") else str(exc)
            return self._local_overview(
                report,
                provider=settings.provider,
                model=settings.model,
                reason=f"AI overview request failed, so the app generated a local fallback summary. {detail or str(exc)}",
            )
        except URLError as exc:
            return self._local_overview(
                report,
                provider=settings.provider,
                model=settings.model,
                reason=f"AI overview request failed, so the app generated a local fallback summary. {exc.reason}",
            )

        text = self._extract_text(data)
        summary, next_steps = self._split_summary(text)
        return {
            "status": "ok",
            "provider": settings.provider,
            "model": settings.model,
            "summary": summary,
            "next_steps": next_steps,
        }

    def _prompt(self, report: dict) -> str:
        payload = {
            "optimization_score": report.get("optimization_score"),
            "weekly_action_plan": report.get("weekly_action_plan", []),
            "competitive_gap_analysis": report.get("competitive_gap_analysis"),
            "conversion_audit": report.get("conversion_audit"),
            "pricing_recommendations": report.get("pricing_recommendations", []),
        }
        return (
            "You are an operations analyst for a Fiverr optimization system. "
            "Review the JSON and return a short executive summary followed by 3 concrete next steps. "
            "Keep it concise and factual.\n\n"
            + json.dumps(payload, indent=2)
        )

    def _extract_text(self, payload: dict) -> str:
        if isinstance(payload.get("output_text"), str) and payload["output_text"].strip():
            return payload["output_text"].strip()
        parts: list[str] = []
        for item in payload.get("output", []):
            for content in item.get("content", []):
                text = content.get("text")
                if text:
                    parts.append(text)
        return "\n".join(parts).strip()

    def _split_summary(self, text: str) -> tuple[str, list[str]]:
        if not text:
            return "", []
        lines = [line.strip("- ").strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return "", []
        summary = lines[0]
        next_steps = lines[1:4]
        return summary, next_steps

    def _local_overview(self, report: dict, *, provider: str, model: str, reason: str) -> dict:
        score = report.get("optimization_score")
        weekly_actions = list(report.get("weekly_action_plan", []) or [])
        competitive = report.get("competitive_gap_analysis") or {}
        conversion = report.get("conversion_audit") or {}
        why = list(competitive.get("why_competitors_win", []) or [])
        actions = weekly_actions[:2]
        if competitive.get("what_to_implement"):
            actions.extend(competitive.get("what_to_implement", [])[:2])
        if conversion.get("actions"):
            actions.extend(conversion.get("actions", [])[:2])
        deduped_steps: list[str] = []
        seen: set[str] = set()
        for action in actions:
            cleaned = str(action).strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            deduped_steps.append(cleaned)
        headline = f"Local fallback summary: optimization score is {score if score is not None else '--'}."
        if why:
            headline += f" Biggest visible market gap: {why[0]}"
        elif weekly_actions:
            headline += f" Top current priority: {weekly_actions[0]}"
        return {
            "status": "fallback",
            "provider": provider,
            "model": model,
            "summary": f"{headline} {reason}".strip(),
            "next_steps": deduped_steps[:3],
        }
