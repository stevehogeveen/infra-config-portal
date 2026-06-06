from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import EnvironmentName, RequestStatus, WorkflowRunStatus
from app.services.netapp_observations import validate_netapp_operator_notes

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
    model_config = ConfigDict(from_attributes=True)

    id: str
    label: str
    enabled: bool
    read_only: bool
    reason: str
    method: str | None = None
    endpoint: str | None = None


class IloConnectionReadinessRead(BaseModel):
    provider_mode: str
    provider_status: str
    host_configured: bool
    username_configured: bool
    password_configured: bool
    tls_verify: bool
    timeout_seconds: float
    missing_fields: list[str] = Field(default_factory=list)
    redfish_probe_available: bool
    safety_flags: dict[str, Any] = Field(default_factory=dict)


class IloEndpointCheckRead(BaseModel):
    name: str | None = None
    path: str | None = None
    status_code: int | None = None
    content_type: str | None = None
    error_class: str | None = None
    classification: str | None = None


class IloEndpointDetectionRead(BaseModel):
    classification: str = "not_checked"
    message: str = "GET-only endpoint detection has not run."
    redfish_status: str = "not_checked"
    legacy_status: str = "not_checked"
    web_status: str = "not_checked"
    inventory_collection_status: str = "not_checked"
    inventory_collection_classification: str = "not_checked"
    inventory_collection_checks: list[IloEndpointCheckRead] = Field(default_factory=list)
    auth_failure_classification: str = "not_checked"
    auth_recovery_hint: str = "not_checked"
    next_safe_action: str = "Run explicit GET-only endpoint detection from Provider Status."
    diagnostic_hints: list[str] = Field(default_factory=list)
    checks: list[IloEndpointCheckRead] = Field(default_factory=list)


class IloCurrentStateRead(BaseModel):
    last_probe_status: str
    last_probe_time: str | None = None
    model: str | None = None
    serial: str | None = None
    current_firmware: str | None = None
    ilo_generation: str | None = None
    endpoint_classification: str = "not_checked"
    endpoint_next_safe_action: str = "Run explicit GET-only endpoint detection."
    redfish_root_status: str = "not_checked"
    redfish_endpoint_detected: str
    legacy_endpoint_status: str
    legacy_endpoint_message: str
    web_endpoint_status: str = "not_checked"
    endpoint_detection: IloEndpointDetectionRead = Field(default_factory=IloEndpointDetectionRead)
    media_inventory_mode: str


class IloDesiredSetupSectionRead(BaseModel):
    id: str
    title: str
    status: str
    apply_enabled: bool = False
    note: str


class IloReportArtifactPlaceholderRead(BaseModel):
    kind: str
    title: str
    status: str
    note: str


class IloReadinessSummaryRead(BaseModel):
    provider_id: str
    connection: IloConnectionReadinessRead
    current_state: IloCurrentStateRead
    desired_setup_sections: list[IloDesiredSetupSectionRead]
    firmware_readiness: IloUpgradeReadinessRead
    upgrade_decision_status: str
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    removable_warnings: list[str] = Field(default_factory=list)
    disabled_dangerous_actions: list[ProviderActionRead] = Field(default_factory=list)
    reports_artifacts: list[IloReportArtifactPlaceholderRead] = Field(default_factory=list)


SECRET_VALUE_RE = re.compile(
    r"(password\s*=|token\s*=|secret\s*=|bearer\s+|-----begin|private[_ -]?key)",
    re.IGNORECASE,
)


class IloNetworkIntent(BaseModel):
    hostname: str | None = Field(default=None, max_length=120)
    management_ip: str | None = Field(default=None, max_length=80)
    subnet_mask_or_prefix: str | None = Field(default=None, max_length=80)
    gateway: str | None = Field(default=None, max_length=80)
    vlan: str | None = Field(default=None, max_length=80)


class IloUserIntent(BaseModel):
    username_label: str = Field(min_length=1, max_length=120)
    role: str = Field(min_length=1, max_length=120)


class IloSnmpIntent(BaseModel):
    enabled: bool = False
    destinations: list[str] = Field(default_factory=list, max_length=10)
    community_or_user_ref_labels: list[str] = Field(default_factory=list, max_length=10)


class IloTimeIntent(BaseModel):
    timezone: str | None = Field(default=None, max_length=120)
    ntp_servers: list[str] = Field(default_factory=list, max_length=10)


class IloDnsDomainIntent(BaseModel):
    domain_name: str | None = Field(default=None, max_length=180)
    dns_servers: list[str] = Field(default_factory=list, max_length=10)


