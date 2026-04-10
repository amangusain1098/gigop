"""Pluggable LLM client abstraction.

The assistant never calls an HTTP SDK directly. Instead it speaks to a
``LLMClient`` Protocol, which has four concrete implementations:

    * ``OllamaLLMClient``       - runs against a local Ollama daemon
                                  (http://localhost:11434). Zero-cost,
                                  fully offline. This is the default when
                                  ``AI_PROVIDER=ollama`` or no remote key
                                  is configured.
    * ``OpenAILLMClient``       - OpenAI-compatible chat completions.
    * ``AnthropicLLMClient``    - Anthropic messages API.
    * ``DeterministicLLMClient``- pure-Python rule-based responder. Used in
                                  unit tests and as the final fallback when
                                  no network is reachable so the product
                                  never fails-closed.

All clients return a ``LLMResponse`` with the raw text and token usage
(when the backend reports it). They deliberately do not try to parse JSON or
structured output - thats the assistants job.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LLMMessage:
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(slots=True)
class LLMResponse:
    text: str
    model: str
    provider: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    raw: dict = field(default_factory=dict)


@runtime_checkable
class LLMClient(Protocol):
    name: str
    model: str

    def complete(
        self,
        messages,
        *,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ) -> "LLMResponse": ...


# ---------------------------------------------------------------------------
# HTTP helper (stdlib only, no new deps)
# ---------------------------------------------------------------------------
def _post_json(
    url,
    payload,
    *,
    headers=None,
    timeout=60.0,
):
    body = json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310
        raw = response.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}


# ---------------------------------------------------------------------------
# Ollama (local, default)
# ---------------------------------------------------------------------------
class OllamaLLMClient:
    """Talks to a locally running Ollama daemon."""

    name = "ollama"

    def __init__(
        self,
        *,
        model: str = "llama3.1:8b",
        base_url: str = "http://localhost:11434",
        timeout: float = 90.0,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(
        self,
        messages,
        *,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ):
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        try:
            data = _post_json(
                f"{self.base_url}/api/chat",
                payload,
                timeout=self.timeout,
            )
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise LLMUnavailableError(f"Ollama unreachable at {self.base_url}: {exc}") from exc

        text = (data.get("message") or {}).get("content", "")
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.name,
            prompt_tokens=int(data.get("prompt_eval_count", 0) or 0),
            completion_tokens=int(data.get("eval_count", 0) or 0),
            latency_ms=int(data.get("total_duration", 0) or 0) // 1_000_000,
            raw=data,
        )


# ---------------------------------------------------------------------------
# OpenAI-compatible
# ---------------------------------------------------------------------------
class OpenAILLMClient:
    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
    ):
        if not api_key:
            raise ValueError("OpenAILLMClient requires an API key")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(
        self,
        messages,
        *,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ):
        payload = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            data = _post_json(
                f"{self.base_url}/chat/completions",
                payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise LLMUnavailableError(f"OpenAI unreachable: {exc}") from exc

        choices = data.get("choices") or []
        text = ""
        if choices:
            text = (choices[0].get("message") or {}).get("content", "")
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.name,
            prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
            completion_tokens=int(usage.get("completion_tokens", 0) or 0),
            raw=data,
        )


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------
class AnthropicLLMClient:
    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        base_url: str = "https://api.anthropic.com/v1",
        anthropic_version: str = "2023-06-01",
        timeout: float = 60.0,
    ):
        if not api_key:
            raise ValueError("AnthropicLLMClient requires an API key")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.anthropic_version = anthropic_version
        self.timeout = timeout

    def complete(
        self,
        messages,
        *,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ):
        system_parts = [m.content for m in messages if m.role == "system"]
        convo = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in {"user", "assistant"}
        ]
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": convo,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        try:
            data = _post_json(
                f"{self.base_url}/messages",
                payload,
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": self.anthropic_version,
                },
                timeout=self.timeout,
            )
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise LLMUnavailableError(f"Anthropic unreachable: {exc}") from exc

        content = data.get("content") or []
        text = "".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
        usage = data.get("usage") or {}
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.name,
            prompt_tokens=int(usage.get("input_tokens", 0) or 0),
            completion_tokens=int(usage.get("output_tokens", 0) or 0),
            raw=data,
        )


# ---------------------------------------------------------------------------
# Deterministic fallback
# ---------------------------------------------------------------------------
class LLMUnavailableError(RuntimeError):
    """Raised when a remote LLM backend cannot be reached."""


class DeterministicLLMClient:
    """Offline, zero-dependency fallback.

    This client does not call any network. It inspects the user turn and
    returns either a short conversational reply (for greetings, identity,
    capability, thanks) or a template-shaped four-part analysis (for real
    optimization requests), so the product remains usable in air-gapped
    environments and in CI.
    """

    name = "deterministic"
    model = "rule-based-v1"

    _TEMPLATE = (
        "Analysis:\n"
        "- Based on the input provided, the current asset has room to grow on discoverability, "
        "clarity of promise, and proof.\n"
        "- Top performers in this niche lead with the outcome, not the service.\n"
        "\n"
        "Problems:\n"
        "- Weak keyword density in the title and first 120 characters.\n"
        "- Generic value proposition that does not name the metric the buyer cares about.\n"
        "- Missing proof blocks (before/after, metrics, named deliverables).\n"
        "- No clear CTA or next step.\n"
        "\n"
        "Optimized Version:\n"
        "- Title: lead with the outcome + the platform + the proof metric.\n"
        "- Description: hook -> pain -> deliverables -> proof -> CTA.\n"
        "- Tags: mix high-volume head terms with 2 long-tail intent terms.\n"
        "- FAQ: address scope, access, guarantees, and turnaround up-front.\n"
        "\n"
        "Action Steps:\n"
        "1. Rewrite the title to include the outcome metric and the platform.\n"
        "2. Move deliverables to the top of the description.\n"
        "3. Add a before/after proof block with a named metric.\n"
        "4. Rebuild the tag list around intent-matched long-tail terms.\n"
        "5. Add a crisp CTA inside the first package description.\n"
    )

    _GREETING_REPLY = (
        "Hey! I am the GigOptimizer copilot. I can rewrite your Fiverr gigs, "
        "audit websites for SEO and Core Web Vitals, and generate social "
        "content that actually converts. What would you like to work on?"
    )

    _IDENTITY_REPLY = (
        "I am the GigOptimizer Pro AI copilot. I specialize in Fiverr gig "
        "optimization, website SEO and performance audits, and content "
        "generation for LinkedIn, Twitter, and blogs. Ask me to rewrite a "
        "gig, audit a URL, or draft posts."
    )

    _CAPABILITY_REPLY = (
        "I can rewrite your Fiverr gig title, description, tags, and FAQ to "
        "rank and convert better; audit any website for SEO, Core Web Vitals, "
        "and conversion blockers; and generate social posts with hooks and "
        "CTAs. Paste a URL, a gig, or a topic and I will take it from there."
    )

    _THANKS_REPLY = (
        "Anytime. Ping me whenever you want to optimize something else."
    )

    _HOW_ARE_YOU_REPLY = (
        "Running smooth. Ready to rewrite a gig, audit a site, or draft some "
        "content whenever you are."
    )

    _GREETINGS_SET = {
        "hi", "hii", "hiii", "hiiii", "hello", "helo", "hey", "heya", "hola",
        "yo", "sup", "howdy", "greetings", "good morning", "good afternoon",
        "good evening", "morning", "evening", "gm", "ga", "ge",
    }
    _THANKS_SET = {
        "thanks", "thank you", "ty", "thx", "thankyou", "appreciate it",
        "cheers", "much appreciated",
    }
    _HOW_ARE_YOU_SET = {
        "how are you", "how is it going", "hows it going", "how are things",
        "whats up", "how do you do", "how are u", "how r u",
    }
    _IDENTITY_SET = {
        "who are you", "what are you", "tell me about yourself",
        "introduce yourself", "your name", "what is your name",
        "whats your name", "who is this", "are you a bot", "are you an ai",
        "are you human",
    }
    _CAPABILITY_SET = {
        "what do you do", "what can you do", "what can you help with",
        "what can i ask you", "how can you help", "what do you help with",
        "what are you for", "what are you good at", "help me",
        "how does this work", "what is this", "what is gigoptimizer",
    }

    @classmethod
    def _classify(cls, user_text):
        text = (user_text or "").strip().lower()
        if not text:
            return "empty"
        stripped = text.rstrip("?!.,;: ")
        canon = stripped.replace("'", "").replace("\u2019", "")
        words = canon.split()
        word_count = len(words)
        if word_count > 8:
            return "task"
        if canon in cls._GREETINGS_SET:
            return "greeting"
        if word_count <= 3 and any(canon == g or canon.startswith(g + " ") for g in cls._GREETINGS_SET):
            return "greeting"
        if canon in cls._THANKS_SET or any(canon == t or canon.startswith(t + " ") for t in cls._THANKS_SET):
            return "thanks"
        if canon in cls._HOW_ARE_YOU_SET or any(canon.startswith(h) for h in cls._HOW_ARE_YOU_SET):
            return "how_are_you"
        if canon in cls._IDENTITY_SET or any(canon.startswith(i) for i in cls._IDENTITY_SET):
            return "identity"
        if canon in cls._CAPABILITY_SET or any(canon.startswith(c) for c in cls._CAPABILITY_SET):
            return "capability"
        return "task"

    def complete(
        self,
        messages,
        *,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ):
        user_text = ""
        for m in reversed(messages):
            if m.role == "user":
                user_text = m.content
                break

        # Detect if the caller already wrapped the user turn in the
        # conversational prompt template (which we should respect), vs a raw
        # one-liner (which we should classify).
        is_conversational_wrapper = "User message:" in user_text and (
            "Reply naturally" in user_text or "casually" in user_text
        )

        # Extract the raw user text even when it has been wrapped in the
        # conversational template.
        raw = user_text
        if is_conversational_wrapper:
            marker = "User message:"
            idx = user_text.rfind(marker)
            if idx >= 0:
                raw = user_text[idx + len(marker):].strip()

        intent = self._classify(raw)

        if intent in {"greeting", "thanks", "how_are_you", "identity", "capability"}:
            if intent == "greeting":
                text = self._GREETING_REPLY
            elif intent == "thanks":
                text = self._THANKS_REPLY
            elif intent == "how_are_you":
                text = self._HOW_ARE_YOU_REPLY
            elif intent == "identity":
                text = self._IDENTITY_REPLY
            else:
                text = self._CAPABILITY_REPLY
            return LLMResponse(
                text=text,
                model=self.model,
                provider=self.name,
                prompt_tokens=sum(len(m.content) // 4 for m in messages),
                completion_tokens=len(text) // 4,
            )

        # Conversational wrapper with an unclassified payload: play nice.
        if is_conversational_wrapper:
            text = (
                "I am the GigOptimizer copilot. Tell me what you would like "
                "to work on - a Fiverr gig, a website audit, or some content "
                "- and I will help you optimize it."
            )
            return LLMResponse(
                text=text,
                model=self.model,
                provider=self.name,
                prompt_tokens=sum(len(m.content) // 4 for m in messages),
                completion_tokens=len(text) // 4,
            )

        # Task intent: return the four-part structured template.
        user_tail = user_text[:160].replace("\n", " ") if user_text else ""
        text = self._TEMPLATE
        if user_tail:
            text = f"{text}\nContext echo: {user_tail}\n"
        return LLMResponse(
            text=text,
            model=self.model,
            provider=self.name,
            prompt_tokens=sum(len(m.content) // 4 for m in messages),
            completion_tokens=len(text) // 4,
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def build_default_client(
    *,
    provider=None,
    model=None,
    api_key=None,
    base_url=None,
    env=None,
):
    """Build the best available client based on config + environment."""

    env = env or os.environ
    provider = (provider or env.get("AI_PROVIDER") or "").strip().lower()
    model = model or env.get("AI_MODEL") or ""
    api_key = api_key or env.get("AI_API_KEY") or ""
    base_url = base_url or env.get("AI_API_BASE_URL") or ""

    if provider in {"openai", "azure-openai"}:
        if not api_key:
            logger.warning("openai provider selected but no AI_API_KEY set, falling back to deterministic")
            return DeterministicLLMClient()
        return OpenAILLMClient(
            api_key=api_key,
            model=model or "gpt-4o-mini",
            base_url=base_url or "https://api.openai.com/v1",
        )

    if provider == "anthropic":
        if not api_key:
            logger.warning("anthropic provider selected but no AI_API_KEY set, falling back to deterministic")
            return DeterministicLLMClient()
        return AnthropicLLMClient(
            api_key=api_key,
            model=model or "claude-sonnet-4-6",
            base_url=base_url or "https://api.anthropic.com/v1",
        )

    if provider == "ollama":
        return OllamaLLMClient(
            model=model or "llama3.1:8b",
            base_url=base_url or "http://localhost:11434",
        )

    if provider in {"", "auto"}:
        client = OllamaLLMClient(
            model=model or "llama3.1:8b",
            base_url=base_url or "http://localhost:11434",
        )
        if _ping(client.base_url):
            return client
        return DeterministicLLMClient()

    if provider in {"deterministic", "offline", "stub", "n8n", "webhook"}:
        return DeterministicLLMClient()

    logger.warning("unknown AI provider %r - using deterministic fallback", provider)
    return DeterministicLLMClient()


def _ping(base_url, *, timeout=0.75):
    """Return True if base_url looks reachable."""
    try:
        request = urllib.request.Request(f"{base_url.rstrip('/')}/api/tags", method="GET")
        with urllib.request.urlopen(request, timeout=timeout):  # nosec B310
            return True
    except Exception:  # noqa: BLE001
        return False
