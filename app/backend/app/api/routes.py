from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, Request as FastAPIRequest, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_actor
from app.core.config import settings
from app.core.database import get_session
from app.models import AuditEvent
from app.providers.cisco_ansible import CiscoAnsibleAdapter
from app.providers.cisco_console import CiscoConsoleAdapter
from app.providers.esxi_readonly import EsxiReadonlyAdapter
from app.providers.ilo_redfish import IloRedfishAdapter
from app.providers.mock import MockSourceOfTruthAdapter
from app.providers.netapp import NetAppOntapAdapter
from app.providers.registry import (
    ProviderRegistryError,
    provider_registry,
    provider_registry_error_status,
)
from app.schemas import (
    ApprovalCreate,
    AiChangeRequestCreate,
    AiChangeRequestRead,
    ArtifactRead,
    AuditEventRead,
    CatalogRead,
    CiscoBootstrapRequirementsRead,
    CiscoBootstrapRequirementsUpdate,
    CiscoConsoleBootstrapApplyCreate,
    CiscoConsoleBootstrapPlanRead,
    CiscoSetupReadinessRead,
    CiscoSetupWizardPlanRead,
    ControlAccessConfigRead,
    ControlAccessConfigWrite,
    ControlActionCatalogRead,
    ControlActionPlanRead,
    ControlActionRunRead,
    FirmwareFileSelectionsRead,
    FirmwareFileSelectionsWrite,
    FirmwareSummaryRead,
    HpeRaidApplyCreate,
    HpeRaidFactoryResetCreate,
    HpeRaidIntentRead,
    HpeRaidIntentWrite,
    HpeRaidPlanPreviewRead,
    HpeStorageDiscoveryRead,
    IloBaselinePreviewRead,
    IloBaselineReadinessRead,
    IloDestructiveRebuildPreviewRead,
    IloReadinessSummaryRead,
    IloReportPreviewRead,
    IloSetupApplyCreate,
    IloSetupCompareReportRead,
    IloSetupIntentRead,
    IloSetupIntentWrite,
    IloSetupPlanPreviewRead,
    IloUpgradeReadinessRead,
    LabSafetySettingsRead,
    LabSafetySettingsWrite,
    LabValidationSummaryRead,
    LabProfileListRead,
    LabProfileRead,
    LabProfileRuntimeApplyRead,
    LabProfileWrite,
    TopologyDesignDraftRead,
    TopologyDesignDraftWrite,
    MediaInventoryRead,
    NetAppConsoleReadinessRead,
    NetAppObservationRead,
    NetAppObservationUpdate,
    NetAppPlanPreviewRead,
    NetAppReadinessComparisonRead,
    NetAppUpgradeReadinessRead,
    OperatorIssuePacketCreate,
    OperatorIssuePacketRead,
    ProviderArtifactRead,
    ProviderModeSettingsRead,
    ProviderModeSettingsWrite,
    ProviderProbeResultRead,
    ProviderStatusRead,
    ReportCenterRead,
    ReportCenterSummaryRead,
    RequestReadinessRead,
    RequestRead,
    UiIntentRequest,
    UiIntentResponse,
    VMDeploymentCreate,
    VMDeploymentUpdate,
    WorkflowActionDiagnosisRead,
    WorkflowActionRead,
    WorkflowActionRunCreate,
    WorkflowActionRunRead,
    WorkflowRunRead,
    WorkflowStageRead,
)
from app.services.artifacts import (
    list_request_artifacts,
    list_workflow_run_artifacts,
)
from app.services.audit import record_audit_event
from app.services.cisco_bootstrap_requirements import (
    CiscoBootstrapRequirementsValidationError,
    get_cisco_bootstrap_requirements,
    save_cisco_bootstrap_requirements,
)
from app.services.cisco_console_bootstrap import (
    apply_cisco_console_bootstrap,
    build_cisco_console_bootstrap_plan,
)
from app.services.lifecycle import (
    ExecutionPreflightError,
    InvalidTransitionError,
    RequestNotFoundError,
    RequestUpdateValidationError,
    ValidationFailureError,
    WorkflowRunNotFoundError,
    approve_request,
    cancel_request,
    create_vm_deployment_request,
    execute_request,
    get_request,
    get_workflow_run,
    list_workflow_runs,
    list_requests,
    plan_request,
    reject_request,
    submit_request,
    update_vm_deployment_request,
)
from app.services.cisco_setup_readiness import get_cisco_setup_readiness
from app.services.cisco_current_intent import get_cisco_current_intent_diff
from app.services.cisco_setup_wizard_plan import get_cisco_setup_wizard_plan
from app.services.build_verification import get_lab_build_verification
from app.services.control_actions import (
    ControlActionNotFoundError,
    get_control_action_catalog,
    plan_control_action,
    run_control_action,
)
from app.services.control_access import (
    ControlAccessConfigNotFoundError,
    ControlAccessConfigValidationError,
    update_control_access_config,
)
from app.services.ilo_baseline import (
    get_ilo_baseline_preview,
    get_ilo_baseline_readiness,
)
from app.services.ilo_readiness import (
    get_ilo_destructive_rebuild_preview,
    get_ilo_readiness_summary,
    get_ilo_report_preview,
    get_ilo_setup_compare,
    get_ilo_setup_intent,
    get_ilo_setup_plan_preview,
    save_ilo_setup_intent,
)
from app.services.ilo_setup_apply import (
    apply_ilo_setup,
    build_ilo_setup_apply_plan,
)
from app.services.provider_mode_settings import (
    ProviderModeSettingsError,
    read_provider_mode_settings,
    update_provider_mode_settings,
)
from app.services.lab_safety_settings import (
    LabSafetySettingsError,
    read_lab_safety_settings,
    update_lab_safety_settings,
)
from app.services.lab_profiles import (
    LabProfileError,
    LabProfileNotFoundError,
    activate_lab_profile,
    apply_active_profile_to_runtime_env,
    create_lab_profile,
    list_lab_profiles,
    update_lab_profile,
)
from app.services.topology_design_drafts import (
    TopologyDesignDraftError,
    get_topology_design_draft,
    save_topology_design_draft,
)
from app.services.lab_validation import get_lab_validation_summary
from app.services.hpe_raid import (
    apply_hpe_raid_factory_reset,
    apply_hpe_raid_plan,
    build_hpe_raid_apply_plan,
    build_hpe_raid_factory_reset_preview,
    build_hpe_raid_reset_plan,
    get_hpe_raid_intent,
    get_hpe_raid_plan_preview,
    get_hpe_storage_discovery,
    reset_server_for_raid,
    save_hpe_raid_intent,
    validate_hpe_raid_after_reset,
    write_hpe_raid_pending_report,
)
from app.services.esxi_install_readiness import get_esxi_install_readiness
from app.services.esxi_management_recovery import (
    recover_esxi_management,
    validate_esxi_post_recovery,
)
from app.services.esxi_netapp_datastore import (
    apply_esxi_netapp_datastore,
    build_esxi_netapp_datastore_preview,
    validate_esxi_netapp_datastore,
)
from app.services.esxi_iscsi_datastore import (
    build_esxi_iscsi_datastore_preview,
    validate_esxi_iscsi_datastore,
)
from app.services.esxi_vm_deploy import (
    apply_esxi_vm_deploy,
    build_esxi_vm_deploy_preview,
    validate_esxi_vm_deploy,
)
from app.services.firmware_compliance import (
    get_firmware_compliance,
    get_firmware_inventory,
    get_firmware_summaries,
    write_waiver_report,
)
from app.services.firmware_file_selections import (
    read_firmware_file_selections,
    save_firmware_file_selections,
)
from app.services.full_rebuild_run import get_full_rebuild_summary
from app.services.golden_state import get_provider_lab_golden_state
from app.services.media_inventory import get_media_inventory
from app.services.netapp_artifacts import (
    list_netapp_artifact_placeholders,
    list_provider_artifact_placeholders,
)
from app.services.netapp_address_plan import (
    apply_netapp_address_remediation,
    build_netapp_address_remediation_plan,
    build_netapp_address_remediation_preview,
    diagnose_netapp_ha_node_warning,
    validate_netapp_address_remediation,
)
from app.services.netapp_console_readiness import get_netapp_console_readiness
from app.services.netapp_factory_reset import (
    apply_netapp_factory_reset,
    build_netapp_factory_reset_preview,
    validate_netapp_factory_reset,
)
from app.services.netapp_observations import (
    get_netapp_observations,
    save_netapp_observations,
)
from app.services.netapp_readiness_comparison import get_netapp_readiness_comparison
from app.services.netapp_real_lab import (
    get_netapp_live_state,
    get_latest_netapp_console_discovery,
    get_latest_netapp_console_state,
    get_netapp_nfs_vcenter_readiness,
    run_netapp_live_state,
    run_netapp_setup_validation,
    run_netapp_console_discovery,
    run_netapp_console_login_state,
    run_netapp_console_read_state,
)
from app.services.netapp_setup_intent import (
    apply_netapp_setup,
    build_netapp_setup_preview,
    run_netapp_post_setup_validation,
)
from app.services.netapp_nfs_setup import (
    apply_netapp_nfs_setup,
    build_netapp_nfs_setup_preview,
    validate_netapp_nfs_setup,
)
from app.services.netapp_iscsi_setup import (
    apply_netapp_iscsi_setup,
    build_netapp_iscsi_setup_preview,
    validate_netapp_iscsi_setup,
)
from app.services.netapp_upgrade_center import (
    apply_netapp_upgrade,
    build_netapp_upgrade_inventory,
    build_netapp_upgrade_plan,
    validate_netapp_upgrade,
)
from app.services.netapp_upgrade_readiness import get_netapp_upgrade_readiness
from app.services.operator_issue_packets import create_operator_issue_packet
from app.services.readiness import get_request_readiness
from app.services.report_center import get_report_center, get_report_summary
from app.services.ai_change_requests import create_ai_change_request
from app.services.ui_intent import resolve_ui_intent
from app.services.upgrade_decision import get_ilo_upgrade_readiness
from app.services.vcenter_netapp_readiness import (
    get_vcenter_attach_esxi_apply,
    get_vcenter_attach_esxi_preview,
    get_vcenter_install_apply,
    get_vcenter_install_plan,
    get_vcenter_install_preview,
    get_vcenter_install_readiness,
    get_vcenter_netapp_datastore_plan,
    get_vcenter_netapp_readiness,
    validate_vcenter_post_attach,
)
from app.services.workflow_registry import (
    WorkflowRegistryNotFoundError,
    get_workflow_action,
    get_workflow_stage,
    list_workflow_actions,
    list_workflow_stages,
)
from app.services.workflow_action_diagnosis import diagnose_workflow_action
from app.services.workflow_action_runner import (
    list_workflow_action_runs,
    run_workflow_action,
)

