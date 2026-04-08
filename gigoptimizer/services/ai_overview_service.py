from __future__ import annotations

import hashlib
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .cache_service import CacheService
from .settings_service import SettingsService


class AIOverviewService:
    AI_CACHE_TTL_SECONDS = 20 * 60

    def __init__(
        self,
        settings_service: SettingsService,
        cache_service: CacheService | None = None,
    ) -> None:
        self.settings_service = settings_service
        self.cache_service = cache_service

    def generate_overview(self, *, report: dict, memory_context: dict | None = None) -> dict:
        settings = self.settings_service.get_settings().ai
        cache_key = self._cache_key(
            "overview",
            {
                "provider": settings.provider,
                "model": settings.model,
                "report": report,
                "memory_context": memory_context or {},
            },
        )
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        if not settings.enabled:
            response = {
                "status": "disabled",
                "provider": settings.provider,
                "model": settings.model,
                "summary": "",
                "next_steps": [],
            }
            self._set_cached(cache_key, response)
            return response
        if settings.provider == "n8n":
            response = self._n8n_overview(report, settings.api_base_url, memory_context=memory_context)
            self._set_cached(cache_key, response)
            return response
        if settings.provider != "openai":
            response = self._local_overview(
                report,
                provider=settings.provider,
                model=settings.model,
                reason="Only the OpenAI provider is wired right now, so the app generated a local fallback summary.",
                memory_context=memory_context,
            )
            self._set_cached(cache_key, response)
            return response
        if not settings.api_key:
            response = self._local_overview(
                report,
                provider=settings.provider,
                model=settings.model,
                reason="AI overview is enabled but no API key is configured, so the app generated a local fallback summary.",
                memory_context=memory_context,
            )
            self._set_cached(cache_key, response)
            return response

        prompt = self._prompt(report, memory_context=memory_context)
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
            response = self._local_overview(
                report,
                provider=settings.provider,
                model=settings.model,
                reason=f"AI overview request failed, so the app generated a local fallback summary. {detail or str(exc)}",
                memory_context=memory_context,
            )
            self._set_cached(cache_key, response)
            return response
        except URLError as exc:
            response = self._local_overview(
                report,
                provider=settings.provider,
                model=settings.model,
                reason=f"AI overview request failed, so the app generated a local fallback summary. {exc.reason}",
                memory_context=memory_context,
            )
            self._set_cached(cache_key, response)
            return response

        text = self._extract_text(data)
        summary, next_steps = self._split_summary(text)
        response = {
            "status": "ok",
            "provider": settings.provider,
            "model": settings.model,
            "summary": summary,
            "next_steps": next_steps,
        }
        self._set_cached(cache_key, response)
        return response

    def chat(self, *, message: str, context: dict) -> dict:
        settings = self.settings_service.get_settings().ai
        cleaned_message = str(message or "").strip()
        cache_key = self._cache_key(
            "chat",
            {
                "provider": settings.provider,
                "model": settings.model,
                "message": cleaned_message,
                "context": context,
            },
        )
        cached = self._get_cached(cache_key)
        if cached is not None:
            return cached

        if not cleaned_message:
            response = {
                "status": "warning",
                "provider": settings.provider,
                "model": settings.model,
                "reply": "Ask about your gig title, pricing, tags, competitors, or current market gaps.",
                "suggestions": [],
            }
            self._set_cached(cache_key, response)
            return response
        if not settings.enabled:
            response = self._local_chat(
                cleaned_message,
                context,
                provider=settings.provider,
                model=settings.model,
                reason="AI assistant is disabled, so the app answered from its local market analysis.",
            )
            self._set_cached(cache_key, response)
            return response
        if settings.provider == "n8n":
            response = self._n8n_chat(cleaned_message, context, settings.api_base_url)
            self._set_cached(cache_key, response)
            return response
        if settings.provider != "openai" or not settings.api_key:
            response = self._local_chat(
                cleaned_message,
                context,
                provider=settings.provider,
                model=settings.model,
                reason="The configured provider is not fully wired, so the app answered from its local market analysis.",
            )
            self._set_cached(cache_key, response)
            return response

        prompt = self._chat_prompt(message=cleaned_message, context=context)
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
            response = self._local_chat(
                cleaned_message,
                context,
                provider=settings.provider,
                model=settings.model,
                reason=f"AI assistant request failed, so the app answered from local market analysis. {detail or str(exc)}",
            )
            self._set_cached(cache_key, response)
            return response
        except URLError as exc:
            response = self._local_chat(
                cleaned_message,
                context,
                provider=settings.provider,
                model=settings.model,
                reason=f"AI assistant request failed, so the app answered from local market analysis. {exc.reason}",
            )
            self._set_cached(cache_key, response)
            return response

        text = self._extract_text(data)
        reply, suggestions = self._split_chat_reply(text)
        response = {
            "status": "ok",
            "provider": settings.provider,
            "model": settings.model,
            "reply": reply,
            "suggestions": suggestions,
        }
        self._set_cached(cache_key, response)
        return response

    def _prompt(self, report: dict, *, memory_context: dict | None = None) -> str:
        payload = {
            "optimization_score": report.get("optimization_score"),
            "weekly_action_plan": report.get("weekly_action_plan", []),
            "competitive_gap_analysis": report.get("competitive_gap_analysis"),
            "conversion_audit": report.get("conversion_audit"),
            "pricing_recommendations": report.get("pricing_recommendations", []),
            "memory_context": memory_context or {},
        }
        return (
            "You are an operations analyst for a Fiverr optimization system. "
            "Review the JSON and return a short executive summary followed by 3 concrete next steps. "
            "Keep it concise and factual.\n\n"
            + json.dumps(payload, indent=2)
        )

    def _chat_prompt(self, *, message: str, context: dict) -> str:
        payload = {
            "question": message,
            "optimization_score": context.get("optimization_score"),
            "recommended_title": context.get("recommended_title"),
            "recommended_tags": context.get("recommended_tags", []),
            "market_anchor_price": context.get("market_anchor_price"),
            "competitor_count": context.get("competitor_count"),
            "why_competitors_win": context.get("why_competitors_win", []),
            "what_to_implement": context.get("what_to_implement", []),
            "do_this_first": context.get("do_this_first", []),
            "prioritized_actions": context.get("prioritized_actions", []),
            "pricing_strategy": context.get("pricing_strategy", []),
            "trust_boosters": context.get("trust_boosters", []),
            "faq_recommendations": context.get("faq_recommendations", []),
            "persona_focus": context.get("persona_focus", []),
            "user_actions": context.get("user_actions", []),
            "comparison_history": context.get("comparison_history", []),
        }
        return (
            "You are the in-app GigOptimizer Pro copilot. "
            "Answer the user using only the provided market analysis and current gig context. "
            "Be practical and concise. Give a short direct answer, then up to 3 suggested next actions.\n\n"
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
        return lines[0], lines[1:4]

    def _split_chat_reply(self, text: str) -> tuple[str, list[str]]:
        if not text:
            return "", []
        lines = [line.strip("- ").strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return "", []
        return lines[0], lines[1:4]

    def _n8n_chat(self, message: str, context: dict, webhook_url: str) -> dict:
        url = webhook_url.strip()
        if not url:
            return self._local_chat(
                message,
                context,
                provider="n8n",
                model="webhook",
                reason="n8n mode is enabled but the webhook URL is not configured, so the app answered from local market analysis.",
            )
        payload = {
            "message": message,
            "context": context,
        }
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError) as exc:
            return self._local_chat(
                message,
                context,
                provider="n8n",
                model="webhook",
                reason=f"n8n assistant request failed, so the app answered from local market analysis. {exc}",
            )

        reply = str(data.get("reply", "")).strip() or str(data.get("message", "")).strip()
        suggestions = [str(item).strip() for item in data.get("suggestions", []) if str(item).strip()]
        if not reply:
            return self._local_chat(
                message,
                context,
                provider="n8n",
                model="webhook",
                reason="n8n assistant returned no reply, so the app answered from local market analysis.",
            )
        return {
            "status": "ok",
            "provider": "n8n",
            "model": "webhook",
            "reply": reply,
            "suggestions": suggestions[:3],
        }

    def _n8n_overview(self, report: dict, webhook_url: str, *, memory_context: dict | None = None) -> dict:
        url = webhook_url.strip()
        if not url:
            return self._local_overview(
                report,
                provider="n8n",
                model="webhook",
                reason="n8n mode is enabled but the webhook URL is not configured, so the app generated a local fallback summary.",
                memory_context=memory_context,
            )
        payload = {
            "mode": "overview",
            "report": report,
            "memory_context": memory_context or {},
        }
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=30) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError) as exc:
            return self._local_overview(
                report,
                provider="n8n",
                model="webhook",
                reason=f"n8n overview request failed, so the app generated a local fallback summary. {exc}",
                memory_context=memory_context,
            )

        summary = str(data.get("summary", "")).strip() or str(data.get("reply", "")).strip()
        next_steps = [str(item).strip() for item in data.get("next_steps", []) if str(item).strip()]
        if not next_steps:
            next_steps = [str(item).strip() for item in data.get("suggestions", []) if str(item).strip()]
        if not summary:
            return self._local_overview(
                report,
                provider="n8n",
                model="webhook",
                reason="n8n overview returned no summary, so the app generated a local fallback summary.",
                memory_context=memory_context,
            )
        return {
            "status": "ok",
            "provider": "n8n",
            "model": "webhook",
            "summary": summary,
            "next_steps": next_steps[:3],
        }

    def _local_overview(
        self,
        report: dict,
        *,
        provider: str,
        model: str,
        reason: str,
        memory_context: dict | None = None,
    ) -> dict:
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

        remembered = ""
        if memory_context and memory_context.get("user_actions"):
            latest_action = memory_context["user_actions"][0]
            action_type = (latest_action.get("action") or {}).get("action_type", "an action")
            remembered = f" Recent review history includes {action_type}."
        return {
            "status": "fallback",
            "provider": provider,
            "model": model,
            "summary": f"{headline}{remembered} {reason}".strip(),
            "next_steps": deduped_steps[:3],
        }

    def _local_chat(self, message: str, context: dict, *, provider: str, model: str, reason: str) -> dict:
        lower_message = message.lower()
        recommended_title = str(context.get("recommended_title", "")).strip()
        recommended_tags = list(context.get("recommended_tags", []) or [])
        why = list(context.get("why_competitors_win", []) or [])
        actions = list(context.get("what_to_implement", []) or [])
        prioritized = list(context.get("do_this_first", []) or [])
        pricing = list(context.get("pricing_strategy", []) or [])
        trust = list(context.get("trust_boosters", []) or [])
        faqs = list(context.get("faq_recommendations", []) or [])
        personas = list(context.get("persona_focus", []) or [])
        user_actions = list(context.get("user_actions", []) or [])

        reply = f"The app recommends updating your gig around the current market gap. {reason}".strip()
        suggestions: list[str] = []

        if any(word in lower_message for word in ["title", "headline"]):
            reply = f"Your strongest current title option is: {recommended_title or 'Run a market compare to generate a title.'}"
            suggestions = prioritized[:2] + (
                ["Queue the recommended title into HITL and approve it if it matches your positioning."] if recommended_title else []
            )
        elif any(word in lower_message for word in ["tag", "keyword"]):
            reply = (
                f"Your current market-aligned tags are: {', '.join(recommended_tags[:5])}."
                if recommended_tags
                else "Run a market compare first so the app can generate aligned tags."
            )
            suggestions = prioritized[:2] or actions[:2]
        elif any(word in lower_message for word in ["price", "pricing", "package"]):
            reply = pricing[0] if pricing else "The app needs a fresh compare run before it can score your pricing against the live market anchor."
            suggestions = pricing[1:3]
        elif any(word in lower_message for word in ["trust", "review", "proof"]):
            reply = trust[0] if trust else "The clearest trust gap is still visible proof and review density compared with stronger competitors."
            suggestions = trust[1:4]
        elif any(word in lower_message for word in ["faq", "question"]):
            reply = faqs[0] if faqs else "The app has not generated FAQ recommendations yet."
            suggestions = faqs[1:4]
        elif any(word in lower_message for word in ["persona", "buyer"]):
            if personas:
                top = personas[0]
                reply = f"The highest-priority buyer persona right now is {top.get('persona', 'Unknown')}."
                suggestions = [str(top.get("pain_point", "")).strip()] + [", ".join(top.get("emphasis", [])[:3])]
            else:
                reply = "The app needs a fresh compare run before it can rank buyer personas."
        elif any(word in lower_message for word in ["decision", "history", "memory"]) and user_actions:
            latest = user_actions[0]
            action = latest.get("action") or {}
            reply = f"Your latest tracked review action was {action.get('action_type', 'an action')}."
            suggestions = prioritized[:2] or actions[:2]
        else:
            if why:
                reply = why[0]
            suggestions = prioritized[:2] + trust[:1]

        suggestions = [item for item in suggestions if item]
        return {
            "status": "fallback",
            "provider": provider,
            "model": model,
            "reply": reply,
            "suggestions": suggestions[:3],
        }

    def _cache_key(self, prefix: str, payload: dict[str, object]) -> str:
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        return f"gigoptimizer:{prefix}:{digest}"

    def _get_cached(self, key: str) -> dict | None:
        if self.cache_service is None:
            return None
        value = self.cache_service.get_json(key)
        return value if isinstance(value, dict) else None

    def _set_cached(self, key: str, value: dict) -> None:
        if self.cache_service is None:
            return
        self.cache_service.set_json(key, value, ttl_seconds=self.AI_CACHE_TTL_SECONDS)
