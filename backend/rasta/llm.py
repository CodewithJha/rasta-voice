"""Free-tier LLM extractor surface.

Model ids below were checked on 12 Nov 2026. Groq and Gemini retire ids;
override them with ``GROQ_MODEL`` / ``GEMINI_MODEL`` or ``LLM_MODEL`` if a
default stops working. HTTP is plain ``httpx``; there is no vendor SDK.
"""

from __future__ import annotations

from rasta.extractors import (
    Extractor,
    ExtractResult,
    GeminiExtractor,
    GroqExtractor,
    LlmError,
    MissingLlmKeyError,
    close_shared_client,
    get_shared_client,
)
from rasta.extractors.gemini import gemini_request_body, gemini_url
from rasta.extractors.groq import groq_request_body
from rasta.extractors.parse import event_from_model_text
from rasta.extractors.prompt import SYSTEM_PROMPT, build_user_message
from rasta.settings import (
    DEFAULT_GEMINI_BASE_URL,
    DEFAULT_GEMINI_MODEL,
    DEFAULT_GROQ_BASE_URL,
    DEFAULT_GROQ_MODEL,
    DEFAULT_LLM_MAX_RETRIES,
    DEFAULT_LLM_TIMEOUT_SECONDS,
)

# Re-exported so a reviewer (and issue 02) can find the ids at the top of
# this file, with the date they were checked.
# Groq: openai/gpt-oss-20b, checked 12 Nov 2026 (llama-3.1-8b-instant left
# the free and developer tiers on 16 Aug 2026).
# Gemini: gemini-3.5-flash-lite, checked 12 Nov 2026 (Google's recommended
# free-tier Flash-Lite for new work).
GROQ_MODEL = DEFAULT_GROQ_MODEL
GEMINI_MODEL = DEFAULT_GEMINI_MODEL
GROQ_BASE_URL = DEFAULT_GROQ_BASE_URL
GEMINI_BASE_URL = DEFAULT_GEMINI_BASE_URL
LLM_TIMEOUT_SECONDS = DEFAULT_LLM_TIMEOUT_SECONDS
LLM_MAX_RETRIES = DEFAULT_LLM_MAX_RETRIES

PROVIDERS = {
    "groq": GroqExtractor,
    "gemini": GeminiExtractor,
}


def get_llm_extractor(provider: str, settings=None):
    """Return a Groq or Gemini extractor, or raise ``LlmError``."""
    try:
        cls = PROVIDERS[provider]
    except KeyError as exc:
        raise LlmError(
            f"unknown LLM provider {provider!r}; use rules, groq, or gemini",
            reason="unknown_provider",
        ) from exc
    return cls(settings)


__all__ = [
    "GEMINI_BASE_URL",
    "GEMINI_MODEL",
    "GROQ_BASE_URL",
    "GROQ_MODEL",
    "LLM_MAX_RETRIES",
    "LLM_TIMEOUT_SECONDS",
    "SYSTEM_PROMPT",
    "ExtractResult",
    "Extractor",
    "GeminiExtractor",
    "GroqExtractor",
    "LlmError",
    "MissingLlmKeyError",
    "build_user_message",
    "close_shared_client",
    "event_from_model_text",
    "gemini_request_body",
    "gemini_url",
    "get_llm_extractor",
    "get_shared_client",
    "groq_request_body",
]