router = APIRouter(prefix="/api/v1")


@router.post(
    "/requests/vm-deploy",
    response_model=RequestRead,
    status_code=status.HTTP_201_CREATED,
)
def create_vm_deploy(
    payload: VMDeploymentCreate,
    fastapi_request: FastAPIRequest,
    session: Session = Depends(get_session),
) -> RequestRead:
    actor = get_current_actor(fastapi_request)
    return create_vm_deployment_request(session, payload, actor=actor)


@router.get("/requests", response_model=list[RequestRead])
def read_requests(session: Session = Depends(get_session)) -> list[RequestRead]:
    return list_requests(session)


@router.get("/requests/{request_id}", response_model=RequestRead)
def read_request(request_id: str, session: Session = Depends(get_session)) -> RequestRead:
    try:
        return get_request(session, request_id)
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc


@router.get("/requests/{request_id}/readiness", response_model=RequestReadinessRead)
def read_request_readiness(
    request_id: str,
    session: Session = Depends(get_session),
) -> RequestReadinessRead:
    try:
        return get_request_readiness(session, request_id)
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc


@router.get("/requests/{request_id}/artifacts", response_model=list[ArtifactRead])
def read_request_artifacts(
    request_id: str,
    session: Session = Depends(get_session),
) -> list[ArtifactRead]:
    try:
        return list_request_artifacts(session, request_id)
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc


@router.patch("/requests/{request_id}", response_model=RequestRead)
def update_request(
    request_id: str,
    payload: VMDeploymentUpdate,
    fastapi_request: FastAPIRequest,
    session: Session = Depends(get_session),
) -> RequestRead:
    actor = get_current_actor(fastapi_request)
    try:
        return update_vm_deployment_request(session, request_id, payload, actor=actor)
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc
    except RequestUpdateValidationError as exc:
        raise HTTPException(status_code=422, detail={"validation_errors": exc.errors}) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/requests/{request_id}/submit", response_model=RequestRead)
def submit(
    request_id: str,
    fastapi_request: FastAPIRequest,
    session: Session = Depends(get_session),
) -> RequestRead:
    actor = get_current_actor(fastapi_request)
    try:
        return submit_request(session, request_id, actor=actor)
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc
    except ProviderRegistryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValidationFailureError as exc:
        raise HTTPException(status_code=422, detail={"validation_errors": exc.errors}) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/requests/{request_id}/approve", response_model=RequestRead)
