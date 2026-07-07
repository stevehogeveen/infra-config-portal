from __future__ import annotations

import re
from datetime import date, datetime
from ipaddress import ip_address, ip_network
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.enums import EnvironmentName, RequestStatus, WorkflowRunStatus
from app.services.list_utils import unique_strings
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


class LabAddressPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subnet: str | None = Field(default=None, max_length=80)
    ilo: str | None = Field(default=None, max_length=80)
    ilo_initial: str | None = Field(default=None, max_length=80)
    server_embedded_nic: str | None = Field(default=None, max_length=80)
    esxi_management: str | None = Field(default=None, max_length=80)
    cisco_management: str | None = Field(default=None, max_length=80)
    ansible_control_host: str | None = Field(default=None, max_length=80)
    netapp_controller_a_sp: str | None = Field(default=None, max_length=80)
    netapp_controller_b_sp: str | None = Field(default=None, max_length=80)
    netapp_cluster_mgmt: str | None = Field(default=None, max_length=80)
    netapp_node_a_mgmt: str | None = Field(default=None, max_length=80)
    netapp_node_b_mgmt: str | None = Field(default=None, max_length=80)
    netapp_svm_mgmt: str | None = Field(default=None, max_length=80)
    netapp_nfs_lifs: list[str] = Field(default_factory=list, max_length=16)
    netapp_iscsi_lifs: list[str] = Field(default_factory=list, max_length=16)

    @field_validator(
        "subnet",
        "ilo",
        "ilo_initial",
        "server_embedded_nic",
        "esxi_management",
        "cisco_management",
        "ansible_control_host",
        "netapp_controller_a_sp",
        "netapp_controller_b_sp",
        "netapp_cluster_mgmt",
        "netapp_node_a_mgmt",
        "netapp_node_b_mgmt",
        "netapp_svm_mgmt",
        mode="before",
    )
    @classmethod
    def strip_address(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("netapp_nfs_lifs", "netapp_iscsi_lifs", mode="before")
    @classmethod
    def split_lifs(cls, value: Any) -> list[str]:
        return _clean_unique_string_list(value)

    @field_validator("subnet")
    @classmethod
    def validate_subnet(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ip_network(value, strict=False)
            except ValueError as exc:
                raise ValueError("subnet must be an IPv4 or IPv6 CIDR") from exc
        return value

    @field_validator(
        "ilo",
        "ilo_initial",
        "server_embedded_nic",
        "esxi_management",
        "cisco_management",
        "ansible_control_host",
        "netapp_controller_a_sp",
        "netapp_controller_b_sp",
        "netapp_cluster_mgmt",
        "netapp_node_a_mgmt",
        "netapp_node_b_mgmt",
        "netapp_svm_mgmt",
    )
    @classmethod
    def validate_ip_address(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ip_address(value)
            except ValueError as exc:
                raise ValueError("address must be an IPv4 or IPv6 address") from exc
        return value

    @field_validator("netapp_nfs_lifs", "netapp_iscsi_lifs")
    @classmethod
    def validate_lifs(cls, value: list[str]) -> list[str]:
        cleaned = _clean_unique_string_list(value)
        for item in cleaned:
            try:
                ip_address(item)
            except ValueError as exc:
                raise ValueError("NetApp LIFs must be IPv4 or IPv6 addresses") from exc
        return cleaned


class LabGlobalSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subnet_prefix: int = Field(default=24, ge=23, le=29)
    gateway: str | None = Field(default=None, max_length=80)
    support_unit: str | None = Field(default=None, max_length=120)
    domain_name: str | None = Field(default=None, max_length=160)
    dom_dc: str | None = Field(default=None, max_length=80)
    dns_servers: list[str] = Field(default_factory=list, max_length=8)
    ntp_servers: list[str] = Field(default_factory=list, max_length=8)
    timezone: str | None = Field(default=None, max_length=80)
    netapp_enabled: bool = True
    netapp_disabled_reason: str | None = Field(default=None, max_length=300)
    vcenter_enabled: bool = False
    vlan_id: str | None = Field(default=None, max_length=80)
    mtu: int | None = Field(default=None, ge=576, le=9216)

    @field_validator(
        "gateway",
        "support_unit",
        "domain_name",
        "dom_dc",
        "timezone",
        "netapp_disabled_reason",
        "vlan_id",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("dns_servers", "ntp_servers", mode="before")
    @classmethod
    def split_server_list(cls, value: Any) -> list[str]:
        return _clean_unique_string_list(value)

    @field_validator("gateway")
    @classmethod
    def validate_gateway(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ip_address(value)
            except ValueError as exc:
                raise ValueError("gateway must be an IPv4 or IPv6 address") from exc
        return value

    @field_validator("dns_servers", "ntp_servers")
    @classmethod
    def validate_server_list(cls, value: list[str]) -> list[str]:
        cleaned = _clean_unique_string_list(value)
        for item in cleaned:
            try:
                ip_address(item)
            except ValueError as exc:
                raise ValueError("server values must be IPv4 or IPv6 addresses") from exc
        return cleaned


class LabSubnetOptionRead(BaseModel):
    prefix: int
    cidr_suffix: str
    label: str
    usable_hosts: int
    netapp_supported: bool
    netapp_disabled_reason: str | None = None
    default_topology: str | None = None


class LabProfileDevices(BaseModel):
    model_config = ConfigDict(extra="allow")

    gateway: str | None = None
    switch_primary: str | None = None
    switch_secondary: str | None = None
    reserved: list[str] = Field(default_factory=list)
    ups: str | None = None
    backup_storage: str | None = None
    utility_vm: str | None = None
    esxi: str | None = None
    ilo: str | None = None
    cisco: str | None = None
    server_model: Literal["gen10", "gen10plus"] | None = None
    netapp: dict[str, Any] | None = None
    vcenter: str | None = None


class LabProfileFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid")

    netapp_enabled: bool = True
    vcenter_enabled: bool = False
    deployment_mode: Literal[
        "server_netapp_direct",
        "server_netapp_vcenter",
        "single_server_local_storage",
        "unsupported_vcenter_without_netapp",
    ] = "server_netapp_direct"
    deployment_label: str = Field(default="Server + NetApp direct attach", max_length=120)
    deployment_supported: bool = False
    storage_location: Literal["netapp_shared", "server_local"] = "netapp_shared"
    firmware_gate_enabled: bool = True
    build_verification_enabled: bool = True
    storage_protocol: Literal["nfs", "iscsi", "local", "none"] = "nfs"
    disable_ipv6: bool = True
    block_legacy_protocols: bool = True
    enable_snmp: bool = False
    enable_ntp: bool = True
    enable_dns: bool = True
    netapp_disabled_reason: str | None = Field(default=None, max_length=300)
    vcenter_disabled_reason: str | None = Field(default=None, max_length=300)

    @field_validator("deployment_mode", "storage_location", "storage_protocol", mode="before")
    @classmethod
    def normalize_choice(cls, value: Any) -> Any:
        if value is None:
            return value
        return str(value).strip().lower()


class LabProfileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1200)
    profile_topology: Literal["high_address_lab", "compact_edge_lab", "custom"] | None = None
    subnet_cidr: str | None = Field(default=None, max_length=80)
    gateway: str | None = Field(default=None, max_length=80)
    dns: list[str] = Field(default_factory=list, max_length=8)
    ntp: list[str] = Field(default_factory=list, max_length=8)
    vlan_id: str | None = Field(default=None, max_length=80)
    mtu: int | None = Field(default=None, ge=576, le=9216)
    devices: LabProfileDevices = Field(default_factory=LabProfileDevices)
    features: LabProfileFeatures = Field(default_factory=LabProfileFeatures)
    global_settings: LabGlobalSettings = Field(default_factory=LabGlobalSettings)
    address_plan: LabAddressPlan = Field(default_factory=LabAddressPlan)

    @field_validator(
        "name",
        "description",
        "profile_topology",
        "subnet_cidr",
        "gateway",
        "vlan_id",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return str(value).strip()

    @field_validator("dns", "ntp", mode="before")
    @classmethod
    def split_top_level_server_list(cls, value: Any) -> list[str]:
        return _clean_unique_string_list(value)

    @field_validator("*", mode="after")
    @classmethod
    def reject_secret_values(cls, value: Any) -> Any:
        _reject_secret_values(value)
        return value


class LabProfileRevisionRead(BaseModel):
    version: int
    saved_at: datetime
    name: str
    description: str
    profile_topology: str = "high_address_lab"
    subnet_cidr: str | None = None
    gateway: str | None = None
    dns: list[str] = Field(default_factory=list)
    ntp: list[str] = Field(default_factory=list)
    vlan_id: str | None = None
    mtu: int | None = None
    devices: LabProfileDevices = Field(default_factory=LabProfileDevices)
    features: LabProfileFeatures = Field(default_factory=LabProfileFeatures)
    global_settings: LabGlobalSettings
    address_plan: LabAddressPlan


class LabProfileRead(BaseModel):
    id: str
    name: str
    description: str
    profile_topology: str = "high_address_lab"
    subnet_cidr: str | None = None
    gateway: str | None = None
    dns: list[str] = Field(default_factory=list)
    ntp: list[str] = Field(default_factory=list)
    vlan_id: str | None = None
    mtu: int | None = None
    devices: LabProfileDevices = Field(default_factory=LabProfileDevices)
    features: LabProfileFeatures = Field(default_factory=LabProfileFeatures)
    global_settings: LabGlobalSettings
    address_plan: LabAddressPlan
    resolved_address_plan: LabAddressPlan
    not_in_scope_stages: list[str] = Field(default_factory=list)
    mismatch_warnings: list[dict[str, Any]] = Field(default_factory=list)
    fix_guidance: list[dict[str, Any]] = Field(default_factory=list)
    source: str
    version: int
    active: bool
    created_at: datetime
    updated_at: datetime
    last_selected_at: datetime | None = None
    history: list[LabProfileRevisionRead] = Field(default_factory=list)


class LabProfileContextRead(BaseModel):
    active_profile: LabProfileRead
    topology: str
    resolved_address_plan: LabAddressPlan
    enabled_features: LabProfileFeatures
    disabled_features: dict[str, str] = Field(default_factory=dict)
    not_in_scope_stages: list[str] = Field(default_factory=list)
    mismatch_warnings: list[dict[str, Any]] = Field(default_factory=list)
    fix_guidance: list[dict[str, Any]] = Field(default_factory=list)


class LabProfileListRead(BaseModel):
    active_profile: LabProfileRead
    active_context: LabProfileContextRead
    runtime_profile: LabProfileRead
    profiles: list[LabProfileRead]
    subnet_options: list[LabSubnetOptionRead] = Field(default_factory=list)
    store_path: str
    mock_only: bool = True
    next_safe_action: str


class LabProfileRuntimeApplyRead(BaseModel):
    applied: bool
    env_path: str
    updated_keys: list[str] = Field(default_factory=list)
    removed_keys: list[str] = Field(default_factory=list)
    restart_required: bool = True
    message: str
    next_action: str
    lab_profiles: LabProfileListRead


class TopologyDesignDraftWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str = Field(min_length=1, max_length=120)
    scenario: Literal["server_netapp_direct", "server_netapp_vcenter", "single_server_local_storage"]
    subnet: str | None = Field(default=None, max_length=80)
    placements: dict[str, str | None] = Field(default_factory=dict)
    device_settings: dict[str, dict[str, str]] = Field(default_factory=dict)
    lane_settings: dict[str, dict[str, str]] = Field(default_factory=dict)
    connection_settings: dict[str, dict[str, str]] = Field(default_factory=dict)

    @field_validator("profile_id", "scenario", "subnet", mode="before")
    @classmethod
    def strip_topology_design_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("*", mode="after")
    @classmethod
    def reject_topology_design_secret_values(cls, value: Any) -> Any:
        _reject_secret_values(value)
        return value

    @field_validator("placements")
    @classmethod
    def validate_topology_design_placement_keys(cls, value: dict[str, str | None]) -> dict[str, str | None]:
        allowed = {"u1", "u2", "u3", "u4", "virtual"}
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"placements contains unknown rack slot(s): {', '.join(unknown)}")
        return value

    @field_validator("device_settings")
    @classmethod
    def validate_topology_design_device_settings(cls, value: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
        allowed_parts = {"switch", "server-gen10", "server-gen10plus", "netapp", "vcenter", "windows"}
        allowed_fields = {
            "datastore",
            "gateway",
            "iscsi_lifs",
            "management_ip",
            "mgmt_vlan",
            "name",
            "nfs_lifs",
            "notes",
            "ports",
            "protocol",
            "raid_boot",
            "raid_data",
            "role",
            "san_ports",
            "storage_vlan",
            "vm_network",
        }
        unknown_parts = sorted(set(value) - allowed_parts)
        if unknown_parts:
            raise ValueError(f"device_settings contains unknown device(s): {', '.join(unknown_parts)}")
        for part, settings in value.items():
            unknown_fields = sorted(set(settings) - allowed_fields)
            if unknown_fields:
                raise ValueError(f"device_settings for {part} contains unknown field(s): {', '.join(unknown_fields)}")
            for field_name, field_value in settings.items():
                if len(str(field_value)) > 240:
                    raise ValueError(f"device_settings {part}.{field_name} is too long")
        return value

    @field_validator("lane_settings")
    @classmethod
    def validate_topology_design_lane_settings(cls, value: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
        allowed_lanes = {"management", "storage", "virtualization"}
        allowed_fields = {"mtu", "notes", "protocol", "purpose", "source", "target", "vlan"}
        unknown_lanes = sorted(set(value) - allowed_lanes)
        if unknown_lanes:
            raise ValueError(f"lane_settings contains unknown lane(s): {', '.join(unknown_lanes)}")
        for lane, settings in value.items():
            unknown_fields = sorted(set(settings) - allowed_fields)
            if unknown_fields:
                raise ValueError(f"lane_settings for {lane} contains unknown field(s): {', '.join(unknown_fields)}")
            for field_name, field_value in settings.items():
                if len(str(field_value)) > 240:
                    raise ValueError(f"lane_settings {lane}.{field_name} is too long")
        return value

    @field_validator("connection_settings")
    @classmethod
    def validate_topology_design_connection_settings(cls, value: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
        allowed_connections = {"switch-server", "switch-netapp", "server-netapp", "server-vm"}
        allowed_fields = {"lane", "mtu", "notes", "protocol", "source", "status", "target", "vlan"}
        unknown_connections = sorted(set(value) - allowed_connections)
        if unknown_connections:
            raise ValueError(f"connection_settings contains unknown connection(s): {', '.join(unknown_connections)}")
        for connection, settings in value.items():
            unknown_fields = sorted(set(settings) - allowed_fields)
            if unknown_fields:
                raise ValueError(f"connection_settings for {connection} contains unknown field(s): {', '.join(unknown_fields)}")
            for field_name, field_value in settings.items():
                if len(str(field_value)) > 240:
                    raise ValueError(f"connection_settings {connection}.{field_name} is too long")
        return value


class TopologyDesignPersistenceItemRead(BaseModel):
    choice: str
    persists_to: str
    commit_state: str
    hardware_effect: str


class TopologyDesignDraftRead(BaseModel):
    id: str
    profile_id: str
    scenario: str
    subnet: str | None = None
    placements: dict[str, str | None] = Field(default_factory=dict)
    device_settings: dict[str, dict[str, str]] = Field(default_factory=dict)
    lane_settings: dict[str, dict[str, str]] = Field(default_factory=dict)
    connection_settings: dict[str, dict[str, str]] = Field(default_factory=dict)
    source: Literal["default", "saved"]
    draft_saved: bool
    hardware_touched: bool = False
    updated_at: datetime | None = None
    store_path: str
    message: str
    persistence_inventory: list[TopologyDesignPersistenceItemRead] = Field(default_factory=list)


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
    file_name: str | None = None
    file_path: str | None = None
    detected_vendor: str | None = None
    detected_product: str | None = None
    detected_version: str | None = None
    confidence: str | None = None


class MediaInventoryRead(BaseModel):
    mode: str
    configured_directories: list[str]
    configured_directory_paths: list[str] = Field(default_factory=list, repr=False)
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


class IloBaselineKitProfileRead(BaseModel):
    kit_id: str
    support_unit: str
    subnet_mask: str
    gateway: str
    dom_dc: str
    derived_subnet: str
    source_type: str = "operator_config"
    checked_at: str | None = None
    freshness: str = "live"
    recheck_command: str = "GET /api/v1/lab/profiles"


class IloBaselineDiscoveryRangeRead(BaseModel):
    source_subnet: str
    default_start_host: str
    default_end_host: str
    addresses: list[str] = Field(default_factory=list)
    override_supported: bool = True
    override_active: bool = False
    source_type: str = "operator_config"
    checked_at: str | None = None
    freshness: str = "live"
    recheck_command: str = "GET /api/v1/providers/hpe-ilo/baseline-preview"


class IloBaselineReadinessCheckRead(BaseModel):
    name: str
    status: str
    current: str
    desired: str
    source_type: str
    checked_at: str | None = None
    freshness: str
    message: str
    next_action: str


class IloBaselineSectionRead(BaseModel):
    id: str
    title: str
    status: str
    items: dict[str, Any] = Field(default_factory=dict)
    secret_refs: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class IloBaselinePlanRowRead(BaseModel):
    section: str
    item: str
    current: Any
    desired: Any
    action: Literal[
        "no_change",
        "create",
        "update",
        "check",
        "warning",
        "blocked",
        "requires_confirmation",
    ]
    severity: str
    message: str


class IloBaselineBlockerRead(BaseModel):
    problem: str
    source: str
    current_value: str
    expected_value: str
    where_to_fix: str
    recommended_action: str
    copyable_command: str | None = None
    recheck_command: str
    evidence_links: list[str] = Field(default_factory=list)


class IloBaselineReadinessRead(BaseModel):
    provider_id: str
    source_provider_id: str
    provider_mode: str
    generated_at: datetime
    source_type: str
    checked_at: str | None = None
    freshness: str
    kit_profile: IloBaselineKitProfileRead
    discovery_range: IloBaselineDiscoveryRangeRead
    connection_readiness: list[IloBaselineReadinessCheckRead]
    current_state: dict[str, Any] = Field(default_factory=dict)
    comparison_rows: list[IloBaselinePlanRowRead] = Field(default_factory=list)
    reset_required: bool = False
    apply_enabled: bool = False
    apply_reason: str
    blockers: list[IloBaselineBlockerRead] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_action: str


class IloBaselinePreviewRead(IloBaselineReadinessRead):
    expected_baseline_sections: list[IloBaselineSectionRead] = Field(default_factory=list)
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
    local_storage_readiness: dict[str, Any] = Field(default_factory=dict)
    impact: dict[str, Any] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    disabled_actions: list[str] = Field(default_factory=list)
    next_safe_action: str


class HpeRaidApplyCreate(BaseModel):
    confirmation_phrase: str


class HpeRaidFactoryResetCreate(BaseModel):
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


def _clean_unique_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        candidates = value.split(",")
    elif isinstance(value, (list, tuple)):
        candidates = value
    else:
        candidates = [value]
    return unique_strings(candidates)


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
    source_type: str = "not_checked"
    checked_at: str | None = None
    freshness: str = "unknown"
    ttl_seconds: int | None = None
    stale_after_seconds: int | None = None
    is_current: bool = False
    is_operator_visible: bool = True
    recheck_command: str | None = None
    evidence_artifacts: list[str] = Field(default_factory=list)
    configuration: dict[str, Any] = Field(default_factory=dict)
    discovery: dict[str, Any] | None = None
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    safe_actions: list[ProviderActionRead] = Field(default_factory=list)
    disabled_actions: list[ProviderActionRead] = Field(default_factory=list)
    last_probe_result: dict[str, Any] | None = None
    last_probe_time: str | None = None


class ProviderModeOptionRead(BaseModel):
    mode: str
    label: str
    status: str
    description: str
    restart_command: str
    requirements: list[str] = Field(default_factory=list)


class ProviderModeSettingsRead(BaseModel):
    current_mode: str
    desired_mode: str
    pending_restart: bool
    options: list[ProviderModeOptionRead]
    restart_command: str
    expected_runtime_mode: str = "local-lab-readwrite"
    dev_test_banner: str | None = None
    mode_env_path: str
    store_path: str
    updated_at: datetime | None = None
    next_safe_action: str


class ProviderModeSettingsWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    desired_mode: Literal["local-readonly", "local-lab-readwrite"]


class LabSafetyFlagRead(BaseModel):
    name: str
    label: str
    description: str
    required: bool
    value: str | bool | None = None
    enabled: bool
    source: str
    status: str


class LabSafetySettingsRead(BaseModel):
    flags: list[LabSafetyFlagRead]
    store_path: str
    updated_at: datetime | None = None
    confirmation_phrase: str
    device_reconfiguration_confirmation_phrase: str
    next_safe_action: str


class LabSafetySettingsWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lab_environment: Literal["isolated-real-lab"] | None = None
    lab_acknowledge_real_hardware: bool | None = None
    lab_acknowledge_device_reconfiguration: bool | None = None
    lab_acknowledge_data_loss_risk: bool | None = None
    lab_acknowledge_lab_only: bool | None = None
    confirmation_phrase: str | None = None
    device_reconfiguration_confirmation_phrase: str | None = None


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
    netapp_configured_source: str | None = None
    manual_env_flag_required: bool = False
    runtime_state: dict[str, Any] | None = None
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
    storage_nfs_vcenter_preview: dict[str, Any] | None = None
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
    netapp_configured_source: str | None = None
    legacy_netapp_configured_env: bool | None = None
    manual_env_flag_required: bool = False
    runtime_state: dict[str, Any] | None = None
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


class LabValidationItemRead(BaseModel):
    id: str
    label: str
    category: str
    stage: str
    status: Literal[
        "ready",
        "partial",
        "blocked",
        "not_configured",
        "not_checked",
        "warning",
        "not_in_scope",
    ]
    current_state: str
    desired_state: str
    setup_summary: str
    next_action: str
    login_hint: str
    management_url: str | None = None
    ssh_target: str | None = None
    proof_points: list[str] = Field(default_factory=list)
    evidence_artifacts: list[str] = Field(default_factory=list)
    evidence_collapsed_by_default: bool = True
    last_checked: str | None = None
    source_type: Literal["live_probe", "live_cached", "historical_artifact", "not_checked"]
    freshness: str
    blockers: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    recheck_command: str
    linked_workflow_action: dict[str, Any] | None = None


class LabValidationProofLinkRead(BaseModel):
    component_id: str
    component_label: str
    path: str


class LabValidationSummaryRead(BaseModel):
    overall_status: str
    progress_counts: dict[str, int]
    top_blocker: dict[str, Any] | None = None
    validation_items: list[LabValidationItemRead]
    proof_links: list[LabValidationProofLinkRead] = Field(default_factory=list)
    generated_at: str
    next_action: str
    source_type: str
    freshness: str
    handoff_report: str
    warnings: list[str] = Field(default_factory=list)


class ReportIssueRead(BaseModel):
    id: str
    source: str
    source_stage: str
    source_stage_id: str | None = None
    source_stage_label: str | None = None
    source_action_id: str | None = None
    source_action_label: str | None = None
    source_action_link: str | None = None
    severity: Literal["critical", "warning", "info", "success"] | str
    classification: Literal[
        "hard_fail",
        "stale_config",
        "operator_action_required",
        "blocked_by_prior_stage",
        "not_configured_yet",
        "warning",
        "passed",
    ] | str
    status: Literal["open", "blocked", "stale", "reviewed", "resolved"] | str
    source_type: str = "not_checked"
    freshness: str = "unknown"
    ttl_seconds: int | None = None
    stale_after_seconds: int | None = None
    is_current: bool = False
    is_operator_visible: bool = True
    title: str
    summary: str
    problem: str
    next_action: str
    recheck_command: str
    source_report: str | None = None
    evidence_artifacts: list[str] = Field(default_factory=list)
    linked_page: str
    last_checked: str | None = None
    can_auto_fix: bool = False
    auto_fix_action_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ReportSourceSummaryRead(BaseModel):
    id: str
    label: str
    status: str
    critical: int = 0
    warning: int = 0
    info: int = 0
    success: int = 0
    issue_count: int = 0
    source_type: str = "not_checked"
    freshness: str = "unknown"
    checked_at: str | None = None
    is_current: bool = False
    is_operator_visible: bool = True
    linked_page: str
    recheck_command: str | None = None
    last_report: str | None = None


class ReportPageBadgeRead(BaseModel):
    page: str
    status: str
    label: str
    count: int = 0
    critical: int = 0
    warning: int = 0
    not_configured_yet: int = 0
    success: int = 0
    sources: list[str] = Field(default_factory=list)
    default_filter: str = "all"


class ReportCenterRead(BaseModel):
    checked_at: str
    overall_status: str
    counts: dict[str, int]
    classification_counts: dict[str, int] = Field(default_factory=dict)
    top_issues: list[ReportIssueRead] = Field(default_factory=list)
    issues: list[ReportIssueRead] = Field(default_factory=list)
    sources: list[ReportSourceSummaryRead] = Field(default_factory=list)
    evidence_artifacts: list[str] = Field(default_factory=list)
    last_reports: dict[str, str | None] = Field(default_factory=dict)
    page_badges: dict[str, ReportPageBadgeRead] = Field(default_factory=dict)


class ReportCenterSummaryRead(BaseModel):
    checked_at: str
    overall_status: str
    counts: dict[str, int]
    classification_counts: dict[str, int] = Field(default_factory=dict)
    top_issues: list[ReportIssueRead] = Field(default_factory=list)
    sources: list[ReportSourceSummaryRead] = Field(default_factory=list)
    page_badges: dict[str, ReportPageBadgeRead] = Field(default_factory=dict)


class ControlActionInputRead(BaseModel):
    name: str
    label: str
    required: bool = False
    secret: bool = False
    description: str = ""


class ControlStateItemRead(BaseModel):
    label: str
    value: str
    status: str | None = None
    detail: str | None = None


class ControlPlanDiffItemRead(BaseModel):
    label: str
    current: str
    desired: str
    status: str
    note: str | None = None


class ControlReportLinkRead(BaseModel):
    label: str
    path: str
    status: str


class ControlEditableConfigFieldRead(BaseModel):
    label: str
    value: str
    source: str


class ControlEditableConfigFieldWrite(BaseModel):
    label: str = Field(max_length=80)
    value: str | None = Field(default=None, max_length=240)

    @field_validator("label", "value", mode="before")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class ControlAccessConfigWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_time_configuring: bool = True
    original_dhcp_ip: str | None = Field(default=None, max_length=80)
    username_reference: str | None = Field(default=None, max_length=120)
    password_configured: bool = False
    password_reference_label: str | None = Field(default=None, max_length=120)
    editable_fields: list[ControlEditableConfigFieldWrite] | None = Field(default=None, max_length=12)

    @field_validator(
        "original_dhcp_ip",
        "username_reference",
        "password_reference_label",
        mode="before",
    )
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @field_validator("original_dhcp_ip")
    @classmethod
    def validate_original_dhcp_ip(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ip_address(value)
            except ValueError as exc:
                raise ValueError("original DHCP/current access IP must be an IPv4 or IPv6 address") from exc
        return value

    @field_validator("*", mode="after")
    @classmethod
    def reject_secret_values(cls, value: Any) -> Any:
        _reject_secret_values(value)
        return value


class ControlAccessConfigRead(BaseModel):
    section_id: str
    title: str
    access_method: str
    first_time_configuring: bool
    first_time_note: str
    original_dhcp_ip: str | None = None
    desired_management_ip: str | None = None
    desired_address_label: str
    username_reference: str | None = None
    password_configured: bool
    password_reference_label: str | None = None
    editable_fields: list[ControlEditableConfigFieldRead] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None


class ControlActionRead(BaseModel):
    id: str
    label: str
    section_id: str
    device_stage: str
    description: str
    classification: Literal["read-only", "write", "destructive", "upgrade"]
    required_inputs: list[ControlActionInputRead] = Field(default_factory=list)
    required_flags: list[str] = Field(default_factory=list)
    required_confirmations: list[str] = Field(default_factory=list)
    availability: str
    blocker: str | None = None
    last_run_status: str
    last_run_at: str | None = None
    last_report: str | None = None
    suggested_command: str | None = None
    method: str | None = None
    api_endpoint: str | None = None
    plan_endpoint: str
    run_endpoint: str
    direct_run_supported: bool = False
    diagnostics: list[str] = Field(default_factory=list)


class FirmwareVersionSummaryRead(BaseModel):
    label: str
    version: str | None = None
    status: str | None = None


class FirmwareFileCandidateRead(BaseModel):
    file_name: str
    file_path: str | None = None
    detected_vendor: str | None = None
    detected_product: str | None = None
    detected_version: str | None = None
    confidence: str = "medium"


class FirmwareFileSelectionsWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_files: dict[str, str] = Field(default_factory=dict)

    @field_validator("selected_files", mode="before")
    @classmethod
    def normalize_empty_mapping(cls, value: Any) -> Any:
        return {} if value is None else value

    @field_validator("selected_files", mode="after")
    @classmethod
    def validate_selection_mapping(cls, value: dict[str, str]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for raw_component_id, raw_file_name in value.items():
            component_id = str(raw_component_id).strip()
            file_name = str(raw_file_name).strip()
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", component_id):
                raise ValueError("firmware component IDs must be short safe identifiers")
            if any(separator in file_name for separator in ("/", "\\")):
                raise ValueError("firmware file selections store filenames only")
            if len(file_name) > 255:
                raise ValueError("firmware filenames must be 255 characters or fewer")
            _reject_secret_values(component_id)
            _reject_secret_values(file_name)
            normalized[component_id] = file_name
        return normalized


class FirmwareFileSelectionsRead(BaseModel):
    provider_id: str
    status: str
    message: str
    source_type: str
    freshness: str
    checked_at: datetime | None = None
    updated_at: datetime | None = None
    store_path: str
    selected_files: dict[str, str] = Field(default_factory=dict)
    apply_enabled: bool = False
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_safe_action: str


class FirmwareUpgradePathRead(BaseModel):
    component_id: str
    component_label: str
    device_label: str
    equipment_label: str | None = None
    equipment_type: str
    current_version: str | None = None
    target_version: str | None = None
    baseline_source: str | None = None
    package_available: bool = False
    package_name: str | None = None
    package_version: str | None = None
    selected_file_name: str | None = None
    selected_file_path: str | None = None
    selection_source: str = "none"
    candidate_files: list[FirmwareFileCandidateRead] = Field(default_factory=list)
    path_status: str
    required_intermediate_versions: list[str] = Field(default_factory=list)
    prechecks_required: list[str] = Field(default_factory=list)
    reboot_required: bool = False
    estimated_impact: str
    apply_enabled: bool = False
    disabled_reason: str
    next_action: str
    evidence_artifacts: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    scan_action_id: str | None = None
    last_checked: str | None = None
    source_type: str
    freshness: str


class FirmwareSummaryRead(BaseModel):
    device_id: str
    label: str
    component_type: str
    current_versions: list[FirmwareVersionSummaryRead] = Field(default_factory=list)
    approved_versions: list[FirmwareVersionSummaryRead] = Field(default_factory=list)
    compliance_status: str
    severity: str
    last_scanned: str | None = None
    source_type: str
    freshness: str
    blocker: str | None = None
    next_action: str
    scan_action_id: str | None = None
    upgrade_center_link: str
    evidence_artifacts: list[str] = Field(default_factory=list)
    upgrade_paths: list[FirmwareUpgradePathRead] = Field(default_factory=list)
    path_status: str = "unknown"
    target_version: str | None = None
    package_available: bool = False
    package_name: str | None = None
    required_intermediate_versions: list[str] = Field(default_factory=list)
    prechecks_required: list[str] = Field(default_factory=list)
    reboot_required: bool = False
    estimated_impact: str = "Unknown until firmware/software path is classified."
    apply_enabled: bool = False
    disabled_reason: str = "No upgrade path rows are available."


class ControlSectionRead(BaseModel):
    id: str
    title: str
    stage: str
    description: str
    status: str
    firmware_summary: FirmwareSummaryRead | None = None
    current_state: list[ControlStateItemRead] = Field(default_factory=list)
    desired_state: list[ControlStateItemRead] = Field(default_factory=list)
    plan_diff: list[ControlPlanDiffItemRead] = Field(default_factory=list)
    access_config: ControlAccessConfigRead | None = None
    actions: list[ControlActionRead] = Field(default_factory=list)
    primary_actions: list[ControlActionRead] = Field(default_factory=list)
    destructive_actions: list[ControlActionRead] = Field(default_factory=list)
    upgrade_actions: list[ControlActionRead] = Field(default_factory=list)
    last_result: dict[str, Any] = Field(default_factory=dict)
    report_links: list[ControlReportLinkRead] = Field(default_factory=list)
    advanced_diagnostics: dict[str, Any] = Field(default_factory=dict)


class ControlLabProfileRead(BaseModel):
    active_profile_name: str
    source: str
    version: int
    topology: str | None = None
    features: dict[str, Any] = Field(default_factory=dict)
    not_in_scope_stages: list[str] = Field(default_factory=list)
    mismatch_warnings: list[dict[str, Any]] = Field(default_factory=list)
    fix_guidance: list[dict[str, Any]] = Field(default_factory=list)
    global_settings: LabGlobalSettings
    address_plan: LabAddressPlan
    known_lab_profile: dict[str, Any]
    network: dict[str, Any]
    configured_flags: dict[str, bool]
    edit_profile_path: str
    env_update_command: str
    stale_or_invalid_values: list[str] = Field(default_factory=list)


class ControlActionCatalogRead(BaseModel):
    generated_at: datetime
    provider_mode: str
    summary: dict[str, Any]
    lab_profile: ControlLabProfileRead
    sections: list[ControlSectionRead]
    actions: list[ControlActionRead]


class ControlActionPlanStepRead(BaseModel):
    label: str
    status: str
    detail: str


class ControlActionPlanRead(BaseModel):
    action: ControlActionRead
    status: str
    message: str
    plan_steps: list[ControlActionPlanStepRead] = Field(default_factory=list)
    suggested_command: str | None = None
    api_endpoint: str | None = None
    method: str | None = None
    direct_run_enabled: bool = False
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class ControlActionRunRead(BaseModel):
    action: ControlActionRead
    status: str
    message: str
    executed: bool = False
    suggested_command: str | None = None
    api_endpoint: str | None = None
    method: str | None = None
    warnings: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class WorkflowActionInputRead(BaseModel):
    name: str
    label: str
    required: bool = False
    secret: bool = False
    description: str = ""


class WorkflowRunTraceRead(BaseModel):
    run_id: str
    action_id: str
    stage_id: str
    started_at: str | None = None
    finished_at: str | None = None
    status: str
    source_type: Literal["live_probe", "live_cached", "historical_artifact", "test_fixture", "not_checked"] | str
    freshness: str
    command: str | None = None
    report_artifacts: list[str] = Field(default_factory=list)
    summary: str
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_action: str


class WorkflowActionRunRead(BaseModel):
    run_id: str
    action_id: str
    action_label: str
    stage_id: str
    stage_label: str
    mode: Literal["read_only", "write", "destructive", "upgrade", "report_only"] | str
    started_at: str
    finished_at: str
    checked_at: str
    status: str
    source_type: Literal["live_probe", "live_cached", "historical_artifact", "test_fixture", "not_checked"] | str
    freshness: str
    not_mock: bool = True
    command: str | None = None
    executed: bool = False
    return_code: int | None = None
    stdout_summary: str = ""
    stderr_summary: str = ""
    report_artifacts: list[str] = Field(default_factory=list)
    trace_artifact: str | None = None
    summary: str
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_action: str


class WorkflowActionRunCreate(BaseModel):
    confirmation_phrase: str | None = None
    confirmed_gates: list[str] = Field(default_factory=list)


class WorkflowActionDiagnosisEvidenceRead(BaseModel):
    label: str
    detail: str


class WorkflowActionDiagnosisRecentRunRead(BaseModel):
    run_id: str
    status: str
    finished_at: str | None = None
    summary: str
    blocker_count: int = 0
    warning_count: int = 0
    trace_artifact: str | None = None


class WorkflowActionDiagnosisRead(BaseModel):
    action_id: str
    action_label: str
    run_id: str | None = None
    status: str
    ai_enabled: bool = False
    advisory_source: Literal["local_rules", "external_ai"] | str = "local_rules"
    confidence: Literal["high", "medium", "low"] | str
    probable_cause: str
    explanation: str
    suggested_next_action: str
    suggested_action_id: str | None = None
    suggested_action_safe: bool = False
    evidence: list[WorkflowActionDiagnosisEvidenceRead] = Field(default_factory=list)
    recent_runs: list[WorkflowActionDiagnosisRecentRunRead] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)


class OperatorIssuePacketCreate(BaseModel):
    route: str = Field(default="/", max_length=160)
    page_title: str = Field(default="", max_length=120)
    operator_note: str = Field(default="", max_length=1600)
    ui_context: dict[str, str] = Field(default_factory=dict)


class OperatorIssuePacketRunRead(BaseModel):
    run_id: str
    action_id: str
    stage_id: str
    started_at: str | None = None
    finished_at: str | None = None
    status: str
    source_type: str
    freshness: str
    command: str | None = None
    report_artifacts: list[str] = Field(default_factory=list)
    summary: str
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    next_action: str


class OperatorIssuePacketDiagnosisRead(BaseModel):
    action_id: str | None = None
    status: str | None = None
    confidence: str | None = None
    probable_cause: str
    suggested_next_action: str
    suggested_action_id: str | None = None
    suggested_action_safe: bool = False


class OperatorIssuePacketRead(BaseModel):
    packet_id: str
    created_at: str
    route: str
    page_title: str
    operator_note: str
    ui_context: dict[str, str] = Field(default_factory=dict)
    ai_enabled: bool = False
    advisory_source: Literal["local_rules", "external_ai"] | str = "local_rules"
    summary: str
    recent_problem_runs: list[OperatorIssuePacketRunRead] = Field(default_factory=list)
    diagnoses: list[OperatorIssuePacketDiagnosisRead] = Field(default_factory=list)
    suggested_next_steps: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    artifact: str
    markdown_artifact: str
    copy_prompt: str


class UiIntentRegionRead(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    kind: Literal["panel", "drawer", "section", "row"] | str = "section"


class UiIntentRegionLayoutRead(BaseModel):
    visible: bool = True
    collapsed: bool = False
    order: int = 0


class UiIntentRequest(BaseModel):
    page: str = Field(min_length=1, max_length=80)
    request: str = Field(min_length=1, max_length=400)
    regions: list[UiIntentRegionRead] = Field(default_factory=list, max_length=40)
    current_layout: dict[str, UiIntentRegionLayoutRead] = Field(default_factory=dict)


class UiIntentOpRead(BaseModel):
    region_id: str = Field(min_length=1, max_length=80)
    op: Literal["hide", "show", "collapse", "expand", "moveUp", "moveDown"]


class UiIntentResponse(BaseModel):
    ops: list[UiIntentOpRead] = Field(default_factory=list)
    summary: str
    source: Literal["local_rules", "external_ai"] | str = "local_rules"


class AiChangeRequestCreate(BaseModel):
    page: str = Field(min_length=1, max_length=80)
    request: str = Field(min_length=1, max_length=1600)
    target: str | None = Field(default=None, max_length=120)
    route: str = Field(default="/", max_length=160)
    regions: list[UiIntentRegionRead] = Field(default_factory=list, max_length=60)
    current_layout: dict[str, UiIntentRegionLayoutRead] = Field(default_factory=dict)
    screenshot_path: str | None = Field(default=None, max_length=240)


class AiChangeRequestRead(BaseModel):
    request_id: str
    status: Literal["queued"] | str = "queued"
    artifact: str
    message: str
    next_action: str


class WorkflowActionRead(BaseModel):
    action_id: str
    label: str
    stage: str
    stage_label: str
    provider: str
    category: Literal[
        "discover",
        "inventory",
        "plan",
        "apply",
        "verify",
        "report",
        "reset",
        "upgrade",
        "waive",
        "reclaim",
    ]
    mode: Literal["read_only", "write", "destructive", "upgrade", "report_only"]
    description: str
    source_type: Literal["make_target", "backend_script", "api_endpoint", "manual_guidance"]
    command: str | None = None
    api_endpoint: str | None = None
    api_method: str | None = None
    required_mode: str
    required_gates: list[str] = Field(default_factory=list)
    required_confirmations: list[str] = Field(default_factory=list)
    required_credentials: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)
    inputs: list[WorkflowActionInputRead] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    reports: list[str] = Field(default_factory=list)
    last_run_report: str | None = None
    last_run_status: str
    current_availability: str
    blockers: list[str] = Field(default_factory=list)
    next_action: str
    evidence_artifacts: list[str] = Field(default_factory=list)
    stale_after_seconds: int
    last_run_trace: WorkflowRunTraceRead
    ui_run_supported: bool = False
    ui_run_blockers: list[str] = Field(default_factory=list)
    guarded_run_supported: bool = False
    guarded_run_blockers: list[str] = Field(default_factory=list)
    run_endpoint: str
    runs_endpoint: str


class WorkflowStageRead(BaseModel):
    stage_id: str
    label: str
    order: int
    current_state: str
    desired_state: str
    primary_action: str | None = None
    secondary_actions: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    reports: list[str] = Field(default_factory=list)
    action_count: int = 0
    blocked_count: int = 0
    report_count: int = 0
    actions: list[WorkflowActionRead] = Field(default_factory=list)


class CatalogRead(BaseModel):
    environments: list[str]
    sites: list[str]
    clusters_by_site: dict[str, list[str]]
    templates: list[str]
    networks: list[dict[str, Any]]
    datastores: list[str]
    storage_tiers: list[str]
