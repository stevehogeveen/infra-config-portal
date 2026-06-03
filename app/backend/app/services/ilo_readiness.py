from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import IloSetupIntent
from app.providers.ilo_redfish import IloRedfishAdapter, PROVIDER_ID
from app.providers.probe_cache import get_probe_result
from app.schemas import (
    IloConnectionReadinessRead,
    IloCurrentStateRead,
    IloDestructiveRebuildPreviewRead,
    IloDestructiveRebuildRequirementRead,
    IloDesiredSetupSectionRead,
    IloReadinessSummaryRead,
    IloReportArtifactPlaceholderRead,
    IloReportPreviewRead,
    IloSetupCompareReportRead,
    IloSetupCompareRowRead,
    IloSetupCompareSectionRead,
    IloSetupIntentRead,
    IloSetupIntentWrite,
    IloSetupPlanPreviewRead,
    IloSetupPlanSectionRead,
)
from app.services.media_inventory import get_media_inventory
from app.services.upgrade_decision import get_ilo_upgrade_readiness


DESIRED_SETUP_SECTIONS = [
    ("identity", "Identity And Access"),
    ("network", "Management Network"),
    ("security", "Security And TLS"),
    ("time", "Time And Directory"),
    ("snmp", "SNMP And Alerting"),
    ("virtual_media", "Virtual Media Boot"),
    ("firmware", "Firmware And Media Upgrade"),
]

DESTRUCTIVE_REBUILD_SCOPE = [
    "verify target identity",
    "wipe existing drives",
    "delete existing RAID/logical drive configuration",
    "create new RAID/logical drives",
    "prepare boot/install media",
    "install ESXi",
    "collect logs/reports/artifacts",
]

DESTRUCTIVE_SAFE_NEXT_ACTION = (
    "Implement or use a dedicated bare-metal rebuild workflow after storage and ESXi "
    "modules are ready."
)