def approve(
    request_id: str,
    payload: ApprovalCreate,
    session: Session = Depends(get_session),
) -> RequestRead:
    try:
        return approve_request(session, request_id, payload)
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc
    except ProviderRegistryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/requests/{request_id}/reject", response_model=RequestRead)
def reject(
    request_id: str,
    payload: ApprovalCreate,
    session: Session = Depends(get_session),
) -> RequestRead:
    try:
        return reject_request(session, request_id, payload)
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/requests/{request_id}/plan", response_model=WorkflowRunRead)
def plan(
    request_id: str,
    fastapi_request: FastAPIRequest,
    session: Session = Depends(get_session),
) -> WorkflowRunRead:
    actor = get_current_actor(fastapi_request)
    try:
        return plan_request(session, request_id, actor=actor)
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/requests/{request_id}/cancel", response_model=RequestRead)
def cancel(
    request_id: str,
    fastapi_request: FastAPIRequest,
    session: Session = Depends(get_session),
) -> RequestRead:
    actor = get_current_actor(fastapi_request)
    try:
        return cancel_request(session, request_id, actor=actor)
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/requests/{request_id}/execute", response_model=WorkflowRunRead)
def execute(
    request_id: str,
    fastapi_request: FastAPIRequest,
    session: Session = Depends(get_session),
) -> WorkflowRunRead:
    actor = get_current_actor(fastapi_request)
    try:
        return execute_request(session, request_id, actor=actor)
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc
    except ProviderRegistryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ExecutionPreflightError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WorkflowRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workflow run not found") from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/workflow-runs/{workflow_run_id}", response_model=WorkflowRunRead)
def read_workflow_run(
    workflow_run_id: str,
    session: Session = Depends(get_session),
) -> WorkflowRunRead:
    try:
        return get_workflow_run(session, workflow_run_id)
    except WorkflowRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workflow run not found") from exc


@router.get("/workflow-runs/{workflow_run_id}/artifacts", response_model=list[ArtifactRead])
def read_workflow_run_artifacts(
    workflow_run_id: str,
    session: Session = Depends(get_session),
) -> list[ArtifactRead]:
    try:
        return list_workflow_run_artifacts(session, workflow_run_id)
    except WorkflowRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workflow run not found") from exc
    except RequestNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Request not found") from exc


@router.get("/audit-events", response_model=list[AuditEventRead])
def read_audit_events(session: Session = Depends(get_session)) -> list[AuditEventRead]:
    return list(
        session.execute(
            select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(200)
        ).scalars()
    )


@router.get("/workflow-runs", response_model=list[WorkflowRunRead])
def read_workflow_runs(session: Session = Depends(get_session)) -> list[WorkflowRunRead]:
    return list_workflow_runs(session)


@router.get("/workflows/stages", response_model=list[WorkflowStageRead])
def read_workflow_stages() -> list[WorkflowStageRead]:
    return list_workflow_stages()


@router.get("/workflows/actions", response_model=list[WorkflowActionRead])
def read_workflow_actions() -> list[WorkflowActionRead]:
    return list_workflow_actions()


@router.get("/workflows/actions/{action_id}", response_model=WorkflowActionRead)
def read_workflow_action(action_id: str) -> WorkflowActionRead:
    try:
        return get_workflow_action(action_id)
    except WorkflowRegistryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workflow action not found") from exc


@router.post("/workflows/actions/{action_id}/run", response_model=WorkflowActionRunRead)
def run_workflow_action_route(
    action_id: str,
    payload: WorkflowActionRunCreate | None = None,
    session: Session = Depends(get_session),
) -> WorkflowActionRunRead:
    try:
        return run_workflow_action(action_id, session, payload.model_dump() if payload else None)
    except WorkflowRegistryNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"blocker": "Workflow action not found", "action_id": action_id},
        ) from exc


@router.get("/workflows/actions/{action_id}/runs", response_model=list[WorkflowActionRunRead])
def read_workflow_action_runs(action_id: str, limit: int = Query(20, ge=1, le=100)) -> list[WorkflowActionRunRead]:
    try:
        return list_workflow_action_runs(action_id, limit=limit)
    except WorkflowRegistryNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"blocker": "Workflow action not found", "action_id": action_id},
        ) from exc


@router.get("/workflows/actions/{action_id}/diagnosis", response_model=WorkflowActionDiagnosisRead)
def read_workflow_action_diagnosis(
    action_id: str,
    limit: int = Query(5, ge=1, le=10),
) -> WorkflowActionDiagnosisRead:
    try:
        return diagnose_workflow_action(action_id, limit=limit)
    except WorkflowRegistryNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail={"blocker": "Workflow action not found", "action_id": action_id},
        ) from exc


@router.post("/operator-issue-packets", response_model=OperatorIssuePacketRead)
def create_operator_issue_packet_route(payload: OperatorIssuePacketCreate) -> OperatorIssuePacketRead:
    return create_operator_issue_packet(payload.model_dump())


@router.post("/ui-intent", response_model=UiIntentResponse)
def resolve_ui_intent_route(payload: UiIntentRequest) -> UiIntentResponse:
    return resolve_ui_intent(payload)


@router.post("/ai-change-requests", response_model=AiChangeRequestRead)
def create_ai_change_request_route(payload: AiChangeRequestCreate) -> AiChangeRequestRead:
    return create_ai_change_request(payload)


@router.get("/workflows/stages/{stage_id}", response_model=WorkflowStageRead)
def read_workflow_stage(stage_id: str) -> WorkflowStageRead:
    try:
        return get_workflow_stage(stage_id)
    except WorkflowRegistryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workflow stage not found") from exc


@router.get("/providers/status", response_model=list[ProviderStatusRead])
def read_provider_status() -> list[ProviderStatusRead]:
    try:
        return provider_registry().statuses()
    except ProviderRegistryError as exc:
        return [provider_registry_error_status(settings.provider_mode, str(exc))]


@router.get("/settings/provider-mode", response_model=ProviderModeSettingsRead)
def read_provider_mode_settings_route() -> ProviderModeSettingsRead:
    return read_provider_mode_settings()


@router.put("/settings/provider-mode", response_model=ProviderModeSettingsRead)
def update_provider_mode_settings_route(
    payload: ProviderModeSettingsWrite,
) -> ProviderModeSettingsRead:
    try:
        return update_provider_mode_settings(payload.model_dump())
    except ProviderModeSettingsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/settings/lab-safety", response_model=LabSafetySettingsRead)
