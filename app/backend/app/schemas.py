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


class ArtifactRead(BaseModel):
    id: str
    request_id: str
    workflow_run_id: str | None
    kind: str
    title: str
    description: str
    status: str
    created_at: datetime
    updated_at: datetime
    mock_only: bool
    redacted: bool
    downloadable: bool
    download_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReadinessIssue(BaseModel):
    code: str
    message: str
    severity: str
    action: str


class RequestReadinessRead(BaseModel):
    request_id: str
    current_status: RequestStatus
    ready_for_submit: bool
    ready_for_approval: bool
    ready_for_plan: bool
    ready_for_execute: bool
    next_action: str
    blockers: list[ReadinessIssue]
    warnings: list[ReadinessIssue]
    summary: str


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


class MediaInventoryItemRead(BaseModel):
    placeholder_name: str
    extension: str
    size_bytes: int
    category: str
    source: str
    actual_name_redacted: bool
    product_hints: list[str] = Field(default_factory=list)
    generation_hints: list[str] = Field(default_factory=list)
    version_hint: str | None = None


class MediaInventoryRead(BaseModel):
    mode: str
    configured_directories: list[str]
    items: list[MediaInventoryItemRead]
    warnings: list[str]


class UpgradeSubjectRead(BaseModel):
    provider_type: str
    product: str | None = None
    generation: str | None = None
    model: str | None = None
    serial: str | None = None
    current_version: str | None = None
    discovery_confidence: str


class UpgradeCandidateRead(BaseModel):
    id: str
    category: str
    product_hint: str | None = None
    generation_hint: str | None = None
    version: str | None = None
    source: str
    redacted_label: str
    match_confidence: str
    warnings: list[str] = Field(default_factory=list)


class UpgradeRuleRead(BaseModel):
    product: str | None = None
    generation: str | None = None
    from_constraint: str | None = None
    to_constraint: str | None = None
    requires_intermediate: list[str] = Field(default_factory=list)
    blocked_reason: str | None = None
    warning: str | None = None
    source: str
    confidence: str


class UpgradeDecisionRead(BaseModel):
    status: str
    current_version: str | None = None
    recommended_target: str | None = None
    required_intermediate_versions: list[str] = Field(default_factory=list)
    candidate_chain: list[UpgradeCandidateRead] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    removable_warnings: list[str] = Field(default_factory=list)
    next_safe_action: str
    apply_enabled: bool = False


class IloUpgradeReadinessRead(BaseModel):
    provider_id: str
    subject: UpgradeSubjectRead
    candidates: list[UpgradeCandidateRead]
    decision: UpgradeDecisionRead
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    removable_warnings: list[str] = Field(default_factory=list)
    upgrade_chain: list[UpgradeCandidateRead] = Field(default_factory=list)
    apply_enabled: bool = False


class ProviderActionRead(BaseModel):
    id: str
    label: str
    enabled: bool
    read_only: bool
    reason: str
    method: str | None = None
    endpoint: str | None = None


class ProviderStatusRead(BaseModel):
    id: str
    name: str
    kind: str
    mode: str
    status: str
    capabilities: list[str]
    message: str
    configuration: dict[str, Any] = Field(default_factory=dict)
    discovery: dict[str, Any] | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    safe_actions: list[ProviderActionRead] = Field(default_factory=list)
    disabled_actions: list[ProviderActionRead] = Field(default_factory=list)
    last_probe_result: dict[str, Any] | None = None
    last_probe_time: str | None = None


class NetAppPlanPreviewRead(BaseModel):
    provider_id: str
    mode: str
    apply_enabled: bool = False
    netapp_configured: bool
    planned_targets: dict[str, Any]
    readiness_summary: dict[str, Any]
    readiness_buckets: dict[str, Any]
    cluster_intent_preview: dict[str, Any]
    svm_intent_preview: dict[str, Any]
    lif_intent_preview: dict[str, Any]
    storage_iscsi_plan_preview: dict[str, Any]
    upgrade_readiness_preview: dict[str, Any]
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    removable_warnings: list[str] = Field(default_factory=list)
    disabled_actions: list[ProviderActionRead] = Field(default_factory=list)
    artifact_placeholders: list[str] = Field(default_factory=list)
    next_safe_action: str


class ProviderProbeResultRead(BaseModel):
    provider_id: str
    status: str
    message: str
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    checked_at: str | None = None
    model_config = ConfigDict(extra="allow")


class CatalogRead(BaseModel):
    environments: list[str]
    sites: list[str]
    clusters_by_site: dict[str, list[str]]
    templates: list[str]
    networks: list[dict[str, Any]]
    datastores: list[str]
    storage_tiers: list[str]