class IloSetupIntentWrite(BaseModel):
    network: IloNetworkIntent = Field(default_factory=IloNetworkIntent)
    users: list[IloUserIntent] = Field(default_factory=list, max_length=20)
    snmp: IloSnmpIntent = Field(default_factory=IloSnmpIntent)
    time: IloTimeIntent = Field(default_factory=IloTimeIntent)
    dns_domain: IloDnsDomainIntent = Field(default_factory=IloDnsDomainIntent)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("*", mode="after")
    @classmethod
    def reject_secret_values(cls, value: Any) -> Any:
        _reject_secret_values(value)
        return value


class IloSetupIntentRead(IloSetupIntentWrite):
    provider_id: str
    apply_enabled: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class HpeRaidVolumeIntent(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    purpose: str = Field(min_length=1, max_length=80)
    raid_level: str = Field(min_length=2, max_length=40)
    drive_bays: list[str] = Field(default_factory=list, max_length=32)
    spare_bays: list[str] = Field(default_factory=list, max_length=32)
    spare_rebuild_mode: str | None = Field(default=None, max_length=80)
    size_policy: str = Field(default="max", min_length=1, max_length=80)
    bootable: bool = False


class HpeRaidIntentWrite(BaseModel):
    controller_ref: str | None = Field(default=None, max_length=240)
    wipe_existing_logical_drives: bool = False
    volumes: list[HpeRaidVolumeIntent] = Field(default_factory=list, max_length=16)
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("*", mode="after")
    @classmethod
    def reject_secret_values(cls, value: Any) -> Any:
        _reject_secret_values(value)
        return value


class HpeRaidIntentRead(HpeRaidIntentWrite):
    provider_id: str
    apply_enabled: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


class HpeStorageDiscoveryRead(BaseModel):
    provider_id: str
    source: str
    last_probe_time: str | None = None
    storage_inventory_available: bool = False
    server: dict[str, Any] = Field(default_factory=dict)
    controllers: list[dict[str, Any]] = Field(default_factory=list)
    physical_drives: list[dict[str, Any]] = Field(default_factory=list)
    logical_drives: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    next_safe_action: str


class HpeRaidPlanPreviewRead(BaseModel):
    provider_id: str
    status: str
    apply_enabled: bool = False
    destructive_actions_requested: bool = False
    destructive_actions_enabled: bool = False
    current_layout: HpeStorageDiscoveryRead
    desired_intent: HpeRaidIntentRead
    planned_layout: dict[str, Any] = Field(default_factory=dict)
    impact: dict[str, Any] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    disabled_actions: list[str] = Field(default_factory=list)
    next_safe_action: str


class HpeRaidApplyCreate(BaseModel):
    confirmation_phrase: str


class IloSetupPlanSectionRead(BaseModel):
    id: str
    title: str
    status: str
    apply_enabled: bool = False
    source: str
    current_observation: str
    planned_preview: str
    notes: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class IloSetupPlanPreviewRead(BaseModel):
    provider_id: str
    mode: str
    plan_only: bool = True
    apply_enabled: bool = False
    generated_from: str
    sections: list[IloSetupPlanSectionRead]
    firmware_readiness_handoff: dict[str, Any] = Field(default_factory=dict)
    reports_artifacts: list[IloReportArtifactPlaceholderRead] = Field(default_factory=list)
    disabled_dangerous_actions: list[ProviderActionRead] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    removable_warnings: list[str] = Field(default_factory=list)


class IloSetupApplyCreate(BaseModel):
    confirmation_phrase: str
    requested_actions: list[str] = Field(default_factory=list)
    destructive_action_requested: bool = False


class IloSetupCompareRowRead(BaseModel):
    section: str
    field: str
    label: str
    desired: str
    discovered: str
    status: str
    next_safe_action: str
    apply_enabled: bool = False


class IloSetupCompareSectionRead(BaseModel):
    id: str
    title: str
    status: str
    apply_enabled: bool = False
    next_safe_action: str
    rows: list[IloSetupCompareRowRead]


class IloSetupCompareReportRead(BaseModel):
    provider_id: str
    mode: str
    source: str
    apply_enabled: bool = False
    sections: list[IloSetupCompareSectionRead]
    disabled_dangerous_actions: list[ProviderActionRead] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    removable_warnings: list[str] = Field(default_factory=list)


class IloDestructiveRebuildRequirementRead(BaseModel):
    id: str
    label: str
    status: str
    detail: str


class IloRealChangeLaneRead(BaseModel):
    id: str
    label: str
    status: str
    execution_enabled: bool = False
    next_safe_action: str
    required_gates: list[str] = Field(default_factory=list)
    blocked_actions: list[str] = Field(default_factory=list)


class IloDestructiveRebuildPreviewRead(BaseModel):
    provider_id: str
    provider_mode: str
    status: str
    destructive_enabled: bool = False
    apply_enabled: bool = False
    safe_next_action: str
    target_identity: dict[str, Any] = Field(default_factory=dict)
    discovered_state: dict[str, Any] = Field(default_factory=dict)
    intended_scope: list[str] = Field(default_factory=list)
    required_capabilities: list[IloDestructiveRebuildRequirementRead] = Field(default_factory=list)
    real_change_lanes: list[IloRealChangeLaneRead] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    future_workflow_handoff: dict[str, Any] = Field(default_factory=dict)
    confirmation_requirements: dict[str, Any] = Field(default_factory=dict)
    artifact_requirements: list[str] = Field(default_factory=list)


class IloReportPreviewRead(BaseModel):
    provider_id: str
    provider_mode: str
    generated_at: datetime
    source: str
    apply_enabled: bool = False
    readiness_summary: dict[str, Any] = Field(default_factory=dict)
    desired_setup_intent: dict[str, Any] = Field(default_factory=dict)
    setup_compare_report: IloSetupCompareReportRead
    setup_plan_preview: dict[str, Any] = Field(default_factory=dict)
    destructive_rebuild_preview: dict[str, Any] = Field(default_factory=dict)
    firmware_readiness: dict[str, Any] = Field(default_factory=dict)
    media_inventory_summary: dict[str, Any] = Field(default_factory=dict)
    disabled_dangerous_actions: list[ProviderActionRead] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    removable_warnings: list[str] = Field(default_factory=list)


def _reject_secret_values(value: Any) -> None:
    if isinstance(value, str):
        if SECRET_VALUE_RE.search(value):
            raise ValueError(
                "iLO setup intent stores labels/placeholders only; secret-looking values are not allowed"
            )
        return
    if isinstance(value, BaseModel):
        _reject_secret_values(value.model_dump())
        return
    if isinstance(value, dict):
        for nested in value.values():
            _reject_secret_values(nested)
        return
    if isinstance(value, list):
        for nested in value:
            _reject_secret_values(nested)


class ProviderStatusRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

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


class CiscoSetupReadinessRead(BaseModel):
    provider_id: str
    phase: str
    planned_management_ip: str | None = None
    management_configured: bool
    state_boundaries: dict[str, Any] = Field(default_factory=dict)
    console: dict[str, Any]
    ethernet_readiness: dict[str, Any] = Field(default_factory=dict)
    real_lab_run: dict[str, Any] = Field(default_factory=dict)
    password_recovery: dict[str, Any] = Field(default_factory=dict)
    bootstrap_preview: dict[str, Any]
    ssh_scp_readiness: dict[str, Any]
    ansible: dict[str, Any]
    backup_report: dict[str, Any]
    setup_wizard_plan: dict[str, Any] | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    disabled_actions: list[str] = Field(default_factory=list)
    next_safe_action: str


class CiscoSetupWizardPlanRead(BaseModel):
    provider_id: str
    status: str
    apply_enabled: bool
    planned_management_ip: str | None = None
    detected_prompt_state: str
    setup_wizard_detected: bool
    message: str
    why_blocked: list[str] = Field(default_factory=list)
    future_guarded_plan_preview: list[str] = Field(default_factory=list)
    not_attempted: list[str] = Field(default_factory=list)
    disabled_actions: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_safe_action: str


class CiscoBootstrapRequirementsRead(BaseModel):
    provider_id: str
    status: str
    apply_enabled: bool
    management_configured: bool
    requirements: dict[str, Any]
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    disabled_actions: list[str] = Field(default_factory=list)
    not_attempted: list[str] = Field(default_factory=list)
    next_safe_action: str


class CiscoBootstrapRequirementsUpdate(BaseModel):
    planned_management_ip: str
    subnet_prefix: str
    gateway: str
    management_vlan: str | None = None
    management_interface: str | None = None
    management_strategy: str
    hostname: str
    domain_name: str
    dns_servers: list[str] = Field(default_factory=list)
    local_admin_username_configured: bool = False
    local_admin_username_reference: str | None = None
    operator_notes: str | None = None


class CiscoConsoleBootstrapPlanRead(BaseModel):
    provider_id: str
    status: str
    target: dict[str, Any]
    apply_enabled: bool
    execution_supported: bool
    serial_writes_attempted: bool
    flow: str
    prompt_state: str
    prompt_detail: str
    prompt_checked_at: str | None = None
    summary: list[str] = Field(default_factory=list)
    intended_steps: list[str] = Field(default_factory=list)
    command_preview: list[str] = Field(default_factory=list)
    redacted_command_summary: list[str] = Field(default_factory=list)
    commands_redacted: bool
    blocker_summary: dict[str, Any] = Field(default_factory=dict)
    artifact_preview: dict[str, Any] = Field(default_factory=dict)
    destructive_actions_disabled: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    confirmation_phrase: str
    next_safe_action: str


class CiscoConsoleBootstrapApplyCreate(BaseModel):
    confirmation_phrase: str
    requested_actions: list[str] = Field(default_factory=list)
    destructive_action_requested: bool = False


class NetAppPlanPreviewRead(BaseModel):
    provider_id: str
    mode: str
    apply_enabled: bool = False
    netapp_configured: bool
    planned_targets: dict[str, Any]
    current_discovered_targets: dict[str, Any] | None = None
    readiness_summary: dict[str, Any]
    setup_readiness: dict[str, Any] | None = None
    upgrade_readiness: dict[str, Any] | None = None
    readiness_buckets: dict[str, Any]
    cluster_intent_preview: dict[str, Any]
    svm_intent_preview: dict[str, Any]
    lif_intent_preview: dict[str, Any]
    storage_iscsi_plan_preview: dict[str, Any]
    readiness_comparison_preview: dict[str, Any] | None = None
    upgrade_readiness_preview: dict[str, Any]
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    removable_warnings: list[str] = Field(default_factory=list)
    disabled_actions: list[ProviderActionRead] = Field(default_factory=list)
    artifact_placeholders: list[str] = Field(default_factory=list)
    next_safe_action: str


class NetAppUpgradeReadinessRead(BaseModel):
    provider_id: str
    mode: str
    apply_enabled: bool = False
    upgrade_enabled: bool = False
    setup_ready: bool = False
    readiness_scope: str = "upgrade"
    current_version_source: str
    current_version: str | None = None
    current_version_confidence: str
    media_inventory_mode: str
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    recommended_target: str | None = None
    required_intermediate_versions: list[str] = Field(default_factory=list)
    upgrade_chain: list[dict[str, Any]] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    removable_warnings: list[str] = Field(default_factory=list)
    next_safe_action: str
    disabled_actions: list[ProviderActionRead] = Field(default_factory=list)


class NetAppConsoleReadinessRead(BaseModel):
    provider_id: str
    mode: str
    bootstrap_enabled: bool = False
    console_probe_enabled: bool = False
    apply_enabled: bool = False
    netapp_configured: bool
    planned_targets: dict[str, Any]
    current_discovered_targets: dict[str, Any] | None = None
    prerequisites: list[dict[str, Any]] = Field(default_factory=list)
    manual_steps: list[str] = Field(default_factory=list)
    expected_prompts_or_states: list[dict[str, Any]] = Field(default_factory=list)
    readiness_buckets: dict[str, Any]
    observations: dict[str, Any] | None = None
    observation_summary: dict[str, Any] | None = None
    observation_blockers: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    removable_warnings: list[str] = Field(default_factory=list)
    disabled_actions: list[ProviderActionRead] = Field(default_factory=list)
    next_safe_action: str


class NetAppObservationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_console_state: Literal[
        "unknown",
        "loader_prompt",
        "boot_menu",
        "cluster_setup_prompt",
        "existing_cluster_login",
        "other",
    ] = "unknown"
    controller_a_console_seen: bool = False
    controller_b_console_seen: bool = False
    controller_a_sp_cabled: bool = False
    controller_b_sp_cabled: bool = False
    management_network_reviewed: bool = False
    planned_targets_reviewed: bool = False
    existing_data_risk_acknowledged: bool = False
    operator_notes: str = Field(default="", max_length=1200)

    @field_validator("operator_notes", mode="before")
    @classmethod
    def strip_operator_notes(cls, value: str | None) -> str:
        return validate_netapp_operator_notes(value)


class NetAppObservationRead(NetAppObservationUpdate):
    provider_id: str
    updated_at: datetime
    updated_by: str
    mock_only: bool = True
    sent_to_netapp: bool = False


class NetAppReadinessComparisonRead(BaseModel):
    provider_id: str
    mode: str
    comparison_enabled: bool = True
    apply_enabled: bool = False
    discovery_enabled: bool = False
    planned_targets: dict[str, Any]
    current_discovered_targets: dict[str, Any] | None = None
    observations: dict[str, Any]
    comparison_items: list[dict[str, Any]] = Field(default_factory=list)
    matched_items: list[dict[str, Any]] = Field(default_factory=list)
    unknown_items: list[dict[str, Any]] = Field(default_factory=list)
    warning_items: list[dict[str, Any]] = Field(default_factory=list)
    blocker_items: list[dict[str, Any]] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    removable_warnings: list[str] = Field(default_factory=list)
    next_safe_action: str
    disabled_actions: list[ProviderActionRead] = Field(default_factory=list)


class ProviderArtifactRead(BaseModel):
    id: str
    provider_id: str
    kind: str
    title: str
    description: str
    status: str
    mock_only: bool
    redacted: bool
    downloadable: bool
    download_url: str | None = None
    generated_at: datetime
    metadata: dict[str, Any]


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