def read_lab_safety_settings_route() -> LabSafetySettingsRead:
    return read_lab_safety_settings()


@router.put("/settings/lab-safety", response_model=LabSafetySettingsRead)
def update_lab_safety_settings_route(
    payload: LabSafetySettingsWrite,
    fastapi_request: FastAPIRequest,
    session: Session = Depends(get_session),
) -> LabSafetySettingsRead:
    update_payload = payload.model_dump(exclude_none=True)
    try:
        result = update_lab_safety_settings(update_payload)
    except LabSafetySettingsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    changed = sorted(
        key
        for key in update_payload
        if key not in {"confirmation_phrase", "device_reconfiguration_confirmation_phrase"}
    )
    record_audit_event(
        session,
        actor=get_current_actor(fastapi_request),
        event_type="settings.lab_safety.updated",
        message="Lab safety runtime settings were updated.",
        data={"changed_fields": changed},
    )
    session.commit()
    return result


@router.get("/control/actions", response_model=ControlActionCatalogRead)
def read_control_actions() -> ControlActionCatalogRead:
    return get_control_action_catalog()


@router.get("/firmware/summary", response_model=list[FirmwareSummaryRead])
def read_firmware_summary() -> list[FirmwareSummaryRead]:
    return get_firmware_summaries()


@router.get("/firmware/file-selections", response_model=FirmwareFileSelectionsRead)
def read_firmware_file_selections_route() -> FirmwareFileSelectionsRead:
    return read_firmware_file_selections()


@router.put("/firmware/file-selections", response_model=FirmwareFileSelectionsRead)
def update_firmware_file_selections_route(
    payload: FirmwareFileSelectionsWrite,
) -> FirmwareFileSelectionsRead:
    return save_firmware_file_selections(payload.model_dump())


@router.put("/control/access/{section_id}", response_model=ControlAccessConfigRead)
def update_control_access_route(
    section_id: str,
    payload: ControlAccessConfigWrite,
) -> ControlAccessConfigRead:
    try:
        return update_control_access_config(section_id, payload.model_dump())
    except ControlAccessConfigNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Control access section not found") from exc
    except ControlAccessConfigValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/control/actions/{action_id}/plan", response_model=ControlActionPlanRead)
def plan_control_action_route(action_id: str) -> ControlActionPlanRead:
    try:
        return plan_control_action(action_id)
    except ControlActionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Control action not found") from exc


@router.post("/control/actions/{action_id}/run", response_model=ControlActionRunRead)
def run_control_action_route(action_id: str) -> ControlActionRunRead:
    try:
        return run_control_action(action_id)
    except ControlActionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Control action not found") from exc


@router.get("/lab/firmware-inventory", response_model=ProviderProbeResultRead)
def read_firmware_inventory() -> dict:
    return get_firmware_inventory(refresh_live=False)


@router.get("/lab/firmware-compliance", response_model=ProviderProbeResultRead)
def read_firmware_compliance(scope: str = Query("full", pattern="^(hpe|cisco|netapp|full)$")) -> dict:
    return get_firmware_compliance(refresh_live=False, scope=scope)


@router.get("/lab/firmware-waiver-check", response_model=ProviderProbeResultRead)
def read_firmware_waiver_check() -> dict:
    return write_waiver_report()


@router.get("/lab/full-rebuild-summary", response_model=ProviderProbeResultRead)
def read_full_rebuild_summary() -> ProviderProbeResultRead:
    return get_full_rebuild_summary()


@router.get("/lab/build-verification", response_model=ProviderProbeResultRead)
def read_lab_build_verification() -> ProviderProbeResultRead:
    return get_lab_build_verification()


@router.get("/lab/golden-state", response_model=ProviderProbeResultRead)
def read_provider_lab_golden_state() -> ProviderProbeResultRead:
    return get_provider_lab_golden_state(write_report=False)


@router.get("/lab/validation", response_model=LabValidationSummaryRead)
def read_lab_validation() -> LabValidationSummaryRead:
    return get_lab_validation_summary(write_report=False)


@router.get("/lab/validation/handoff", response_model=LabValidationSummaryRead)
def read_lab_validation_handoff() -> LabValidationSummaryRead:
    return get_lab_validation_summary(write_report=True)


@router.get("/lab/vcenter-netapp/readiness", response_model=ProviderProbeResultRead)
def read_vcenter_netapp_readiness() -> ProviderProbeResultRead:
    return get_vcenter_netapp_readiness(check_ports=False, write_report=False)


@router.get("/lab/vcenter-netapp/datastore-plan", response_model=ProviderProbeResultRead)
def read_vcenter_netapp_datastore_plan() -> ProviderProbeResultRead:
    return get_vcenter_netapp_datastore_plan(write_report=False)


@router.get("/lab/vcenter/install-readiness", response_model=ProviderProbeResultRead)
def read_vcenter_install_readiness() -> ProviderProbeResultRead:
    return get_vcenter_install_readiness(check_ports=False, write_report=False)


@router.get("/lab/vcenter/install-plan", response_model=ProviderProbeResultRead)
def read_vcenter_install_plan() -> ProviderProbeResultRead:
    return get_vcenter_install_plan(write_report=False)


@router.get("/lab/vcenter/install-preview", response_model=ProviderProbeResultRead)
def read_vcenter_install_preview() -> ProviderProbeResultRead:
    return get_vcenter_install_preview(write_report=False)


@router.post("/lab/vcenter/install-apply", response_model=ProviderProbeResultRead)
def run_vcenter_install_apply() -> ProviderProbeResultRead:
    return get_vcenter_install_apply(write_report=True)


@router.get("/lab/vcenter/attach-esxi-preview", response_model=ProviderProbeResultRead)
def read_vcenter_attach_esxi_preview() -> ProviderProbeResultRead:
    return get_vcenter_attach_esxi_preview(write_report=False)


@router.post("/lab/vcenter/attach-esxi-apply", response_model=ProviderProbeResultRead)
def run_vcenter_attach_esxi_apply() -> ProviderProbeResultRead:
    return get_vcenter_attach_esxi_apply(write_report=True)


@router.get("/lab/vcenter/post-attach-validation", response_model=ProviderProbeResultRead)
def read_vcenter_post_attach_validation() -> ProviderProbeResultRead:
    return validate_vcenter_post_attach(write_report=False)


@router.get("/reports/issues", response_model=ReportCenterRead)
def read_report_issues(session: Session = Depends(get_session)) -> ReportCenterRead:
    return get_report_center(session)