def get_ilo_setup_intent(session: Session) -> IloSetupIntentRead:
    record = session.get(IloSetupIntent, PROVIDER_ID)
    if record is None:
        return _intent_read(IloSetupIntentWrite())
    try:
        payload = IloSetupIntentWrite.model_validate(record.intent_json)
    except ValueError:
        return _intent_read(IloSetupIntentWrite())
    return _intent_read(
        payload,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def save_ilo_setup_intent(
    session: Session,
    payload: IloSetupIntentWrite,
) -> IloSetupIntentRead:
    record = session.get(IloSetupIntent, PROVIDER_ID)
    if record is None:
        record = IloSetupIntent(provider_id=PROVIDER_ID, intent_json=payload.model_dump())
        session.add(record)
    else:
        record.intent_json = payload.model_dump()

    session.commit()
    session.refresh(record)
    return _intent_read(
        IloSetupIntentWrite.model_validate(record.intent_json),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def get_ilo_readiness_summary() -> IloReadinessSummaryRead:
    status = IloRedfishAdapter().health()
    probe_result, probe_time = get_probe_result(PROVIDER_ID)
    media_inventory = get_media_inventory()
    firmware_readiness = get_ilo_upgrade_readiness()
    config = status.configuration

    return IloReadinessSummaryRead(
        provider_id=PROVIDER_ID,
        connection=IloConnectionReadinessRead(
            provider_mode=status.mode,
            provider_status=status.status,
            host_configured=bool(config.get("host_configured")),
            username_configured=bool(config.get("username_configured")),
            password_configured=bool(config.get("password_configured")),
            tls_verify=bool(config.get("tls_verify")),
            timeout_seconds=float(config.get("timeout_seconds") or 0),
            missing_fields=_string_list(config.get("missing_fields")),
            redfish_probe_available=any(
                action.id == "probe-ilo-redfish" and action.enabled
                for action in status.safe_actions
            ),
            safety_flags={
                key: value
                for key, value in config.items()
                if key.startswith("lab_") or key.endswith("_ack") or key == "readonly_allowed"
            },
        ),
        current_state=IloCurrentStateRead(
            last_probe_status=_last_probe_status(probe_result),
            last_probe_time=probe_time,
            model=firmware_readiness.subject.model,
            serial=firmware_readiness.subject.serial,
            current_firmware=firmware_readiness.subject.current_version,
            ilo_generation=firmware_readiness.subject.generation,
            redfish_endpoint_detected=_redfish_endpoint_detected(probe_result),
            legacy_endpoint_status="unknown/not_checked",
            legacy_endpoint_message=(
                "No legacy iLO endpoint probe has been run; legacy endpoints are not "
                "contacted by this preview."
            ),
            media_inventory_mode=media_inventory.mode,
        ),
        desired_setup_sections=[
            IloDesiredSetupSectionRead(
                id=section_id,
                title=title,
                status="plan_only",
                apply_enabled=False,
                note="Desired setup can be previewed only; no iLO settings are applied.",
            )
            for section_id, title in DESIRED_SETUP_SECTIONS
        ],
        firmware_readiness=firmware_readiness,
        upgrade_decision_status=firmware_readiness.decision.status,
        blockers=_unique([*status.blockers, *firmware_readiness.blockers]),
        warnings=_unique([*status.warnings, *firmware_readiness.warnings]),
        removable_warnings=firmware_readiness.removable_warnings,
        disabled_dangerous_actions=[asdict(action) for action in status.disabled_actions],
        reports_artifacts=[
            IloReportArtifactPlaceholderRead(
                kind="readiness-report",
                title="iLO Readiness Report",
                status="placeholder",
                note="Will summarize connection, discovery, blockers, and plan-only decisions.",
            ),
            IloReportArtifactPlaceholderRead(
                kind="preview-plan",
                title="iLO Setup Preview",
                status="placeholder",
                note="Will list desired setup sections without applying settings.",
            ),
            IloReportArtifactPlaceholderRead(
                kind="upgrade-decision",
                title="Firmware Upgrade Decision",
                status="placeholder",
                note="Will capture firmware candidate matching and upgrade chain decisions.",
            ),
        ],
    )


def get_ilo_setup_plan_preview(session: Session | None = None) -> IloSetupPlanPreviewRead:
    summary = get_ilo_readiness_summary()
    decision = summary.firmware_readiness.decision
    intent = get_ilo_setup_intent(session) if session is not None else _intent_read(IloSetupIntentWrite())

    return IloSetupPlanPreviewRead(
        provider_id=PROVIDER_ID,
        mode=summary.connection.provider_mode,
        plan_only=True,
        apply_enabled=False,
        generated_from="readiness-summary cached discovery and placeholders",
        sections=[
            _section(
                "network",
                "Network",
                status=_network_status(intent, summary),
                current_observation=(
                    f"Redfish endpoint {summary.current_state.redfish_endpoint_detected}; "
                    f"legacy endpoint {summary.current_state.legacy_endpoint_status}."
                ),
                planned_preview=_network_preview(intent),
                notes=[
                    "Uses cached Redfish discovery status only.",
                    summary.current_state.legacy_endpoint_message,
                ],
                warnings=_network_warnings(intent),
            ),
            _section(
                "users",
                "Users",
                status="planned" if intent.users else "missing_intent",
                current_observation=(
                    "Local credential presence is known; iLO account inventory is not "
                    "queried by this preview."
                ),
                planned_preview=_users_preview(intent),
                notes=["Credentials remain local configuration presence flags only."],
            ),
            _section(
                "snmp",
                "SNMP",
                status=_snmp_status(intent),
                current_observation="No cached SNMP configuration discovery is available.",
                planned_preview=_snmp_preview(intent),
                warnings=_snmp_warnings(intent),
            ),
            _section(
                "time",
                "NTP / Time",
                status=_time_status(intent),
                current_observation="No cached NTP or clock configuration discovery is available.",
                planned_preview=_time_preview(intent),
                warnings=_time_warnings(intent),
            ),
            _section(
                "dns_domain",
                "DNS / Domain",
                status=_dns_status(intent),
                current_observation="No cached DNS, hostname, or domain discovery is available.",
                planned_preview=_dns_preview(intent),
                warnings=_dns_warnings(intent),
            ),
            _section(
                "firmware_readiness",
                "Firmware Readiness Handoff",
                status=_firmware_status(summary),
                current_observation=(
                    f"Current firmware {summary.current_state.current_firmware or 'unknown'}; "
                    f"iLO generation {summary.current_state.ilo_generation or 'unknown'}."
                ),
                planned_preview=(
                    f"Hand off to upgrade decision status {decision.status}. "
                    "No firmware upload, flash, reboot, reset, or virtual media action is run."
                ),
                blockers=summary.firmware_readiness.blockers,
                warnings=[
                    *summary.firmware_readiness.warnings,
                    *summary.firmware_readiness.removable_warnings,
                ],
            ),
            _section(
                "reports_artifacts",
                "Reports / Artifacts",
                status="planned",
                current_observation=(
                    f"{len(summary.reports_artifacts)} report placeholders are defined."
                ),
                planned_preview=(
                    "Preview report and artifact placeholder generation only. No media "
                    "files or real-lab artifacts are collected."
                ),
                notes=[artifact.title for artifact in summary.reports_artifacts],
            ),
            _section(
                "destructive_rebuild_handoff",
                "Full Destructive Rebuild Handoff",
                status="blocked_out_of_scope",
                current_observation=(
                    "iLO identity and readiness context can support a future rebuild "
                    "review, but drive inventory, RAID planning, ESXi media prep, and "
                    "guarded execution are not owned by this iLO page."
                ),
                planned_preview=(
                    "Preview destructive rebuild requirements only. No wipe, RAID, "
                    "virtual media, boot, BIOS, power, or ESXi install action will run "
                    "from this iLO page."
                ),
                blockers=[DESTRUCTIVE_SAFE_NEXT_ACTION],
                warnings=[
                    "Full rebuild remains blocked until a dedicated guarded rebuild workflow exists."
                ],
            ),
        ],
        firmware_readiness_handoff={
            "decision_status": decision.status,
            "current_firmware": summary.current_state.current_firmware,
            "ilo_generation": summary.current_state.ilo_generation,
            "recommended_target": decision.recommended_target,
            "next_safe_action": decision.next_safe_action,
            "apply_enabled": False,
        },
        reports_artifacts=summary.reports_artifacts,
        disabled_dangerous_actions=summary.disabled_dangerous_actions,
        blockers=summary.blockers,
        warnings=summary.warnings,
        removable_warnings=summary.removable_warnings,
    )


def get_ilo_destructive_rebuild_preview() -> IloDestructiveRebuildPreviewRead:
    summary = get_ilo_readiness_summary()
    identity = _destructive_target_identity(summary)
    requirements = _destructive_rebuild_requirements(summary, identity)
    blockers = _unique(
        [
            requirement.detail
            for requirement in requirements
            if requirement.status in {"missing", "blocked", "required"}
        ]
    )
    blockers = _unique(
        [
            *blockers,
            "A dedicated guarded bare-metal rebuild workflow is not implemented in this iLO provider.",
            "Storage drive discovery and RAID planning are required before any destructive storage action.",
            "ESXi install media and final dry-run review are required before installation can be planned.",
        ]
    )

    return IloDestructiveRebuildPreviewRead(
        provider_id=PROVIDER_ID,
        provider_mode=summary.connection.provider_mode,
        status="blocked_out_of_scope",
        destructive_enabled=False,
        apply_enabled=False,
        safe_next_action=DESTRUCTIVE_SAFE_NEXT_ACTION,
        target_identity=identity,
        discovered_state={
            "last_probe_status": summary.current_state.last_probe_status,
            "last_probe_time": summary.current_state.last_probe_time,
            "redfish_endpoint_detected": summary.current_state.redfish_endpoint_detected,
            "media_inventory_mode": summary.current_state.media_inventory_mode,
        },
        intended_scope=DESTRUCTIVE_REBUILD_SCOPE,
        required_capabilities=requirements,
        blockers=blockers,
        warnings=[
            "No wipe, RAID, virtual media, boot order, BIOS, power, or ESXi install action is exposed here.",
            "Use this iLO page only for readiness, identity context, blocked intent, and future workflow handoff.",
        ],
        future_workflow_handoff={
            "target_workflow": "dedicated bare-metal destructive rebuild workflow",
            "owning_modules": ["storage/RAID", "ESXi install", "Run Center", "artifact reporting"],
            "ilo_role": "identity/readiness context and read-only discovery handoff",
            "status": "not_available_from_ilo_page",
        },
        confirmation_requirements={
            "provider_mode": "local-destructive or intentionally supported equivalent",
            "required_acknowledgements": [
                "LAB_CLOSED_LOOP_ACK=YES",
                "LAB_READONLY_ACK=YES",
                "LAB_DESTRUCTIVE_ACK=YES",
            ],
            "operator_phrase": "DESTROY AND REBUILD",
            "dry_run_required": True,
            "final_review_required": True,
            "identity_verification_required": True,
        },
        artifact_requirements=[
            "dry-run plan",
            "final review report",
            "operator confirmation record",
            "drive inventory snapshot",
            "RAID plan and result summary",
            "ESXi install preparation and result summary",
            "redacted logs and audit events",
        ],
    )


def get_ilo_setup_compare(session: Session) -> IloSetupCompareReportRead:
    summary = get_ilo_readiness_summary()
    intent = get_ilo_setup_intent(session)
    sections = [
        _compare_section(
            "network",
            "Network",
            [
                _compare_unknown(
                    "network",
                    "hostname",
                    "Hostname",
                    intent.network.hostname,
                    sensitive=True,
                ),
                _compare_unknown(
                    "network",
                    "management_ip",
                    "Management IP",
                    intent.network.management_ip,
                    sensitive=True,
                ),
                _compare_unknown(
                    "network",
                    "subnet_mask_or_prefix",
                    "Subnet Mask / Prefix",
                    intent.network.subnet_mask_or_prefix,
                    sensitive=True,
                ),
                _compare_unknown(
                    "network",
                    "gateway",
                    "Gateway",
                    intent.network.gateway,
                    sensitive=True,
                ),
                _compare_unknown("network", "vlan", "VLAN", intent.network.vlan),
            ],
        ),
        _compare_section(
            "users",
            "Users",
            [
                _compare_unknown(
                    "users",
                    "desired_local_usernames",
                    "Desired Local Usernames",
                    "configured" if intent.users else None,
                    sensitive=True,
                ),
                _compare_unknown(
                    "users",
                    "role_privilege_intent",
                    "Role / Privilege Intent",
                    "configured" if intent.users else None,
                    sensitive=True,
                ),
            ],
        ),
        _compare_section(
            "snmp",
            "SNMP",
            [
                _compare_unknown(
                    "snmp",
                    "enabled",
                    "Enabled",
                    _snmp_enabled_compare_desired(intent),
                ),
                _compare_unknown(
                    "snmp",
                    "destinations",
                    "Destination Placeholders",
                    "configured" if intent.snmp.destinations else None,
                    sensitive=True,
                ),
                _compare_unknown(
                    "snmp",
                    "community_or_user_refs",
                    "Community/User Ref Labels",
                    "configured" if intent.snmp.community_or_user_ref_labels else None,
                    sensitive=True,
                ),
            ],
        ),
        _compare_section(
            "time",
            "NTP / Time",
            [
                _compare_unknown("time", "timezone", "Timezone", intent.time.timezone),
                _compare_unknown(
                    "time",
                    "ntp_servers",
                    "NTP Server Placeholders",
                    "configured" if intent.time.ntp_servers else None,
                    sensitive=True,
                ),
            ],
        ),
        _compare_section(
            "dns_domain",
            "DNS / Domain",
            [
                _compare_unknown(
                    "dns_domain",
                    "domain_name",
                    "Domain Name",
                    intent.dns_domain.domain_name,
                    sensitive=True,
                ),
                _compare_unknown(
                    "dns_domain",
                    "dns_servers",
                    "DNS Server Placeholders",
                    "configured" if intent.dns_domain.dns_servers else None,
                    sensitive=True,
                ),
            ],
        ),
        _compare_section(
            "firmware",
            "Firmware",
            [
                _compare_firmware_row(
                    "current_firmware",
                    "Current Firmware",
                    summary.current_state.current_firmware,
                ),
                _compare_firmware_row(
                    "ilo_generation",
                    "iLO Generation",
                    summary.current_state.ilo_generation,
                ),
            ],
        ),
    ]
    return IloSetupCompareReportRead(
        provider_id=PROVIDER_ID,
        mode=summary.connection.provider_mode,
        source="saved setup intent compared with cached readiness/discovery only",
        apply_enabled=False,
        sections=sections,
        disabled_dangerous_actions=summary.disabled_dangerous_actions,
        blockers=summary.blockers,
        warnings=summary.warnings,
        removable_warnings=summary.removable_warnings,
    )


def get_ilo_report_preview(session: Session) -> IloReportPreviewRead:
    summary = get_ilo_readiness_summary()
    intent = get_ilo_setup_intent(session)
    compare = get_ilo_setup_compare(session)
    plan = get_ilo_setup_plan_preview(session)
    destructive_preview = get_ilo_destructive_rebuild_preview()
    media_inventory = get_media_inventory()

    return IloReportPreviewRead(
        provider_id=PROVIDER_ID,
        provider_mode=summary.connection.provider_mode,
        generated_at=datetime.now(UTC),
        source=(
            "readiness summary, saved setup intent, cached discovery, setup compare, "
            "setup plan preview, firmware readiness, and media inventory metadata"
        ),
        apply_enabled=False,
        readiness_summary=_redacted_readiness_summary(summary),
        desired_setup_intent=_redacted_intent_summary(intent),
        setup_compare_report=compare,
        setup_plan_preview=_redacted_plan_summary(plan),
        destructive_rebuild_preview=_redacted_destructive_rebuild_preview(destructive_preview),
        firmware_readiness=_redacted_firmware_readiness(summary),
        media_inventory_summary={
            "mode": media_inventory.mode,
            "configured_directory_count": len(media_inventory.configured_directories),
            "item_count": len(media_inventory.items),
            "categories": _counts_by_category(media_inventory.items),
            "items": [
                {
                    "placeholder_name": item.placeholder_name,
                    "category": item.category,
                    "source": item.source,
                    "actual_name_redacted": item.actual_name_redacted,
                    "version_hint": item.version_hint,
                }
                for item in media_inventory.items
            ],
            "warnings": media_inventory.warnings,
        },
        disabled_dangerous_actions=summary.disabled_dangerous_actions,
        blockers=_unique([*summary.blockers, *compare.blockers, *destructive_preview.blockers]),
        warnings=_unique([*summary.warnings, *compare.warnings, *destructive_preview.warnings]),
        removable_warnings=_unique(
            [*summary.removable_warnings, *compare.removable_warnings]
        ),
    )


def _section(
    section_id: str,
    title: str,
    *,
    current_observation: str,
    planned_preview: str,
    status: str = "plan_only",
    notes: list[str] | None = None,
    blockers: list[str] | None = None,
    warnings: list[str] | None = None,
) -> IloSetupPlanSectionRead:
    return IloSetupPlanSectionRead(
        id=section_id,
        title=title,
        status=status,
        apply_enabled=False,
        source="readiness-summary",
        current_observation=current_observation,
        planned_preview=planned_preview,
        notes=notes or [],
        blockers=blockers or [],
        warnings=warnings or [],
    )


def _destructive_target_identity(summary: IloReadinessSummaryRead) -> dict[str, Any]:
    return {
        "identity_verified": False,
        "model": summary.current_state.model or None,
        "model_discovered": bool(summary.current_state.model),
        "serial_present": bool(summary.current_state.serial),
        "ilo_generation": summary.current_state.ilo_generation or None,
        "ilo_generation_discovered": bool(summary.current_state.ilo_generation),
        "firmware_known": bool(summary.current_state.current_firmware),
        "redfish_endpoint_detected": summary.current_state.redfish_endpoint_detected,
    }


def _destructive_rebuild_requirements(
    summary: IloReadinessSummaryRead,
    identity: dict[str, Any],
) -> list[IloDestructiveRebuildRequirementRead]:
    return [
        _destructive_requirement(
            "verified_ilo_identity",
            "Verified iLO identity",
            "blocked",
            "Target identity must be verified against discovered model, serial presence, and iLO data.",
        ),
        _destructive_requirement(
            "model_discovered",
            "Model discovered",
            "satisfied" if identity["model_discovered"] else "missing",
            "Run explicit read-only iLO discovery until the server model is known.",
        ),
        _destructive_requirement(
            "serial_present",
            "Serial present",
            "satisfied" if identity["serial_present"] else "missing",
            "Run explicit read-only iLO discovery until serial presence can be confirmed.",
        ),
        _destructive_requirement(
            "ilo_generation_discovered",
            "iLO generation discovered",
            "satisfied" if identity["ilo_generation_discovered"] else "missing",
            "Run explicit read-only iLO discovery until iLO generation is known.",
        ),
        _destructive_requirement(
            "firmware_known",
            "Firmware known",
            "satisfied" if identity["firmware_known"] else "missing",
            "Run explicit read-only iLO discovery until current firmware is known.",
        ),
        _destructive_requirement(
            "drive_inventory",
            "Drive inventory required",
            "required",
            "A storage module must discover physical drives before wipe or RAID planning.",
        ),
        _destructive_requirement(
            "raid_plan",
            "RAID plan required",
            "required",
            "A storage/RAID module must build and review the logical drive plan.",
        ),
        _destructive_requirement(
            "esxi_install_media",
            "ESXi install media required",
            "required",
            "An ESXi install module must validate boot/install media metadata before handoff.",
        ),
        _destructive_requirement(
            "final_dry_run_plan",
            "Final dry-run plan required",
            "required",
            "Run Center must generate a dry-run plan before any destructive approval.",
        ),
        _destructive_requirement(
            "destructive_confirmation",
            "Destructive confirmation required",
            "required",
            "A guarded workflow must require the exact phrase DESTROY AND REBUILD.",
        ),
        _destructive_requirement(
            "dedicated_workflow",
            "Dedicated rebuild workflow required",
            "blocked",
            "The iLO page does not own wipe, RAID creation, virtual media, boot, BIOS, power, or ESXi install execution.",
        ),
    ]


def _destructive_requirement(
    requirement_id: str,
    label: str,
    status: str,
    detail: str,
) -> IloDestructiveRebuildRequirementRead:
    return IloDestructiveRebuildRequirementRead(
        id=requirement_id,
        label=label,
        status=status,
        detail=detail,
    )


def _redacted_readiness_summary(summary: IloReadinessSummaryRead) -> dict[str, Any]:
    return {
        "connection": {
            "provider_mode": summary.connection.provider_mode,
            "provider_status": summary.connection.provider_status,
            "host_configured": summary.connection.host_configured,
            "username_configured": summary.connection.username_configured,
            "password_configured": summary.connection.password_configured,
            "redfish_probe_available": summary.connection.redfish_probe_available,
            "missing_fields": summary.connection.missing_fields,
        },
        "current_state": {
            "last_probe_status": summary.current_state.last_probe_status,
            "last_probe_time": summary.current_state.last_probe_time,
            "model": summary.current_state.model,
            "serial_present": bool(summary.current_state.serial),
            "current_firmware": summary.current_state.current_firmware,
            "ilo_generation": summary.current_state.ilo_generation,
            "redfish_endpoint_detected": summary.current_state.redfish_endpoint_detected,
            "legacy_endpoint_status": summary.current_state.legacy_endpoint_status,
            "media_inventory_mode": summary.current_state.media_inventory_mode,
        },
        "upgrade_decision_status": summary.upgrade_decision_status,
        "apply_enabled": False,
    }


def _redacted_intent_summary(intent: IloSetupIntentRead) -> dict[str, Any]:
    return {
        "network": {
            "hostname": _configured(intent.network.hostname),
            "management_ip": _configured(intent.network.management_ip),
            "subnet_mask_or_prefix": _configured(intent.network.subnet_mask_or_prefix),
            "gateway": _configured(intent.network.gateway),
            "vlan": _configured(intent.network.vlan),
        },
        "users": {
            "desired_local_username_labels": _count_label(intent.users),
            "role_privilege_intent": _count_label(intent.users),
        },
        "snmp": {
            "enabled": intent.snmp.enabled,
            "destinations": _count_label(intent.snmp.destinations),
            "community_or_user_ref_labels": _count_label(
                intent.snmp.community_or_user_ref_labels
            ),
        },
        "time": {
            "timezone": _configured(intent.time.timezone),
            "ntp_servers": _count_label(intent.time.ntp_servers),
        },
        "dns_domain": {
            "domain_name": _configured(intent.dns_domain.domain_name),
            "dns_servers": _count_label(intent.dns_domain.dns_servers),
        },
        "notes": _configured(intent.notes),
        "apply_enabled": False,
    }


def _redacted_firmware_readiness(summary: IloReadinessSummaryRead) -> dict[str, Any]:
    readiness = summary.firmware_readiness
    return {
        "provider_id": readiness.provider_id,
        "subject": {
            "provider_type": readiness.subject.provider_type,
            "product": readiness.subject.product,
            "generation": readiness.subject.generation,
            "model": readiness.subject.model,
            "serial_present": bool(readiness.subject.serial),
            "current_version": readiness.subject.current_version,
            "discovery_confidence": readiness.subject.discovery_confidence,
        },
        "candidate_count": len(readiness.candidates),
        "upgrade_chain_count": len(readiness.upgrade_chain),
        "decision": {
            "status": readiness.decision.status,
            "current_version": readiness.decision.current_version,
            "recommended_target": readiness.decision.recommended_target,
            "required_intermediate_versions": readiness.decision.required_intermediate_versions,
            "next_safe_action": readiness.decision.next_safe_action,
            "apply_enabled": False,
        },
        "blockers": readiness.blockers,
        "warnings": readiness.warnings,
        "removable_warnings": readiness.removable_warnings,
        "apply_enabled": False,
    }


def _redacted_plan_summary(plan: IloSetupPlanPreviewRead) -> dict[str, Any]:
    return {
        "mode": plan.mode,
        "plan_only": plan.plan_only,
        "apply_enabled": False,
        "generated_from": plan.generated_from,
        "sections": [
            {
                "id": section.id,
                "title": section.title,
                "status": section.status,
                "apply_enabled": False,
                "source": section.source,
                "blockers": section.blockers,
                "warnings": section.warnings,
                "note_count": len(section.notes),
            }
            for section in plan.sections
        ],
        "firmware_readiness_handoff": plan.firmware_readiness_handoff,
    }


def _redacted_destructive_rebuild_preview(
    preview: IloDestructiveRebuildPreviewRead,
) -> dict[str, Any]:
    return {
        "status": preview.status,
        "destructive_enabled": False,
        "apply_enabled": False,
        "safe_next_action": preview.safe_next_action,
        "target_identity": {
            "identity_verified": False,
            "model_discovered": bool(preview.target_identity.get("model_discovered")),
            "serial_present": bool(preview.target_identity.get("serial_present")),
            "ilo_generation_discovered": bool(
                preview.target_identity.get("ilo_generation_discovered")
            ),
            "firmware_known": bool(preview.target_identity.get("firmware_known")),
            "redfish_endpoint_detected": preview.target_identity.get(
                "redfish_endpoint_detected"
            ),
        },
        "intended_scope": preview.intended_scope,
        "required_capabilities": [
            requirement.model_dump() for requirement in preview.required_capabilities
        ],
        "blockers": preview.blockers,
        "warnings": preview.warnings,
        "future_workflow_handoff": preview.future_workflow_handoff,
        "confirmation_requirements": preview.confirmation_requirements,
        "artifact_requirements": preview.artifact_requirements,
    }


def _counts_by_category(items: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item.category] = counts.get(item.category, 0) + 1
    return counts


def _configured(value: str | None) -> str:
    return "configured" if value and value.strip() else "missing"


def _count_label(values: list[Any]) -> str:
    return f"configured:{len(values)}" if values else "missing"


def _compare_section(
    section_id: str,
    title: str,
    rows: list[IloSetupCompareRowRead],
) -> IloSetupCompareSectionRead:
    status_order = {
        "mismatch": 0,
        "blocked": 1,
        "discovered_unknown": 2,
        "desired_missing": 3,
        "not_comparable": 4,
        "match": 5,
    }
    section_status = min(rows, key=lambda row: status_order.get(row.status, 99)).status
    return IloSetupCompareSectionRead(
        id=section_id,
        title=title,
        status=section_status,
        apply_enabled=False,
        next_safe_action=_section_next_safe_action(section_status),
        rows=rows,
    )


def _compare_unknown(
    section: str,
    field: str,
    label: str,
    desired: str | None,
    *,
    sensitive: bool = False,
) -> IloSetupCompareRowRead:
    if _missing(desired):
        return _compare_row(
            section,
            field,
            label,
            desired="missing",
            discovered="unknown",
            status="desired_missing",
            next_safe_action="Save desired intent locally before comparing this field.",
        )
    return _compare_row(
        section,
        field,
        label,
        desired="configured" if sensitive else str(desired),
        discovered="unknown",
        status="discovered_unknown",
        next_safe_action=(
            "Run an explicit read-only discovery path when available; do not treat unknown "
            "discovery as a mismatch."
        ),
    )


def _compare_firmware_row(
    field: str,
    label: str,
    discovered: str | None,
) -> IloSetupCompareRowRead:
    if _missing(discovered):
        return _compare_row(
            "firmware",
            field,
            label,
            desired="not configured",
            discovered="unknown",
            status="discovered_unknown",
            next_safe_action="Run explicit read-only iLO discovery before firmware planning.",
        )
    return _compare_row(
        "firmware",
        field,
        label,
        desired="no firmware apply intent",
        discovered=str(discovered),
        status="not_comparable",
        next_safe_action="Review firmware readiness handoff; no firmware action is enabled.",
    )


def _snmp_enabled_compare_desired(intent: IloSetupIntentRead) -> str | None:
    if intent.snmp.enabled:
        return "enabled"
    if intent.snmp.destinations or intent.snmp.community_or_user_ref_labels:
        return "disabled"
    return None


def _compare_row(
    section: str,
    field: str,
    label: str,
    *,
    desired: str,
    discovered: str,
    status: str,
    next_safe_action: str,
) -> IloSetupCompareRowRead:
    return IloSetupCompareRowRead(
        section=section,
        field=field,
        label=label,
        desired=desired,
        discovered=discovered,
        status=status,
        next_safe_action=next_safe_action,
        apply_enabled=False,
    )


def _section_next_safe_action(status: str) -> str:
    if status == "desired_missing":
        return "Save desired intent locally, then refresh the compare report."
    if status == "discovered_unknown":
        return "Use cached readiness as context; run only explicit read-only discovery when available."
    if status == "not_comparable":
        return "Review the read-only report; no apply action is available."
    if status == "match":
        return "No action is needed for this read-only comparison."
    return "Review the report; no apply action is available."


def _missing(value: str | None) -> bool:
    return value is None or not str(value).strip()


def _intent_read(
    payload: IloSetupIntentWrite,
    *,
    created_at: Any = None,
    updated_at: Any = None,
) -> IloSetupIntentRead:
    return IloSetupIntentRead(
        provider_id=PROVIDER_ID,
        apply_enabled=False,
        created_at=created_at,
        updated_at=updated_at,
        **payload.model_dump(),
    )


def _network_status(intent: IloSetupIntentRead, summary: IloReadinessSummaryRead) -> str:
    if not any(
        (
            intent.network.hostname,
            intent.network.management_ip,
            intent.network.subnet_mask_or_prefix,
            intent.network.gateway,
            intent.network.vlan,
        )
    ):
        return "missing_intent"
    if summary.current_state.redfish_endpoint_detected == "detected":
        return "warning"
    return "planned"


def _network_preview(intent: IloSetupIntentRead) -> str:
    network = intent.network
    if not any(
        (
            network.hostname,
            network.management_ip,
            network.subnet_mask_or_prefix,
            network.gateway,
            network.vlan,
        )
    ):
        return "Missing network intent. No network settings are planned."
    parts = [
        _label("hostname", network.hostname),
        _label("management IP", network.management_ip),
        _label("subnet/prefix", network.subnet_mask_or_prefix),
        _label("gateway", network.gateway),
        _label("VLAN", network.vlan),
    ]
    return f"Preview only: {', '.join(part for part in parts if part)}. No network setting is changed."


def _network_warnings(intent: IloSetupIntentRead) -> list[str]:
    required = (
        intent.network.hostname,
        intent.network.management_ip,
        intent.network.subnet_mask_or_prefix,
        intent.network.gateway,
    )
    if any(required) and not all(required):
        return ["Network intent is partial; hostname, management IP, subnet/prefix, and gateway are expected together."]
    return []


def _users_preview(intent: IloSetupIntentRead) -> str:
    if not intent.users:
        return "Missing user intent. No local user labels or roles are planned."
    users = ", ".join(f"{user.username_label} as {user.role}" for user in intent.users)
    return f"Preview only: desired local user labels {users}. No users or passwords are changed."


def _snmp_status(intent: IloSetupIntentRead) -> str:
    if not intent.snmp.enabled and not intent.snmp.destinations and not intent.snmp.community_or_user_ref_labels:
        return "missing_intent"
    if intent.snmp.enabled and not intent.snmp.destinations:
        return "blocked"
    return "planned"


def _snmp_preview(intent: IloSetupIntentRead) -> str:
    if _snmp_status(intent) == "missing_intent":
        return "Missing SNMP intent. No SNMP settings are planned."
    state = "enabled" if intent.snmp.enabled else "disabled"
    destinations = ", ".join(intent.snmp.destinations) or "no destinations"
    refs = ", ".join(intent.snmp.community_or_user_ref_labels) or "no community/user refs"
    return f"Preview only: SNMP {state}, destinations {destinations}, references {refs}. No SNMP setting is written."


def _snmp_warnings(intent: IloSetupIntentRead) -> list[str]:
    if intent.snmp.enabled and not intent.snmp.community_or_user_ref_labels:
        return ["SNMP is enabled without community/user reference labels."]
    return []


def _time_status(intent: IloSetupIntentRead) -> str:
    if not intent.time.timezone and not intent.time.ntp_servers:
        return "missing_intent"
    if intent.time.timezone and intent.time.ntp_servers:
        return "planned"
    return "warning"


def _time_preview(intent: IloSetupIntentRead) -> str:
    if _time_status(intent) == "missing_intent":
        return "Missing NTP/time intent. No time settings are planned."
    servers = ", ".join(intent.time.ntp_servers) or "no NTP servers"
    return f"Preview only: timezone {intent.time.timezone or 'not set'}, NTP servers {servers}. No time setting is written."


def _time_warnings(intent: IloSetupIntentRead) -> list[str]:
    if _time_status(intent) == "warning":
        return ["NTP/time intent is partial; timezone and NTP server placeholders are expected together."]
    return []


def _dns_status(intent: IloSetupIntentRead) -> str:
    if not intent.dns_domain.domain_name and not intent.dns_domain.dns_servers:
        return "missing_intent"
    if intent.dns_domain.domain_name and intent.dns_domain.dns_servers:
        return "planned"
    return "warning"


def _dns_preview(intent: IloSetupIntentRead) -> str:
    if _dns_status(intent) == "missing_intent":
        return "Missing DNS/domain intent. No DNS settings are planned."
    servers = ", ".join(intent.dns_domain.dns_servers) or "no DNS servers"
    return f"Preview only: domain {intent.dns_domain.domain_name or 'not set'}, DNS servers {servers}. No DNS setting is written."


def _dns_warnings(intent: IloSetupIntentRead) -> list[str]:
    if _dns_status(intent) == "warning":
        return ["DNS/domain intent is partial; domain and DNS server placeholders are expected together."]
    return []


def _firmware_status(summary: IloReadinessSummaryRead) -> str:
    decision = summary.firmware_readiness.decision
    if decision.status == "current":
        return "already_discovered"
    if summary.firmware_readiness.blockers:
        return "blocked"
    if summary.firmware_readiness.warnings or summary.firmware_readiness.removable_warnings:
        return "warning"
    return "planned"


def _label(name: str, value: str | None) -> str:
    return f"{name} {value}" if value else ""


def _last_probe_status(probe_result: dict[str, Any] | None) -> str:
    if not probe_result:
        return "no_probe"
    status = probe_result.get("status")
    return status if isinstance(status, str) and status else "unknown"


def _redfish_endpoint_detected(probe_result: dict[str, Any] | None) -> str:
    if not probe_result:
        return "no_probe"
    if probe_result.get("status") != "ok":
        return "not_detected"
    service_root = probe_result.get("service_root")
    return "detected" if isinstance(service_root, dict) and service_root else "unknown"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
