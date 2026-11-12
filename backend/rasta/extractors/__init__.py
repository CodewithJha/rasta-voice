"""Extractor providers used by ``rasta.extract``.

The public entry point stays ``rasta.extract.extract_event``. This package
holds the protocol, the free-tier HTTP callers, and the shared HTTP client
that issue 29 can take over.
"""

from rasta.extractors.base import Extractor, ExtractResult, LlmError, MissingLlmKeyError
from rasta.extractors.breaker import CircuitOpenError, get_breaker, set_breaker
from rasta.extractors.gemini import GeminiExtractor
from rasta.extractors.groq import GroqExtractor
from rasta.extractors.http import close_shared_client, get_shared_client

__all__ = [
    "CircuitOpenError",
    "ExtractResult",
    "Extractor",
    "GeminiExtractor",
    "GroqExtractor",
    "LlmError",
    "MissingLlmKeyError",
    "close_shared_client",
    "get_breaker",
    "get_shared_client",
    "set_breaker",
]
