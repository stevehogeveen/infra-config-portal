from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.enums import RequestStatus, WorkflowRunStatus


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Environment(Base):
    __tablename__ = "environments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)


class Site(Base):
    __tablename__ = "sites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Cluster(Base):
    __tablename__ = "clusters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), index=True)
    site: Mapped[str] = mapped_column(String(80), index=True)


class Network(Base):
    __tablename__ = "networks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    vlan_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    environment: Mapped[str | None] = mapped_column(String(32), nullable=True)


class StorageTier(Base):
    __tablename__ = "storage_tiers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProviderCredentialRef(Base):
    __tablename__ = "provider_credential_refs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    external_ref: Mapped[str] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Workflow(Base):
    __tablename__ = "workflows"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[str] = mapped_column(String(40), default="1.0.0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    runs: Mapped[list["WorkflowRun"]] = relationship(back_populates="workflow")


class Request(Base):
    __tablename__ = "requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_type: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(
        String(40),
        default=RequestStatus.DRAFT.value,
        index=True,
    )
    requester: Mapped[str] = mapped_column(String(120), index=True)
    owner: Mapped[str] = mapped_column(String(120), index=True)
    environment: Mapped[str] = mapped_column(String(32), index=True)
    site: Mapped[str] = mapped_column(String(80), index=True)
    expiry_date: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )

    vm_deploy: Mapped["VMDeploymentRequest"] = relationship(
        back_populates="request",
        cascade="all, delete-orphan",
        uselist=False,
    )
    workflow_runs: Mapped[list["WorkflowRun"]] = relationship(back_populates="request")
    approvals: Mapped[list["Approval"]] = relationship(back_populates="request")
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="request")


class VMDeploymentRequest(Base):
    __tablename__ = "vm_deployment_requests"

    request_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("requests.id"),
        primary_key=True,
    )
    cluster: Mapped[str] = mapped_column(String(120), index=True)
    vm_name: Mapped[str] = mapped_column(String(80), index=True)
    template: Mapped[str] = mapped_column(String(120))
    cpu: Mapped[int] = mapped_column(Integer)
    memory_gb: Mapped[int] = mapped_column(Integer)
    disk_gb: Mapped[int] = mapped_column(Integer)
    network: Mapped[str] = mapped_column(String(120))
    datastore: Mapped[str | None] = mapped_column(String(120), nullable=True)
    storage_tier: Mapped[str | None] = mapped_column(String(80), nullable=True)

    request: Mapped[Request] = relationship(back_populates="vm_deploy")


class IloSetupIntent(Base):
    __tablename__ = "ilo_setup_intents"

    provider_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    intent_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


class DeviceInventory(Base):
    __tablename__ = "device_inventory"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    device_type: Mapped[str] = mapped_column(String(80), index=True)
    display_name: Mapped[str] = mapped_column(String(200), index=True)
    host: Mapped[str | None] = mapped_column(String(300), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    seed_key: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


class DeviceInventoryState(Base):
    __tablename__ = "device_inventory_state"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default="legacy-seed-v1")
    seeded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class HpeRaidIntent(Base):
    __tablename__ = "hpe_raid_intents"

    provider_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    intent_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


class ProviderRuntimeState(Base):
    __tablename__ = "provider_runtime_states"
    __table_args__ = (
        UniqueConstraint(
            "provider_id",
            "device_role",
            name="uq_provider_runtime_states_provider_device",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    provider_id: Mapped[str] = mapped_column(String(80), index=True)
    device_role: Mapped[str] = mapped_column(String(120), index=True)
    discovered_console_port: Mapped[str | None] = mapped_column(String(300), nullable=True)
    discovered_baud: Mapped[int | None] = mapped_column(Integer, nullable=True)
    configured_state: Mapped[str] = mapped_column(String(80), default="not_detected", index=True)
    configured: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_successful_probe_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_report_path: Mapped[str | None] = mapped_column(String(400), nullable=True)
    confidence: Mapped[str | None] = mapped_column(String(40), nullable=True)
    blockers: Mapped[list] = mapped_column(JSON, default=list)
    data_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(String(36), ForeignKey("requests.id"), index=True)
    workflow_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workflows.id"),
        nullable=True,
        index=True,
    )
    workflow_slug: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(
        String(40),
        default=WorkflowRunStatus.PLANNED.value,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(120), default="vsphere.mock")
    plan_json: Mapped[dict] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
    )

    request: Mapped[Request] = relationship(back_populates="workflow_runs")
    workflow: Mapped[Workflow | None] = relationship(back_populates="runs")
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="workflow_run")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(String(36), ForeignKey("requests.id"), index=True)
    approver: Mapped[str] = mapped_column(String(120), index=True)
    decision: Mapped[str] = mapped_column(String(40))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    request: Mapped[Request] = relationship(back_populates="approvals")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("requests.id"),
        nullable=True,
        index=True,
    )
    workflow_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workflow_runs.id"),
        nullable=True,
        index=True,
    )
    actor: Mapped[str] = mapped_column(String(120), index=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    from_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    data_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    request: Mapped[Request | None] = relationship(back_populates="audit_events")
    workflow_run: Mapped[WorkflowRun | None] = relationship(back_populates="audit_events")
