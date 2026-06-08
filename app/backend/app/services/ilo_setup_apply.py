from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.providers.action_policy import (
    ActionCategory,
    LOCAL_LAB_MODE,
    LOCAL_READONLY_MODE,
    current_lab_action_policy,
)
from app.providers.ilo_redfish import (
    IloRedfishConfig,
    _base_url,
    _get_json,
    _odata_id,
    _redfish_url,
)
from app.providers.lab_safety import current_lab_safety
from app.providers.probe_cache import record_probe_result
from app.providers.redaction import redact_sensitive
from app.schemas import IloSetupApplyCreate
from app.services.ilo_readiness import get_ilo_setup_intent

APPLY_PROVIDER_ID = "ilo-redfish-setup-apply"
CONFIRMATION_PHRASE = "APPLY ILO HOSTNAME SETUP"
HOSTNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,62}$")
BLOCKED_ACTIONS = [
    "management IP changes",
    "gateway changes",
    "subnet or prefix changes",
    "VLAN changes",
    "user or role changes",
    "SNMP changes",
    "NTP server changes",
    "DNS server changes",
    "firmware upload or flash",
    "virtual media mount or eject",
    "boot order changes",
    "power actions",
    "iLO reset",
]


def build_ilo_setup_apply_plan(session: Session) -> dict[str, Any]:
    config = IloRedfishConfig.from_settings()
    intent = get_ilo_setup_intent(session)
    hostname = intent.network.hostname
    blockers: list[str] = []
    warnings: list[str] = []
    operations: list[dict[str, Any]] = []

    if not hostname:
        blockers.append("Saved iLO setup intent network.hostname is required for this apply lane.")
    elif not HOSTNAME_RE.match(hostname):
        blockers.append(
            "Saved iLO hostname must start with a letter and contain only letters, numbers, or hyphens."
        )
    else:
        operations.append(
            {
                "id": "manager_network_protocol_hostname",
                "method": "PATCH",
                "resource": "ManagerNetworkProtocol",
                "field": "HostName",
                "path": "discovered from /redfish/v1/Managers",
                "desired_value_redacted": True,
                "verify_after_patch": True,
            }
        )

    if any(
        [
            intent.network.management_ip,
            intent.network.subnet_mask_or_prefix,
            intent.network.gateway,
            intent.network.vlan,
        ]
    ):
        blockers.append(
            "iLO IP, subnet, gateway, and VLAN changes are blocked to avoid cutting off management access."
        )
    if intent.users:
        blockers.append("iLO user and role changes are blocked in this hostname-only apply lane.")
    if intent.snmp.enabled or intent.snmp.destinations or intent.snmp.community_or_user_ref_labels:
        blockers.append("SNMP changes are blocked until a field-level readback/compare lane is added.")
    if intent.time.timezone or intent.time.ntp_servers:
        blockers.append("NTP/time changes are blocked until this lab iLO schema is verified.")
    if intent.dns_domain.domain_name or intent.dns_domain.dns_servers:
        warnings.append(
            "DNS/domain intent is saved for preview, but this apply lane changes only HostName."
        )

    gate_blockers = _environment_gate_blockers(config, confirmation_phrase=CONFIRMATION_PHRASE)
    apply_enabled = bool(operations) and not blockers and not gate_blockers

    return {
        "provider_id": APPLY_PROVIDER_ID,
        "status": "ready_to_apply" if apply_enabled else "blocked",
        "message": (
            "iLO HostName apply gates are satisfied."
            if apply_enabled
            else "iLO HostName apply is blocked; no settings were changed."
        ),
        "apply_enabled": apply_enabled,
        "execution_supported": True,
        "actual_write_supported": True,
        "target": {
            "host_configured": bool(config.host),
            "target_ack_required": "LAB_TARGET_ACK must match the configured ILO_TEST_HOST value.",
            "target_redacted": True,
        },
        "operations": operations,
        "blocked_actions": BLOCKED_ACTIONS,
        "required_gates": [
            "PROVIDER_MODE=local-lab-readwrite with all required lab acknowledgement flags.",
            "The action must be represented as an explicit workflow step.",
            "This lane only changes iLO HostName; IP, gateway, VLAN, user, firmware, power, and reset remain blocked here.",
        ],
        "blockers": list(dict.fromkeys([*blockers, *gate_blockers])),
        "warnings": warnings,
        "confirmation_phrase": CONFIRMATION_PHRASE,
        "next_safe_action": (
            "Set only the required local gates, save a hostname intent, review this plan, "
            "then POST the exact confirmation phrase."
        ),
    }


