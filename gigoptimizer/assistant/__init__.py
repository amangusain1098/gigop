"""GigOptimizer AI Assistant package.

This module exposes the unified ``AIAssistant`` entry point that powers the
product's three core features:

    * Fiverr gig optimization
    * Website / SEO audits
    * Social content generation

It is designed to be pluggable: the actual LLM call is resolved through a
``LLMClient`` abstraction, so the assistant can run against a local Ollama
model, a remote OpenAI / Anthropic API, or a deterministic rule-based fallback
when no network is available.
"""

from __future__ import annotations

from .assistant import AIAssistant, AssistantResponse
from .client import (
    AnthropicLLMClient,
    DeterministicLLMClient,
    LLMClient,
    LLMMessage,
    LLMResponse,
    OllamaLLMClient,
    OpenAILLMClient,
    build_default_client,
)
from .prompts import (
    ARCHITECT_DESIGN_PROMPT,
    CHAIN_OF_THOUGHT_PROMPT,
    CONTENT_REFINER_PROMPT,
    FIVERR_SEO_EXPERT_PROMPT,
    GIG_OPTIMIZER_SYSTEM_PROMPT,
    SAAS_SELF_AUDIT_PROMPT,
    render_prompt,
)
from .schemas import (
    ArchitectBlueprint,
    ContentGenerationResult,
    FiverrGigOptimizationResult,
    OutputImprovementResult,
    SaaSSelfAuditResult,
    StructuredAnalysis,
    WebsiteAuditResult,
)
from .scoring import GigScoreBreakdown, ScoringRubric

__all__ = [
    "AIAssistant",
    "AssistantResponse",
    "AnthropicLLMClient",
    "DeterministicLLMClient",
    "LLMClient",
    "LLMMessage",
    "LLMResponse",
    "OllamaLLMClient",
    "OpenAILLMClient",
    "build_default_client",
    "ARCHITECT_DESIGN_PROMPT",
    "CHAIN_OF_THOUGHT_PROMPT",
    "CONTENT_REFINER_PROMPT",
    "FIVERR_SEO_EXPERT_PROMPT",
    "GIG_OPTIMIZER_SYSTEM_PROMPT",
    "SAAS_SELF_AUDIT_PROMPT",
    "render_prompt",
    "ArchitectBlueprint",
    "ContentGenerationResult",
    "FiverrGigOptimizationResult",
    "OutputImprovementResult",
    "SaaSSelfAuditResult",
    "StructuredAnalysis",
    "WebsiteAuditResult",
    "GigScoreBreakdown",
    "ScoringRubric",
]
