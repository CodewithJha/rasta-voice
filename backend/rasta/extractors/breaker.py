"""Circuit-breaker hook for the LLM path.

Issue 29 owns the real breaker. Until that lands, the default is a closed
breaker (calls are allowed). If a later issue installs an open breaker,
the extractor must fall back to rules instead of hanging or returning 500.
Tests can swap the breaker with ``set_breaker``.
"""

from __future__ import annotations

from typing import Protocol

from rasta.extractors.base import LlmError


class CircuitOpenError(LlmError):
    """The LLM breaker is open; the caller should use the rules fallback."""

    def __init__(self, name: str = "llm") -> None:
        super().__init__(
            f"circuit breaker open for {name}",
            reason="circuit_open",
        )


class Breaker(Protocol):
    """Minimal hook. Issue 29 can replace the process-wide instance."""

    def allow(self, name: str) -> bool:
        """Return True if a call to ``name`` may start."""


class ClosedBreaker:
    """Always allows the call. The skeleton until issue 29 lands."""

    def allow(self, name: str) -> bool:
        return True


_breaker: Breaker = ClosedBreaker()


def get_breaker() -> Breaker:
    """Return the process-wide breaker."""
    return _breaker


def set_breaker(breaker: Breaker | None) -> None:
    """Install a breaker, or restore the closed default when ``breaker`` is None."""
    global _breaker
    _breaker = ClosedBreaker() if breaker is None else breaker


def ensure_closed(name: str = "llm") -> None:
    """Raise ``CircuitOpenError`` when the breaker is open."""
    if not get_breaker().allow(name):
        raise CircuitOpenError(name)
