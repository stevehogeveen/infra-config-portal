from __future__ import annotations

from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class DestructivePlanClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    provider_id: str = Field(min_length=1)
    action_id: str = Field(min_length=1)
    plan_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    target_binding_digest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    claimed_at: datetime


class DestructivePlanClaimStore(Protocol):
    """Atomically accepts a destructive plan once and refuses every replay."""

    def claim_once(self, claim: DestructivePlanClaim) -> bool: ...
