"""Typed process settings loaded from the environment.

Issue 04 owns the in-memory event-store capacity. Other services keep
reading their own env vars; issue 02 will add LLM fields to this same
module. Call ``get_settings()`` rather than ``os.environ`` so a typo or
a non-positive capacity fails in one place. ``clear_settings_cache``
exists so tests can change the env without restarting the process.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from os import environ

# Env names. Importers should use these instead of string literals.
ENV_EVENT_STORE_CAPACITY = "EVENT_STORE_CAPACITY"

# The issue cap is 200. Callers inject the validated value into EventStore;
# the store itself does not read the environment.
DEFAULT_EVENT_STORE_CAPACITY = 200
# Hard ceiling so a typo cannot allocate unbounded memory in one process.
MAX_EVENT_STORE_CAPACITY = 10_000


class SettingsError(ValueError):
    """Raised when an environment value cannot be used as settings."""


def _raw(name: str, default: str = "") -> str:
    return environ.get(name, default).strip()


def _positive_int(name: str, default: int, maximum: int) -> int:
    raw = _raw(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise SettingsError(f"{name} must be a positive integer, got {raw!r}") from exc
    if value < 1 or value > maximum:
        raise SettingsError(
            f"{name} must be an integer between 1 and {maximum}, got {raw!r}"
        )
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated process settings."""

    event_store_capacity: int

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from the current environment.

        A missing capacity uses the issue default. A typo, zero, or a
        value above the documented ceiling raises ``SettingsError``.
        """
        return cls(
            event_store_capacity=_positive_int(
                ENV_EVENT_STORE_CAPACITY,
                DEFAULT_EVENT_STORE_CAPACITY,
                MAX_EVENT_STORE_CAPACITY,
            )
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings for this process."""
    return Settings.from_env()


def clear_settings_cache() -> None:
    """Drop the cached settings. Tests call this after changing the env."""
    get_settings.cache_clear()
