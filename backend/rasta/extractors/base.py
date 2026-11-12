"""Shared types for extractor providers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

import httpx

from rasta.schema import RiderEvent

ExtractorSource = Literal["llm", "rules"]


@dataclass(frozen=True, slots=True)
class ExtractResult:
    """A validated event plus the envelope fields that must not enter RiderEvent."""

    event: RiderEvent
    source: ExtractorSource
    fallback_reason: str | None = None


class Extractor(Protocol):
    """Turns a transcript into a ``RiderEvent``.

    Implementations must not log the transcript, the prompt, the raw model
    text, or the API key. HTTP is done with the injected or shared client.
    """

    name: str

    def extract(
        self,
        transcript: str,
        *,
        client: httpx.Client | None = None,
    ) -> RiderEvent:
        """Return a schema-valid event or raise ``LlmError``."""


class LlmError(Exception):
    """A free-tier call failed in a way the rules fallback can handle."""

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


class MissingLlmKeyError(LlmError):
    """The configured provider was selected but its key is empty."""

    def __init__(self, env_name: str) -> None:
        super().__init__(
            f"{env_name} is not set. Set the key or use LLM_PROVIDER=rules.",
            reason="missing_api_key",
        )
        self.env_name = env_name