def apply_ilo_setup(session: Session, payload: IloSetupApplyCreate) -> dict[str, Any]:
    config = IloRedfishConfig.from_settings()
    plan = build_ilo_setup_apply_plan(session)
    blockers = list(plan["blockers"])
    blockers.extend(_environment_gate_blockers(config, confirmation_phrase=payload.confirmation_phrase))
    if payload.destructive_action_requested or _requests_blocked_action(payload.requested_actions):
        blockers.append("Requested action includes a blocked or destructive iLO operation.")

    if blockers:
        return _record_result(
            config,
            {
                "provider_id": APPLY_PROVIDER_ID,
                "status": "blocked",
                "message": "iLO setup apply was blocked; no Redfish PATCH was sent.",
                "patch_attempted": False,
                "patch_count": 0,
                "blockers": list(dict.fromkeys(blockers)),
                "warnings": plan["warnings"],
                "checked_at": datetime.now(UTC).isoformat(),
            },
        )

    intent = get_ilo_setup_intent(session)
    desired_hostname = intent.network.hostname
    assert desired_hostname is not None
    assert config.host is not None
    assert config.username is not None
    assert config.password is not None

    requests: list[dict[str, Any]] = []
    operations: list[dict[str, Any]] = []
    status = "ok"
    message = "iLO HostName setup apply completed and readback verification passed."
    blockers = []

    try:
        timeout = httpx.Timeout(config.timeout_seconds)
        with httpx.Client(
            auth=(config.username, config.password),
            follow_redirects=False,
            timeout=timeout,
            trust_env=False,
            verify=config.verify_tls,
        ) as client:
            base_url = _base_url(config.host)
            manager_path = _manager_path(client, base_url, requests)
            network_protocol_path = _network_protocol_path(
                client,
                base_url,
                manager_path,
                requests,
            )
            before = _get_json(client, base_url, network_protocol_path, requests)
            before_hostname = _string_value(before.get("HostName"))
            if before_hostname == desired_hostname:
                operations.append(
                    {
                        "id": "manager_network_protocol_hostname",
                        "status": "already_matched",
                        "path": network_protocol_path,
                        "patch_sent": False,
                        "verified": True,
                    }
                )
            else:
                response = client.patch(
                    _redfish_url(base_url, network_protocol_path),
                    json={"HostName": desired_hostname},
                )
                requests.append(
                    {
                        "method": "PATCH",
                        "path": network_protocol_path,
                        "status_code": response.status_code,
                    }
                )
                response.raise_for_status()
                after = _get_json(client, base_url, network_protocol_path, requests)
                after_hostname = _string_value(after.get("HostName"))
                verified = after_hostname == desired_hostname
                operations.append(
                    {
                        "id": "manager_network_protocol_hostname",
                        "status": "verified" if verified else "readback_mismatch",
                        "path": network_protocol_path,
                        "patch_sent": True,
                        "verified": verified,
                    }
                )
                if not verified:
                    status = "failed"
                    message = "iLO HostName PATCH completed but readback did not match intent."
                    blockers.append("Readback verification did not match the saved hostname intent.")
    except httpx.HTTPStatusError as exc:
        status = "failed"
        message = "iLO HostName PATCH failed with an HTTP error."
        blockers.append(f"Redfish returned HTTP {exc.response.status_code}; no further writes were attempted.")
    except httpx.HTTPError as exc:
        status = "failed"
        message = "iLO HostName PATCH failed before completing safely."
        blockers.append(f"Redfish client error: {exc.__class__.__name__}.")

    return _record_result(
        config,
        {
            "provider_id": APPLY_PROVIDER_ID,
            "status": status,
            "message": message,
            "patch_attempted": any(operation.get("patch_sent") for operation in operations),
            "patch_count": sum(1 for operation in operations if operation.get("patch_sent")),
            "operations": operations,
            "requests": requests,
            "blockers": blockers,
            "warnings": plan["warnings"],
            "checked_at": datetime.now(UTC).isoformat(),
        },
        extra_redactions=[desired_hostname],
    )