@router.get("/reports/summary", response_model=ReportCenterSummaryRead)
def read_report_summary(session: Session = Depends(get_session)) -> ReportCenterSummaryRead:
    return get_report_summary(session)


@router.get("/lab/profiles", response_model=LabProfileListRead)
def read_lab_profiles() -> LabProfileListRead:
    return list_lab_profiles()


@router.post(
    "/lab/profiles",
    response_model=LabProfileRead,
    status_code=status.HTTP_201_CREATED,
)
def create_lab_profile_route(payload: LabProfileWrite) -> LabProfileRead:
    try:
        return create_lab_profile(payload.model_dump(exclude_unset=True))
    except LabProfileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/lab/profiles/{profile_id}", response_model=LabProfileRead)
def update_lab_profile_route(profile_id: str, payload: LabProfileWrite) -> LabProfileRead:
    try:
        return update_lab_profile(profile_id, payload.model_dump(exclude_unset=True))
    except LabProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Lab profile not found") from exc
    except LabProfileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/lab/profiles/{profile_id}/activate", response_model=LabProfileListRead)
def activate_lab_profile_route(profile_id: str) -> LabProfileListRead:
    try:
        return activate_lab_profile(profile_id)
    except LabProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Lab profile not found") from exc


@router.post("/lab/profiles/active/apply-runtime-env", response_model=LabProfileRuntimeApplyRead)
def apply_active_lab_profile_runtime_env_route() -> LabProfileRuntimeApplyRead:
    try:
        return apply_active_profile_to_runtime_env()
    except LabProfileError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/lab/topology-design-draft", response_model=TopologyDesignDraftRead)
def read_topology_design_draft(
    profile_id: str = Query("runtime", min_length=1, max_length=120),
    scenario: str = Query(..., min_length=1, max_length=80),
    subnet: str | None = Query(None, max_length=80),
) -> TopologyDesignDraftRead:
    try:
        return get_topology_design_draft(profile_id=profile_id, scenario=scenario, subnet=subnet)
    except TopologyDesignDraftError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/lab/topology-design-draft", response_model=TopologyDesignDraftRead)
def update_topology_design_draft(payload: TopologyDesignDraftWrite) -> TopologyDesignDraftRead:
    try:
        return save_topology_design_draft(payload.model_dump())
    except TopologyDesignDraftError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/providers/cisco/setup-readiness",
    response_model=CiscoSetupReadinessRead,
)
def read_cisco_setup_readiness() -> CiscoSetupReadinessRead:
    return get_cisco_setup_readiness()


@router.post(
    "/providers/cisco/current-intent-diff",
    response_model=ProviderProbeResultRead,
)
def run_cisco_current_intent_diff() -> ProviderProbeResultRead:
    return get_cisco_current_intent_diff()


@router.get(
    "/providers/cisco/setup-wizard-plan",
    response_model=CiscoSetupWizardPlanRead,
)
def read_cisco_setup_wizard_plan() -> CiscoSetupWizardPlanRead:
    return get_cisco_setup_wizard_plan()


@router.get(
    "/providers/cisco/bootstrap-requirements",
    response_model=CiscoBootstrapRequirementsRead,
)
def read_cisco_bootstrap_requirements() -> CiscoBootstrapRequirementsRead:
    return get_cisco_bootstrap_requirements()


@router.put(
    "/providers/cisco/bootstrap-requirements",
    response_model=CiscoBootstrapRequirementsRead,
)
def update_cisco_bootstrap_requirements(
    payload: CiscoBootstrapRequirementsUpdate,
) -> CiscoBootstrapRequirementsRead:
    try:
        return save_cisco_bootstrap_requirements(payload.model_dump())
    except CiscoBootstrapRequirementsValidationError as exc:
        raise HTTPException(status_code=422, detail={"validation_errors": exc.errors}) from exc


@router.get(
    "/providers/cisco/console-bootstrap/plan",
    response_model=CiscoConsoleBootstrapPlanRead,
)
def read_cisco_console_bootstrap_plan() -> CiscoConsoleBootstrapPlanRead:
    return build_cisco_console_bootstrap_plan()


@router.post(
    "/providers/cisco/console-bootstrap/apply",
    response_model=ProviderProbeResultRead,
)
def apply_cisco_console_bootstrap_route(
    payload: CiscoConsoleBootstrapApplyCreate,
) -> ProviderProbeResultRead:
    return apply_cisco_console_bootstrap(payload.model_dump())


@router.post(
    "/providers/cisco-console/prompt-readiness",
    response_model=ProviderProbeResultRead,
)
def cisco_console_prompt_readiness() -> ProviderProbeResultRead:
    return _run_provider_probe("cisco-console", CiscoConsoleAdapter().prompt_readiness)


@router.post("/providers/{provider_id}/probe", response_model=ProviderProbeResultRead)
def probe_provider(provider_id: str) -> ProviderProbeResultRead:
    if provider_id == "ilo-redfish":
        return _run_provider_probe(provider_id, IloRedfishAdapter().probe)
    if provider_id == "cisco-console":
        return _run_provider_probe(provider_id, CiscoConsoleAdapter().probe)
    if provider_id == "cisco-ansible":
        return _run_provider_probe(provider_id, CiscoAnsibleAdapter().probe)
    if provider_id == "esxi-readonly":
        return _run_provider_probe(provider_id, EsxiReadonlyAdapter().probe)
    raise HTTPException(status_code=404, detail="Provider probe not found")


@router.get(
    "/providers/ilo-redfish/upgrade-readiness",
    response_model=IloUpgradeReadinessRead,
)
def read_ilo_upgrade_readiness() -> IloUpgradeReadinessRead:
    return get_ilo_upgrade_readiness()


@router.get(
    "/providers/hpe-ilo/baseline-preview",
    response_model=IloBaselinePreviewRead,
)
def read_hpe_ilo_baseline_preview() -> IloBaselinePreviewRead:
    return get_ilo_baseline_preview()


@router.get(
    "/providers/hpe-ilo/readiness",
    response_model=IloBaselineReadinessRead,
)
def read_hpe_ilo_readiness() -> IloBaselineReadinessRead:
    return get_ilo_baseline_readiness()


@router.get(
    "/providers/ilo-redfish/readiness-summary",
    response_model=IloReadinessSummaryRead,
)
def read_ilo_readiness_summary() -> IloReadinessSummaryRead:
    return get_ilo_readiness_summary()


