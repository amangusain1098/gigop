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
structured output - that's the assistant's job.
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
    raw: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class LLMClient(Protocol):
    name: str
    model: str

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ) -> LLMResponse: ...


# ---------------------------------------------------------------------------
# HTTP helper (stdlib only, no new deps)
# ---------------------------------------------------------------------------
def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    request = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - POST to configured host
        raw = response.read().decode("utf-8", errors="replace")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw}


# ---------------------------------------------------------------------------
# Ollama (local, default)
# ---------------------------------------------------------------------------
class OllamaLLMClient:
    """Talks to a locally running Ollama daemon.

    Install once with ``ollama pull llama3.1:8b`` (or any other instruction
    tuned model) and the assistant can run entirely on the user's machine.
    """

    name = "ollama"

    def __init__(
        self,
        *,
        model: str = "llama3.1:8b",
        base_url: str = "http://localhost:11434",
        timeout: float = 90.0,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ) -> LLMResponse:
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
    ) -> None:
        if not api_key:
            raise ValueError("OpenAILLMClient requires an API key")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ) -> LLMResponse:
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
    ) -> None:
        if not api_key:
            raise ValueError("AnthropicLLMClient requires an API key")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.anthropic_version = anthropic_version
        self.timeout = timeout

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        system_parts = [m.content for m in messages if m.role == "system"]
        convo = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in {"user", "assistant"}
        ]
        payload: dict[str, Any] = {
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
            block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"
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

    This client does not call any network. It returns a template-shaped
    response that satisfies the assistant's parser, so the product remains
    usable in air-gapped environments and in CI. The text is intentionally
    generic but follows the required four-part format so the downstream
    parser never crashes.
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

    def complete(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.4,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        # Keep a short echo of the user turn so tests can assert context was
        # threaded through.
        user_tail = ""
        for m in reversed(messages):
            if m.role == "user":
                user_tail = m.content[:160].replace("\n", " ")
                break
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
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    env: dict[str, str] | None = None,
) -> LLMClient:
    """Build the best available client based on config + environment.

    Resolution order:

    1. Explicit ``provider`` argument.
    2. ``AI_PROVIDER`` environment variable.
    3. Fall back to ``ollama`` (local) if it appears reachable, otherwise
       ``deterministic``.
    """

    env = env or os.environ  # type: ignore[assignment]
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
        # Try Ollama, silently fall back if not reachable.
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


def _ping(base_url: str, *, timeout: float = 0.75) -> bool:
    """Return True if ``base_url`` looks reachable."""
    try:
        request = urllib.request.Request(f"{base_url.rstrip('/')}/api/tags", method="GET")
        with urllib.request.urlopen(request, timeout=timeout):  # nosec B310 - local loopback ping
            return True
    except Exception:  # noqa: BLE001 - any failure means "not reachable"
        return False
