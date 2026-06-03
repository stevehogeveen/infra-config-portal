from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.providers.ilo_redfish import IloRedfishAdapter, PROVIDER_ID
from app.providers.probe_cache import get_probe_result
from app.schemas import (
    IloConnectionReadinessRead,
    IloCurrentStateRead,
    IloDesiredSetupSectionRead,
    IloReadinessSummaryRead,
    IloReportArtifactPlaceholderRead,
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