@router.get(
    "/providers/ilo-redfish/destructive-rebuild-preview",
    response_model=IloDestructiveRebuildPreviewRead,
)
def read_ilo_destructive_rebuild_preview() -> IloDestructiveRebuildPreviewRead:
    return get_ilo_destructive_rebuild_preview()


@router.get(
    "/providers/ilo-redfish/setup-plan-preview",
    response_model=IloSetupPlanPreviewRead,
)
def read_ilo_setup_plan_preview(
    session: Session = Depends(get_session),
) -> IloSetupPlanPreviewRead:
    return get_ilo_setup_plan_preview(session)


@router.get(
    "/providers/ilo-redfish/setup-intent",
    response_model=IloSetupIntentRead,
)
def read_ilo_setup_intent(
    session: Session = Depends(get_session),
) -> IloSetupIntentRead:
    return get_ilo_setup_intent(session)


@router.put(
    "/providers/ilo-redfish/setup-intent",
    response_model=IloSetupIntentRead,
)
def update_ilo_setup_intent(
    payload: IloSetupIntentWrite,
    session: Session = Depends(get_session),
) -> IloSetupIntentRead:
    return save_ilo_setup_intent(session, payload)


@router.get(
    "/providers/ilo-redfish/setup-compare",
    response_model=IloSetupCompareReportRead,
)
def read_ilo_setup_compare(
    session: Session = Depends(get_session),
) -> IloSetupCompareReportRead:
    return get_ilo_setup_compare(session)


@router.get(
    "/providers/ilo-redfish/report-preview",
    response_model=IloReportPreviewRead,
)
def read_ilo_report_preview(
    session: Session = Depends(get_session),
) -> IloReportPreviewRead:
    return get_ilo_report_preview(session)


@router.get(
    "/providers/ilo-redfish/setup-apply-plan",
    response_model=ProviderProbeResultRead,
)
def read_ilo_setup_apply_plan(
    session: Session = Depends(get_session),
) -> ProviderProbeResultRead:
    return build_ilo_setup_apply_plan(session)


@router.post(
    "/providers/ilo-redfish/setup-apply",
    response_model=ProviderProbeResultRead,
)
def apply_ilo_setup_route(
    payload: IloSetupApplyCreate,
    session: Session = Depends(get_session),
) -> ProviderProbeResultRead:
    return apply_ilo_setup(session, payload)


@router.get(
    "/providers/ilo-redfish/hpe-storage-discovery",
    response_model=HpeStorageDiscoveryRead,
)
def read_hpe_storage_discovery() -> HpeStorageDiscoveryRead:
    return get_hpe_storage_discovery()


@router.get(
    "/providers/ilo-redfish/hpe-raid-intent",
    response_model=HpeRaidIntentRead,
)
def read_hpe_raid_intent(
    session: Session = Depends(get_session),
) -> HpeRaidIntentRead:
    return get_hpe_raid_intent(session)


@router.put(
    "/providers/ilo-redfish/hpe-raid-intent",
    response_model=HpeRaidIntentRead,
)
def update_hpe_raid_intent(
    payload: HpeRaidIntentWrite,
    session: Session = Depends(get_session),
) -> HpeRaidIntentRead:
    return save_hpe_raid_intent(session, payload)


@router.get(
    "/providers/ilo-redfish/hpe-raid-plan-preview",
    response_model=HpeRaidPlanPreviewRead,
)
def read_hpe_raid_plan_preview(
    session: Session = Depends(get_session),
) -> HpeRaidPlanPreviewRead:
    return get_hpe_raid_plan_preview(session)


@router.get(
    "/providers/ilo-redfish/hpe-raid-apply-plan",
    response_model=ProviderProbeResultRead,
)
def read_hpe_raid_apply_plan(
    session: Session = Depends(get_session),
) -> ProviderProbeResultRead:
    return build_hpe_raid_apply_plan(session)


@router.post(
    "/providers/ilo-redfish/hpe-raid-apply",
    response_model=ProviderProbeResultRead,
)
def apply_hpe_raid_route(
    payload: HpeRaidApplyCreate,
    session: Session = Depends(get_session),
) -> ProviderProbeResultRead:
    return apply_hpe_raid_plan(session, payload)


@router.get(
    "/providers/ilo-redfish/hpe-raid-factory-reset-preview",
    response_model=ProviderProbeResultRead,
)
def read_hpe_raid_factory_reset_preview(
    session: Session = Depends(get_session),
) -> ProviderProbeResultRead:
    return build_hpe_raid_factory_reset_preview(session)


@router.post(
    "/providers/ilo-redfish/hpe-raid-factory-reset-apply",
    response_model=ProviderProbeResultRead,
)
def apply_hpe_raid_factory_reset_route(
    payload: HpeRaidFactoryResetCreate,
    session: Session = Depends(get_session),
) -> ProviderProbeResultRead:
    return apply_hpe_raid_factory_reset(session, payload)


@router.get(
    "/providers/ilo-redfish/hpe-raid-pending",
    response_model=ProviderProbeResultRead,
)
def read_hpe_raid_pending(
    session: Session = Depends(get_session),
) -> ProviderProbeResultRead:
    return write_hpe_raid_pending_report(session)


@router.get(
    "/providers/ilo-redfish/hpe-raid-reset-plan",
    response_model=ProviderProbeResultRead,
)
def read_hpe_raid_reset_plan() -> ProviderProbeResultRead:
    return build_hpe_raid_reset_plan()


@router.post(
    "/providers/ilo-redfish/hpe-raid-reset",
    response_model=ProviderProbeResultRead,
)
def reset_hpe_raid_server_route() -> ProviderProbeResultRead:
    return reset_server_for_raid()


@router.post(
    "/providers/ilo-redfish/hpe-raid-validate-after-reset",
    response_model=ProviderProbeResultRead,
)
def validate_hpe_raid_after_reset_route(
    session: Session = Depends(get_session),
) -> ProviderProbeResultRead:
    return validate_hpe_raid_after_reset(session)


@router.get(
    "/providers/ilo-redfish/esxi-install-readiness",
    response_model=ProviderProbeResultRead,
)
def read_esxi_install_readiness(
    session: Session = Depends(get_session),
) -> ProviderProbeResultRead:
    return get_esxi_install_readiness(session)


@router.get(
    "/providers/esxi-readonly/vm-deploy-preview",
    response_model=ProviderProbeResultRead,
)
def read_esxi_vm_deploy_preview() -> ProviderProbeResultRead:
    return build_esxi_vm_deploy_preview(write_report=False)


