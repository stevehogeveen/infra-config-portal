from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import EnvironmentName, RequestStatus, WorkflowRunStatus

VM_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]{2,62}$")


class VMDeploymentCreate(BaseModel):
    requester: str = Field(min_length=2, max_length=120)
    environment: EnvironmentName
    site: str = Field(min_length=2, max_length=80)
    cluster: str = Field(min_length=2, max_length=120)
    vm_name: str = Field(min_length=3, max_length=63)
    template: str = Field(min_length=2, max_length=120)
    cpu: int = Field(ge=1, le=64)
    memory_gb: int = Field(
        ge=1,
        le=1024,
        validation_alias=AliasChoices("memory_gb", "memory"),
    )
    disk_gb: int = Field(
        ge=10,
        le=65536,
        validation_alias=AliasChoices("disk_gb", "disk_size", "disk_size_gb"),
    )
    network: str = Field(min_length=2, max_length=120)
    datastore: str | None = Field(default=None, min_length=2, max_length=120)
    storage_tier: str | None = Field(default=None, min_length=2, max_length=80)
    owner: str = Field(min_length=2, max_length=120)
    expiry_date: date
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("vm_name")
    @classmethod
    def validate_vm_name(cls, value: str) -> str:
        if not VM_NAME_RE.match(value):
            raise ValueError(
                "vm_name must start with a letter and contain only letters, numbers, and hyphens"
            )
        if "--" in value:
            raise ValueError("vm_name must not contain repeated hyphens")
        return value

    @field_validator(
        "site",
        "cluster",
        "template",
        "network",
        "datastore",
        "storage_tier",
        "requester",
        "owner",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return str(value).strip()

    @field_validator("expiry_date")
    @classmethod
    def expiry_must_be_future(cls, value: date) -> date:
        if value <= date.today():
            raise ValueError("expiry_date must be in the future")
        return value

    @model_validator(mode="after")
    def require_storage_target(self) -> "VMDeploymentCreate":
        if not self.datastore and not self.storage_tier:
            raise ValueError("datastore or storage_tier is required")
        return self


class VMDeploymentUpdate(BaseModel):
    requester: str | None = Field(default=None, min_length=2, max_length=120)
    environment: EnvironmentName | None = None
    site: str | None = Field(default=None, min_length=2, max_length=80)
    cluster: str | None = Field(default=None, min_length=2, max_length=120)
    vm_name: str | None = Field(default=None, min_length=3, max_length=63)
    template: str | None = Field(default=None, min_length=2, max_length=120)
    cpu: int | None = Field(default=None, ge=1, le=64)
    memory_gb: int | None = Field(
        default=None,
        ge=1,
        le=1024,
        validation_alias=AliasChoices("memory_gb", "memory"),
    )
    disk_gb: int | None = Field(
        default=None,
        ge=10,
        le=65536,
        validation_alias=AliasChoices("disk_gb", "disk_size", "disk_size_gb"),
    )
    network: str | None = Field(default=None, min_length=2, max_length=120)
    datastore: str | None = Field(default=None, min_length=2, max_length=120)
    storage_tier: str | None = Field(default=None, min_length=2, max_length=80)
    owner: str | None = Field(default=None, min_length=2, max_length=120)
    expiry_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("vm_name")
    @classmethod
    def validate_vm_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not VM_NAME_RE.match(value):
            raise ValueError(
                "vm_name must start with a letter and contain only letters, numbers, and hyphens"
            )
        if "--" in value:
            raise ValueError("vm_name must not contain repeated hyphens")
        return value

    @field_validator(
        "site",
        "cluster",
        "template",
        "network",
        "datastore",
        "storage_tier",
        "requester",
        "owner",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return str(value).strip()

    @field_validator("expiry_date")
    @classmethod
    def expiry_must_be_future(cls, value: date | None) -> date | None:
        if value is None:
            return value
        if value <= date.today():
            raise ValueError("expiry_date must be in the future")
        return value

    @model_validator(mode="after")
    def require_update_field(self) -> "VMDeploymentUpdate":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class VMDeploymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cluster: str
    vm_name: str
    template: str
    cpu: int
    memory_gb: int
    disk_gb: int
    network: str
    datastore: str | None
    storage_tier: str | None


class RequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    request_type: str
    status: RequestStatus
    requester: str
    owner: str
    environment: EnvironmentName
    site: str
    expiry_date: date
    notes: str | None
    created_at: datetime
    updated_at: datetime
    vm_deploy: VMDeploymentRead


class ApprovalCreate(BaseModel):
    approver: str = Field(min_length=2, max_length=120)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("approver", mode="before")
    @classmethod
    def strip_approver(cls, value: str) -> str:
        return str(value).strip()


class WorkflowRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    request_id: str
    workflow_id: str | None
    workflow_slug: str
    status: WorkflowRunStatus
    provider: str
    plan_json: dict[str, Any]
    result_json: dict[str, Any] | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    request_id: str | None
    workflow_run_id: str | None
    actor: str
    event_type: str
    from_status: str | None
    to_status: str | None
    message: str
    data_json: dict[str, Any]
    created_at: datetime


class ProviderStatusRead(BaseModel):
    name: str
    kind: str
    mode: str
    status: str
    capabilities: list[str]
    message: str


class CatalogRead(BaseModel):
    environments: list[str]
    sites: list[str]
    clusters_by_site: dict[str, list[str]]
    templates: list[str]
    networks: list[dict[str, Any]]
    datastores: list[str]
    storage_tiers: list[str]
