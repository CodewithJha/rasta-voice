"""Pydantic mirror of shared/rider_event.schema.json.

Change the JSON schema, this file, and frontend/src/types.ts in one commit.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Intent(StrEnum):
    customer_unreachable = "customer_unreachable"
    address_issue = "address_issue"
    item_missing = "item_missing"
    delay = "delay"
    accident_sos = "accident_sos"
    other = "other"


class Urgency(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class RiderEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Intent
    order_id: str | None
    eta_minutes: int | None
    urgency: Urgency
    dispatch_action: str = Field(min_length=1)
    transcript: str
    confidence: float = Field(ge=0, le=1)