@router.post(
    "/providers/esxi-readonly/vm-deploy-apply",
    response_model=ProviderProbeResultRead,
)
def run_esxi_vm_deploy_apply_route() -> ProviderProbeResultRead:
    return apply_esxi_vm_deploy()


@router.post(
    "/providers/esxi-readonly/vm-deploy-validate",
    response_model=ProviderProbeResultRead,
)
def run_esxi_vm_deploy_validate_route() -> ProviderProbeResultRead:
    return validate_esxi_vm_deploy()


@router.post(
    "/providers/esxi-readonly/recover-management",
    response_model=ProviderProbeResultRead,
)
def run_esxi_recover_management_route() -> ProviderProbeResultRead:
    return recover_esxi_management()


@router.post(
    "/providers/esxi-readonly/post-recovery-validation",
    response_model=ProviderProbeResultRead,
)
def run_esxi_post_recovery_validation_route() -> ProviderProbeResultRead:
    return validate_esxi_post_recovery()


@router.get(
    "/providers/esxi-readonly/netapp-datastore-preview",
    response_model=ProviderProbeResultRead,
)
def read_esxi_netapp_datastore_preview() -> ProviderProbeResultRead:
    return build_esxi_netapp_datastore_preview(write_report=False)


@router.post(
    "/providers/esxi-readonly/netapp-datastore-apply",
    response_model=ProviderProbeResultRead,
)
def run_esxi_netapp_datastore_apply_route() -> ProviderProbeResultRead:
    return apply_esxi_netapp_datastore()


@router.post(
    "/providers/esxi-readonly/netapp-datastore-validate",
    response_model=ProviderProbeResultRead,
)
def run_esxi_netapp_datastore_validate_route() -> ProviderProbeResultRead:
    return validate_esxi_netapp_datastore()


@router.post(
    "/providers/esxi-readonly/iscsi-datastore-preview",
    response_model=ProviderProbeResultRead,
)
def run_esxi_iscsi_datastore_preview_route() -> ProviderProbeResultRead:
    return build_esxi_iscsi_datastore_preview()


@router.post(
    "/providers/esxi-readonly/iscsi-datastore-validate",
    response_model=ProviderProbeResultRead,
)
def run_esxi_iscsi_datastore_validate_route() -> ProviderProbeResultRead:
    return validate_esxi_iscsi_datastore()


@router.get(
    "/providers/netapp-ontap/plan-preview",
    response_model=NetAppPlanPreviewRead,
)
def read_netapp_plan_preview() -> NetAppPlanPreviewRead:
    return NetAppOntapAdapter().plan_preview()


@router.get(
    "/providers/netapp-ontap/console-readiness",
    response_model=NetAppConsoleReadinessRead,
)
def read_netapp_console_readiness() -> NetAppConsoleReadinessRead:
    return get_netapp_console_readiness()


@router.get(
    "/providers/netapp-ontap/console-discovery",
    response_model=ProviderProbeResultRead,
)
def read_netapp_console_discovery() -> ProviderProbeResultRead:
    return get_latest_netapp_console_discovery()


@router.post(
    "/providers/netapp-ontap/console-discovery",
    response_model=ProviderProbeResultRead,
)
def run_netapp_console_discovery_route() -> ProviderProbeResultRead:
    return run_netapp_console_discovery()


@router.get(
    "/providers/netapp-ontap/console-read-state",
    response_model=ProviderProbeResultRead,
)
def read_netapp_console_state() -> ProviderProbeResultRead:
    return get_latest_netapp_console_state()


@router.post(
    "/providers/netapp-ontap/console-read-state",
    response_model=ProviderProbeResultRead,
)
def run_netapp_console_state_route() -> ProviderProbeResultRead:
    return run_netapp_console_read_state()


@router.post(
    "/providers/netapp-ontap/console-login-state",
    response_model=ProviderProbeResultRead,
)
def run_netapp_console_login_state_route() -> ProviderProbeResultRead:
    return run_netapp_console_login_state()


@router.get(
    "/providers/netapp-ontap/live-state",
    response_model=ProviderProbeResultRead,
)
def read_netapp_live_state() -> ProviderProbeResultRead:
    return get_netapp_live_state()


@router.post(
    "/providers/netapp-ontap/live-state",
    response_model=ProviderProbeResultRead,
)
def run_netapp_live_state_route() -> ProviderProbeResultRead:
    return run_netapp_live_state()


@router.post(
    "/providers/netapp-ontap/validate-setup",
    response_model=ProviderProbeResultRead,
)
def run_netapp_setup_validation_route() -> ProviderProbeResultRead:
    return run_netapp_setup_validation()


@router.post(
    "/providers/netapp-ontap/post-setup-validation",
    response_model=ProviderProbeResultRead,
)
def run_netapp_post_setup_validation_route() -> ProviderProbeResultRead:
    return run_netapp_post_setup_validation()


@router.get(
    "/providers/netapp-ontap/address-plan",
    response_model=ProviderProbeResultRead,
)
def read_netapp_address_plan_route() -> ProviderProbeResultRead:
    return build_netapp_address_remediation_plan(write_report=False)


@router.post(
    "/providers/netapp-ontap/address-plan",
    response_model=ProviderProbeResultRead,
)
def run_netapp_address_plan_route() -> ProviderProbeResultRead:
    return build_netapp_address_remediation_plan()


@router.get(
    "/providers/netapp-ontap/address-preview",
    response_model=ProviderProbeResultRead,
)
def read_netapp_address_preview_route() -> ProviderProbeResultRead:
    return build_netapp_address_remediation_preview(write_report=False)


@router.post(
    "/providers/netapp-ontap/address-preview",
    response_model=ProviderProbeResultRead,
)
def run_netapp_address_preview_route() -> ProviderProbeResultRead:
    return build_netapp_address_remediation_preview()


@router.post(
    "/providers/netapp-ontap/address-apply",
    response_model=ProviderProbeResultRead,
)
def run_netapp_address_apply_route() -> ProviderProbeResultRead:
    return apply_netapp_address_remediation()


@router.post(
    "/providers/netapp-ontap/address-validate",
    response_model=ProviderProbeResultRead,
)
def run_netapp_address_validate_route() -> ProviderProbeResultRead:
    return validate_netapp_address_remediation()


@router.post(
    "/providers/netapp-ontap/ha-node-diagnose",
    response_model=ProviderProbeResultRead,
)
def run_netapp_ha_node_diagnose_route() -> ProviderProbeResultRead:
    return diagnose_netapp_ha_node_warning()


