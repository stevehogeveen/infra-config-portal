from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InventoryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["ilo.inventory"] = "ilo.inventory"


class InventoryJob(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: Literal[1] = 1
    operation: Literal["ilo.inventory"] = "ilo.inventory"
    device_id: str
    target_revision: str
    profile_revision: str
    provider_mode: str
    actor: str


class SystemFact(BaseModel):
    model: str | None = None
    manufacturer: str | None = None
    serial_number: str | None = None
    power_state: str | None = None


class InventoryResult(BaseModel):
    version: Literal[1] = 1
    device_id: str
    status: Literal["completed", "blocked", "failed"]
    source: Literal["mock", "ansible"]
    checked_at: str
    summary: str
    systems: list[SystemFact] = Field(default_factory=list)


class InventoryRun(BaseModel):
    version: Literal[1] = 1
    job_id: str
    device_id: str
    status: str
    current: bool = False
    result: InventoryResult | None = None