def _environment_gate_blockers(
    config: IloRedfishConfig,
    *,
    confirmation_phrase: str,
) -> list[str]:
    blockers: list[str] = []
    if config.missing_fields:
        blockers.append(f"Missing local iLO configuration: {', '.join(config.missing_fields)}.")
    if settings.provider_mode == LOCAL_READONLY_MODE:
        safety = current_lab_safety()
        blockers.append("PROVIDER_MODE=local-readonly is read-only; Redfish PATCH writes are blocked.")
        if not safety.readonly_allowed:
            blockers.extend(safety.blockers)
    if settings.provider_mode == LOCAL_LAB_MODE:
        policy = current_lab_action_policy(settings.provider_mode)
        blockers.extend(
            policy.action_blockers(
                "ilo-redfish.manager-network-protocol-hostname",
                ActionCategory.NETWORK_CONFIG,
            )
        )
    if settings.provider_mode not in {LOCAL_READONLY_MODE, LOCAL_LAB_MODE}:
        blockers.append(
            "PROVIDER_MODE=local-lab-readwrite plus an explicit workflow step is required "
            "before any iLO Redfish PATCH can run."
        )
    if not settings.ilo_setup_apply_enabled:
        blockers.append("ILO_SETUP_APPLY_ENABLED=true is required for guarded iLO setup apply.")
    if settings.lab_apply_ack != "YES":
        blockers.append("LAB_APPLY_ACK=YES is required for guarded iLO setup apply.")
    if not config.host or settings.lab_target_ack != config.host:
        blockers.append("LAB_TARGET_ACK must match the configured ILO_TEST_HOST value.")
    if confirmation_phrase != CONFIRMATION_PHRASE:
        blockers.append(f"Exact confirmation phrase is required: {CONFIRMATION_PHRASE}")
    return list(dict.fromkeys(blockers))


def _manager_path(client: httpx.Client, base_url: str, requests: list[dict[str, Any]]) -> str:
    root = _get_json(client, base_url, "/redfish/v1/", requests)
    managers_path = _odata_id(root.get("Managers")) or "/redfish/v1/Managers/"
    managers = _get_json(client, base_url, managers_path, requests)
    members = managers.get("Members", [])
    if not isinstance(members, list) or not members:
        raise httpx.HTTPError("Redfish Managers collection has no members.")
    path = _odata_id(members[0])
    if not path:
        raise httpx.HTTPError("Redfish Managers collection member has no @odata.id.")
    return path


def _network_protocol_path(
    client: httpx.Client,
    base_url: str,
    manager_path: str,
    requests: list[dict[str, Any]],
) -> str:
    manager = _get_json(client, base_url, manager_path, requests)
    return _odata_id(manager.get("NetworkProtocol")) or f"{manager_path.rstrip('/')}/NetworkProtocol"


def _requests_blocked_action(value: object) -> bool:
    if not isinstance(value, list):
        return False
    blocked_terms = (
        "power",
        "reset",
        "reboot",
        "firmware",
        "virtual media",
        "boot",
        "user",
        "password",
        "ip",
        "gateway",
        "vlan",
        "snmp",
        "ntp",
        "dns",
    )
    return any(
        isinstance(item, str) and any(term in item.lower() for term in blocked_terms)
        for item in value
    )


def _string_value(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _record_result(
    config: IloRedfishConfig,
    result: dict[str, Any],
    *,
    extra_redactions: list[str | None] | None = None,
) -> dict[str, Any]:
    values: list[str | None] = [config.password, config.username, config.host]
    values.extend(extra_redactions or [])
    redacted = redact_sensitive(result, values)
    return record_probe_result(APPLY_PROVIDER_ID, redacted)