@router.get(
    "/providers/netapp-ontap/factory-reset-preview",
    response_model=ProviderProbeResultRead,
)
def read_netapp_factory_reset_preview_route() -> ProviderProbeResultRead:
    return build_netapp_factory_reset_preview(write_report=False)


@router.post(
    "/providers/netapp-ontap/factory-reset-preview",
    response_model=ProviderProbeResultRead,
)
def run_netapp_factory_reset_preview_route() -> ProviderProbeResultRead:
    return build_netapp_factory_reset_preview()


@router.post(
    "/providers/netapp-ontap/factory-reset-apply",
    response_model=ProviderProbeResultRead,
)
def run_netapp_factory_reset_apply_route() -> ProviderProbeResultRead:
    return apply_netapp_factory_reset()


@router.post(
    "/providers/netapp-ontap/factory-reset-validate",
    response_model=ProviderProbeResultRead,
)
def run_netapp_factory_reset_validate_route() -> ProviderProbeResultRead:
    return validate_netapp_factory_reset()


@router.get(
    "/providers/netapp-ontap/nfs-vcenter-readiness",
    response_model=ProviderProbeResultRead,
)
def read_netapp_nfs_vcenter_readiness() -> ProviderProbeResultRead:
    return get_netapp_nfs_vcenter_readiness()


@router.get(
    "/providers/netapp-ontap/nfs-setup-preview",
    response_model=ProviderProbeResultRead,
)
def read_netapp_nfs_setup_preview() -> ProviderProbeResultRead:
    return build_netapp_nfs_setup_preview(write_report=False)


@router.post(
    "/providers/netapp-ontap/nfs-setup-apply",
    response_model=ProviderProbeResultRead,
)
def run_netapp_nfs_setup_apply_route() -> ProviderProbeResultRead:
    return apply_netapp_nfs_setup()


@router.post(
    "/providers/netapp-ontap/nfs-setup-validate",
    response_model=ProviderProbeResultRead,
)
def run_netapp_nfs_setup_validate_route() -> ProviderProbeResultRead:
    return validate_netapp_nfs_setup()


@router.get(
    "/providers/netapp-ontap/iscsi-setup-preview",
    response_model=ProviderProbeResultRead,
)
def read_netapp_iscsi_setup_preview() -> ProviderProbeResultRead:
    return build_netapp_iscsi_setup_preview(write_report=False)


@router.post(
    "/providers/netapp-ontap/iscsi-setup-apply",
    response_model=ProviderProbeResultRead,
)
def run_netapp_iscsi_setup_apply_route() -> ProviderProbeResultRead:
    return apply_netapp_iscsi_setup()


@router.post(
    "/providers/netapp-ontap/iscsi-setup-validate",
    response_model=ProviderProbeResultRead,
)
def run_netapp_iscsi_setup_validate_route() -> ProviderProbeResultRead:
    return validate_netapp_iscsi_setup()


@router.get(
    "/providers/netapp-ontap/setup-preview",
    response_model=ProviderProbeResultRead,
)
def read_netapp_setup_preview() -> ProviderProbeResultRead:
    return build_netapp_setup_preview(run_address_scan=False, write_report=False)


@router.post(
    "/providers/netapp-ontap/setup-apply",
    response_model=ProviderProbeResultRead,
)
def run_netapp_setup_apply_route() -> ProviderProbeResultRead:
    return apply_netapp_setup()


@router.get(
    "/providers/netapp-ontap/ontap-upgrade/inventory",
    response_model=ProviderProbeResultRead,
)
def read_netapp_ontap_upgrade_inventory() -> ProviderProbeResultRead:
    return build_netapp_upgrade_inventory(write_report=False)


@router.get(
    "/providers/netapp-ontap/ontap-upgrade/plan",
    response_model=ProviderProbeResultRead,
)
def read_netapp_ontap_upgrade_plan() -> ProviderProbeResultRead:
    return build_netapp_upgrade_plan(write_report=False)


@router.post(
    "/providers/netapp-ontap/ontap-upgrade/validate",
    response_model=ProviderProbeResultRead,
)
def run_netapp_ontap_upgrade_validate_route() -> ProviderProbeResultRead:
    return validate_netapp_upgrade()


@router.post(
    "/providers/netapp-ontap/ontap-upgrade/apply",
    response_model=ProviderProbeResultRead,
)
def run_netapp_ontap_upgrade_apply_route() -> ProviderProbeResultRead:
    return apply_netapp_upgrade()


@router.get(
    "/providers/netapp-ontap/observations",
    response_model=NetAppObservationRead,
)
def read_netapp_observations() -> NetAppObservationRead:
    return get_netapp_observations()


@router.put(
    "/providers/netapp-ontap/observations",
    response_model=NetAppObservationRead,
)
def update_netapp_observations(
    payload: NetAppObservationUpdate,
    fastapi_request: FastAPIRequest,
) -> NetAppObservationRead:
    actor = get_current_actor(fastapi_request)
    try:
        return save_netapp_observations(payload.model_dump(), updated_by=actor)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/providers/netapp-ontap/readiness-comparison",
    response_model=NetAppReadinessComparisonRead,
)
def read_netapp_readiness_comparison() -> NetAppReadinessComparisonRead:
    return get_netapp_readiness_comparison()


@router.get(
    "/providers/netapp-ontap/upgrade-readiness",
    response_model=NetAppUpgradeReadinessRead,
)
def read_netapp_upgrade_readiness() -> NetAppUpgradeReadinessRead:
    return get_netapp_upgrade_readiness()


@router.get(
    "/providers/artifacts",
    response_model=list[ProviderArtifactRead],
)
def read_provider_artifacts() -> list[ProviderArtifactRead]:
    return list_provider_artifact_placeholders()


@router.get(
    "/providers/netapp-ontap/artifacts",
    response_model=list[ProviderArtifactRead],
)
def read_netapp_artifacts() -> list[ProviderArtifactRead]:
    return list_netapp_artifact_placeholders()


def _run_provider_probe(provider_id: str, probe: Callable[[], dict]) -> dict:
    try:
        return probe()
    except Exception as exc:
        return {
            "provider_id": provider_id,
            "status": "blocked",
            "message": "Provider probe failed before completing safely.",
            "warnings": [],
            "blockers": [f"Provider probe failed: {exc.__class__.__name__}."],
        }


@router.get("/catalog", response_model=CatalogRead)
def read_catalog() -> CatalogRead:
    return MockSourceOfTruthAdapter().catalog()


@router.get("/media-inventory", response_model=MediaInventoryRead)
def read_media_inventory() -> MediaInventoryRead:
    return get_media_inventory()
