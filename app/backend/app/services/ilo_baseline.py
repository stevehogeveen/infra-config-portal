from __future__ import annotations

from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address, IPv4Network, ip_address, ip_network
from typing import Any

from app.providers.ilo_redfish import IloRedfishAdapter, PROVIDER_ID as ILO_REDFISH_PROVIDER_ID
from app.providers.probe_cache import get_probe_result
from app.schemas import (
    IloBaselineBlockerRead,
    IloBaselineDiscoveryRangeRead,
    IloBaselineKitProfileRead,
    IloBaselinePlanRowRead,
    IloBaselinePreviewRead,
    IloBaselineReadinessCheckRead,
    IloBaselineReadinessRead,
    IloBaselineSectionRead,
    IloReportArtifactPlaceholderRead,
)
from app.services.lab_profiles import active_lab_profile_context

HPE_ILO_BASELINE_PROVIDER_ID = "hpe-ilo"
APPLY_REASON = (
    "Preview/readiness only. iLO configuration writes, user changes, SNMP writes, "
    "license changes, reset, and apply actions are disabled until a future guarded "
    "workflow adds explicit approval and readback verification."
)
RECHECK_COMMAND = "make provider-lab-ilo-reachability"
DEFAULT_TIMEZONE = "Eastern"
STALE_AFTER = timedelta(hours=24)


def get_ilo_baseline_preview() -> IloBaselinePreviewRead:
    generated_at = datetime.now(UTC)
    profile_context = active_lab_profile_context()
    profile = profile_context["active_profile"]
    probe_result, probe_checked_at = get_probe_result(ILO_REDFISH_PROVIDER_ID)
    provider_status = IloRedfishAdapter().health()
    metadata = _source_metadata(probe_result, probe_checked_at, generated_at)
    kit_profile = _kit_profile(profile, generated_at)
    discovery_range = _discovery_range(kit_profile, generated_at)
    current_state = _current_state(provider_status, probe_result, probe_checked_at, metadata)
    connection_readiness = _connection_readiness(
        provider_status,
        probe_result,
        probe_checked_at,
        metadata,
    )
    expected_sections = _expected_sections(kit_profile, discovery_range, current_state)
    rows = [
        *_kit_rows(kit_profile),
        *_discovery_rows(discovery_range),
        *_connection_rows(connection_readiness),
        *_baseline_rows(expected_sections, current_state),
        _reset_row(current_state),
    ]
    blockers = _blockers(provider_status)
    warnings = _warnings(kit_profile, discovery_range, current_state, provider_status)

    return IloBaselinePreviewRead(
        provider_id=HPE_ILO_BASELINE_PROVIDER_ID,
        source_provider_id=ILO_REDFISH_PROVIDER_ID,
        provider_mode=provider_status.mode,
        generated_at=generated_at,
        source_type=metadata["source_type"],
        checked_at=metadata["checked_at"],
        freshness=metadata["freshness"],
        kit_profile=kit_profile,
        discovery_range=discovery_range,
        connection_readiness=connection_readiness,
        current_state=current_state,
        comparison_rows=rows,
        reset_required=bool(current_state.get("reset_required")),
        apply_enabled=False,
        apply_reason=APPLY_REASON,
        blockers=blockers,
        warnings=warnings,
        next_action="Review the preview, then run iLO reachability for fresh live readiness before any future apply design.",
        expected_baseline_sections=expected_sections,
        reports_artifacts=[
            IloReportArtifactPlaceholderRead(
                kind="ilo-baseline-preview",
                title="iLO Baseline Configuration Preview",
                status="planned",
                note="Structured preview from active lab profile, cached read-only state, and secret references only.",
            ),
            IloReportArtifactPlaceholderRead(
                kind="ilo-baseline-readiness",
                title="iLO Baseline Readiness",
                status="not_checked" if probe_result is None else metadata["freshness"],
                note="Fresh live readiness requires an explicit reachability or GET-only Redfish check.",
            ),
        ],
    )


def get_ilo_baseline_readiness() -> IloBaselineReadinessRead:
    preview = get_ilo_baseline_preview()
    return IloBaselineReadinessRead(
        provider_id=preview.provider_id,
        source_provider_id=preview.source_provider_id,
        provider_mode=preview.provider_mode,
        generated_at=preview.generated_at,
        source_type=preview.source_type,
        checked_at=preview.checked_at,
        freshness=preview.freshness,
        kit_profile=preview.kit_profile,
        discovery_range=preview.discovery_range,
        connection_readiness=preview.connection_readiness,
        current_state=preview.current_state,
        comparison_rows=[
            row
            for row in preview.comparison_rows
            if row.section in {"Connection Readiness", "Discovery", "Reset Handling"}
        ],
        reset_required=preview.reset_required,
        apply_enabled=False,
        apply_reason=preview.apply_reason,
        blockers=preview.blockers,
        warnings=preview.warnings,
        next_action=preview.next_action,
    )


def _kit_profile(profile: dict[str, Any], generated_at: datetime) -> IloBaselineKitProfileRead:
    global_settings = _dict(profile.get("global_settings"))
    address_plan = _dict(profile.get("resolved_address_plan") or profile.get("address_plan"))
    gateway = _clean(global_settings.get("gateway") or profile.get("gateway")) or "not_configured"
    subnet = _clean(address_plan.get("subnet") or profile.get("subnet_cidr"))
    network = _network_from_profile(subnet)
    subnet_mask = str(network.netmask) if network else "not_configured"
    derived_subnet = _derived_subnet(gateway, subnet_mask, network)
    dns_servers = _string_list(global_settings.get("dns_servers") or profile.get("dns"))
    kit_id = _kit_id(profile)

    return IloBaselineKitProfileRead(
        kit_id=kit_id,
        support_unit=_clean(global_settings.get("support_unit")) or "not_configured",
        subnet_mask=subnet_mask,
        gateway=gateway,
        dom_dc=_clean(global_settings.get("dom_dc"))
        or _first_ip_or_placeholder(dns_servers, "not_configured"),
        derived_subnet=derived_subnet,
        source_type="operator_config",
        checked_at=generated_at.isoformat(),
        freshness="live",
    )


def _discovery_range(
    kit_profile: IloBaselineKitProfileRead,
    generated_at: datetime,
) -> IloBaselineDiscoveryRangeRead:
    network = _network_from_profile(kit_profile.derived_subnet)
    addresses: list[str] = []
    if network is not None:
        addresses = [
            str(address)
            for offset in range(21, 30)
            for address in [network.network_address + offset]
            if address in network
        ]
    start_host = addresses[0] if addresses else "not_available"
    end_host = addresses[-1] if addresses else "not_available"
    return IloBaselineDiscoveryRangeRead(
        source_subnet=kit_profile.derived_subnet,
        default_start_host=start_host,
        default_end_host=end_host,
        addresses=addresses,
        override_supported=True,
        override_active=False,
        source_type="operator_config",
        checked_at=generated_at.isoformat(),
        freshness="live",
    )


def _current_state(
    provider_status: Any,
    probe_result: dict[str, Any] | None,
    probe_checked_at: str | None,
    metadata: dict[str, str | None],
) -> dict[str, Any]:
    endpoint_detection = _dict((probe_result or {}).get("endpoint_detection"))
    return {
        "source_type": metadata["source_type"],
        "checked_at": probe_checked_at,
        "freshness": metadata["freshness"],
        "provider_status": provider_status.status,
        "provider_mode": provider_status.mode,
        "target_configured": _presence(provider_status.configuration.get("host_configured")),
        "username_configured": _presence(provider_status.configuration.get("username_configured")),
        "password_configured": _presence(provider_status.configuration.get("password_configured")),
        "login_status": "redacted",
        "ping_reachability": "not_checked",
        "https_443": _https_status(endpoint_detection),
        "redfish_root": str(endpoint_detection.get("redfish_status") or "not_checked"),
        "license_status": _license_status(probe_result),
        "users": "not_checked",
        "snmp": "not_checked",
        "snmpv3": "not_checked",
        "alert_destinations": "not_checked",
        "dedicated_ilo_ipv6": "not_checked",
        "sntp_time": "not_checked",
        "reset_required": bool(_dict(probe_result).get("reset_required")),
        "reset_status": "not_checked",
        "evidence": {
            "probe_cache": "available" if probe_result else "not_checked",
            "recheck_command": RECHECK_COMMAND,
        },
    }


def _connection_readiness(
    provider_status: Any,
    probe_result: dict[str, Any] | None,
    probe_checked_at: str | None,
    metadata: dict[str, str | None],
) -> list[IloBaselineReadinessCheckRead]:
    config = provider_status.configuration
    endpoint_detection = _dict((probe_result or {}).get("endpoint_detection"))
    redfish_status = str(endpoint_detection.get("redfish_status") or "not_checked")
    https_status = _https_status(endpoint_detection)
    return [
        _readiness_check(
            "Target configured",
            "ok" if config.get("host_configured") else "missing",
            _presence(config.get("host_configured")),
            "configured",
            "operator_config",
            None,
            "live",
            "iLO target is represented only as a configured/missing flag.",
            "Set ILO_TEST_HOST locally, then rerun readiness.",
        ),
        _readiness_check(
            "Credential references",
            "ok"
            if config.get("username_configured") and config.get("password_configured")
            else "missing",
            (
                "configured"
                if config.get("username_configured") and config.get("password_configured")
                else "missing"
            ),
            "configured secret references",
            "operator_config",
            None,
            "live",
            "Login/configuration state is redacted; no username or password is returned.",
            "Set local iLO credential references, then rerun readiness.",
        ),
        _readiness_check(
            "Ping reachability",
            "not_checked",
            "not_checked",
            "reachable is not sufficient for readiness",
            "not_checked",
            None,
            "not_checked",
            "Ping is intentionally not treated as iLO readiness.",
            RECHECK_COMMAND,
        ),
        _readiness_check(
            "HTTPS / 443",
            "ok" if https_status == "available" else "not_checked",
            https_status,
            "available",
            str(metadata["source_type"]),
            probe_checked_at,
            str(metadata["freshness"]),
            "HTTPS readiness is taken only from cached explicit checks when present.",
            RECHECK_COMMAND,
        ),
        _readiness_check(
            "Redfish root",
            "ok" if redfish_status == "available" else "not_checked",
            redfish_status,
            "available",
            str(metadata["source_type"]),
            probe_checked_at,
            str(metadata["freshness"]),
            "Redfish root readiness is cached GET-only evidence when available.",
            "Run GET-only endpoint detection before treating Redfish as ready.",
        ),
    ]


def _expected_sections(
    kit_profile: IloBaselineKitProfileRead,
    discovery_range: IloBaselineDiscoveryRangeRead,
    current_state: dict[str, Any],
) -> list[IloBaselineSectionRead]:
    kit_id = kit_profile.kit_id
    admin_user = f"{kit_id}_Admin"
    operator_user = f"{kit_id}_OA"
    service_user = f"{kit_id}_ServiceAdmin"
    alert_destinations = _alert_destinations(kit_profile)
    return [
        _section(
            "users",
            "User Baseline",
            {
                "admin_account": admin_user,
                "operator_account": operator_user,
                "service_admin_account": service_user,
                "password_handling": "secret references only",
            },
            secret_refs=[
                "secret-ref:ilo-admin-password",
                "secret-ref:ilo-oa-password",
                "secret-ref:ilo-service-admin-password",
            ],
        ),
        _section(
            "license",
            "License Check",
            {
                "current_license_status": current_state.get("license_status") or "unknown",
                "allowed_statuses": ["unknown", "ok", "missing", "error"],
                "preview_blocks_on_unknown": False,
            },
            notes=["Unknown license status does not block this preview."],
        ),
        _section(
            "snmp",
            "SNMP Baseline",
            {
                "system_contact": kit_profile.support_unit,
                "system_location": kit_id,
                "read_community": "secret-ref:ilo-snmp-read-community",
                "system_role": "iLO",
            },
            secret_refs=["secret-ref:ilo-snmp-read-community"],
        ),
        _section(
            "snmpv3",
            "SNMPv3 Baseline",
            {
                "user": f"{kit_id}_SNMPv3",
                "auth_protocol": "SHA",
                "privacy_protocol": "AES",
                "auth_passphrase": "secret-ref:ilo-snmpv3-auth-passphrase",
                "privacy_passphrase": "secret-ref:ilo-snmpv3-privacy-passphrase",
            },
            secret_refs=[
                "secret-ref:ilo-snmpv3-auth-passphrase",
                "secret-ref:ilo-snmpv3-privacy-passphrase",
            ],
        ),
        _section(
            "alert_destinations",
            "SNMP Alert Destinations",
            {
                "desired_destinations": alert_destinations,
                "alert_protocol": "SNMPv3Inform",
                "reconcile_behavior": "add missing, update existing, avoid duplicates",
            },
        ),
        _section(
            "ipv6_dedicated",
            "Dedicated iLO Network IPv6",
            {
                "dhcpv6_dns_server": "disabled",
                "dhcpv6_domain_name": "disabled",
                "dhcpv6_rapid_commit": "disabled",
                "dhcpv6_sntp": "disabled",
                "dhcpv6_stateful_mode": "disabled",
                "dhcpv6_stateless_mode": "disabled",
            },
        ),
        _section(
            "sntp_time",
            "SNTP / Time Baseline",
            {
                "dhcpv4_ntp": "disabled",
                "dhcpv6_ntp": "disabled",
                "interface_type": "Dedicated",
                "sntp_server": kit_profile.gateway,
                "timezone": DEFAULT_TIMEZONE,
            },
        ),
        _section(
            "reset_handling",
            "Reset Handling",
            {
                "reset_required": bool(current_state.get("reset_required")),
                "auto_reset": False,
                "future_guard": "requires explicit approval and confirmation",
            },
            notes=["Reset is a guarded future plan item only; this preview never resets the server."],
        ),
    ]


def _kit_rows(kit_profile: IloBaselineKitProfileRead) -> list[IloBaselinePlanRowRead]:
    fields = [
        ("KitID", kit_profile.kit_id),
        ("SupportUnit", kit_profile.support_unit),
        ("SubnetMask", kit_profile.subnet_mask),
        ("Gateway", kit_profile.gateway),
        ("DomDC", kit_profile.dom_dc),
        ("Derived subnet", kit_profile.derived_subnet),
    ]
    return [
        _row(
            "Kit Profile",
            label,
            "operator_config",
            value,
            "warning" if value == "not_configured" else "check",
            "warning" if value == "not_configured" else "info",
            f"{label} is derived from the active lab profile.",
        )
        for label, value in fields
    ]


def _discovery_rows(discovery_range: IloBaselineDiscoveryRangeRead) -> list[IloBaselinePlanRowRead]:
    desired = ", ".join(discovery_range.addresses) or "not_available"
    return [
        _row(
            "Discovery",
            "Default iLO scan range",
            "not_checked",
            desired,
            "check",
            "info",
            "Default discovery scans subnet .21 through .29; ping alone is not readiness.",
        )
    ]


def _connection_rows(checks: list[IloBaselineReadinessCheckRead]) -> list[IloBaselinePlanRowRead]:
    return [
        _row(
            "Connection Readiness",
            check.name,
            check.current,
            check.desired,
            "warning" if check.status == "missing" else "check",
            "warning" if check.status in {"missing", "not_checked"} else "info",
            check.message,
        )
        for check in checks
    ]


def _baseline_rows(
    sections: list[IloBaselineSectionRead],
    current_state: dict[str, Any],
) -> list[IloBaselinePlanRowRead]:
    rows: list[IloBaselinePlanRowRead] = []
    section_by_id = {section.id: section for section in sections}
    users = section_by_id["users"].items
    rows.extend(
        [
            _row(
                "User Baseline",
                "Admin account",
                current_state["users"],
                users["admin_account"],
                "create",
                "warning",
                "Future apply would create or update the admin-style account from KitID; password is a secret reference.",
            ),
            _row(
                "User Baseline",
                "Operator account",
                current_state["users"],
                users["operator_account"],
                "create",
                "warning",
                "Future apply would create or update the OA-style account from KitID; password is a secret reference.",
            ),
            _row(
                "User Baseline",
                "Service/admin placeholder",
                current_state["users"],
                users["service_admin_account"],
                "create",
                "warning",
                "Service/admin account is a placeholder with secret-reference password handling only.",
            ),
        ]
    )
    rows.append(
        _row(
            "License Check",
            "License status",
            current_state["license_status"],
            "ok",
            "check",
            "warning",
            "Unknown license status is allowed in preview and must be checked before any future apply.",
        )
    )
    snmp = section_by_id["snmp"].items
    rows.extend(
        [
            _row("SNMP Baseline", "System contact", current_state["snmp"], snmp["system_contact"], "update", "warning", "SNMP current state is not read yet."),
            _row("SNMP Baseline", "System location", current_state["snmp"], snmp["system_location"], "update", "warning", "System location should match KitID."),
            _row("SNMP Baseline", "Read community", current_state["snmp"], snmp["read_community"], "update", "warning", "Community value is represented only as a secret reference."),
            _row("SNMP Baseline", "System role", current_state["snmp"], snmp["system_role"], "update", "warning", "System role baseline is iLO."),
        ]
    )
    snmpv3 = section_by_id["snmpv3"].items
    rows.extend(
        [
            _row("SNMPv3 Baseline", "SNMPv3 user", current_state["snmpv3"], snmpv3["user"], "create", "warning", "SNMPv3 user is expected but current iLO state is not checked."),
            _row("SNMPv3 Baseline", "Auth protocol", current_state["snmpv3"], snmpv3["auth_protocol"], "update", "warning", "Auth protocol baseline is SHA."),
            _row("SNMPv3 Baseline", "Privacy protocol", current_state["snmpv3"], snmpv3["privacy_protocol"], "update", "warning", "Privacy protocol baseline is AES."),
            _row("SNMPv3 Baseline", "Passphrases", current_state["snmpv3"], "secret-ref:ilo-snmpv3-*", "update", "warning", "SNMPv3 passphrases are secret references only."),
        ]
    )
    alerts = section_by_id["alert_destinations"].items
    rows.append(
        _row(
            "SNMP Alert Destinations",
            "Alert destination reconcile",
            current_state["alert_destinations"],
            alerts["desired_destinations"],
            "update",
            "warning",
            "Plan behavior is reconcile-style: add missing, update existing, and avoid duplicates.",
        )
    )
    ipv6 = section_by_id["ipv6_dedicated"].items
    rows.append(
        _row(
            "Dedicated iLO Network IPv6",
            "DHCPv6 dedicated-port options",
            current_state["dedicated_ilo_ipv6"],
            ipv6,
            "update",
            "warning",
            "Future apply would disable DHCPv6 DNS, domain name, rapid commit, SNTP, stateful, and stateless modes.",
        )
    )
    time = section_by_id["sntp_time"].items
    rows.append(
        _row(
            "SNTP / Time Baseline",
            "SNTP and timezone",
            current_state["sntp_time"],
            time,
            "update",
            "warning",
            "Future apply would disable DHCP NTP, use the Dedicated interface, default SNTP to Gateway, and timezone to Eastern.",
        )
    )
    return rows


def _reset_row(current_state: dict[str, Any]) -> IloBaselinePlanRowRead:
    return _row(
        "Reset Handling",
        "Reset after baseline",
        current_state.get("reset_status") or "not_checked",
        "guarded future reset only when reset_required is true",
        "requires_confirmation",
        "warning",
        "This first pass never auto-resets. Any future reset must be a guarded plan item with explicit approval.",
    )


def _blockers(provider_status: Any) -> list[IloBaselineBlockerRead]:
    blockers: list[IloBaselineBlockerRead] = []
    for blocker in provider_status.blockers:
        blockers.append(
            IloBaselineBlockerRead(
                problem=str(blocker),
                source=ILO_REDFISH_PROVIDER_ID,
                current_value=provider_status.status,
                expected_value="configured local iLO target and credential references",
                where_to_fix=".env.local.real-lab",
                recommended_action="Configure missing local iLO settings, then rerun readiness.",
                copyable_command=RECHECK_COMMAND,
                recheck_command=RECHECK_COMMAND,
                evidence_links=[],
            )
        )
    return blockers


def _warnings(
    kit_profile: IloBaselineKitProfileRead,
    discovery_range: IloBaselineDiscoveryRangeRead,
    current_state: dict[str, Any],
    provider_status: Any,
) -> list[str]:
    warnings = list(provider_status.warnings)
    if kit_profile.support_unit == "not_configured":
        warnings.append("SupportUnit is not configured in the active lab profile.")
    if kit_profile.dom_dc == "not_configured":
        warnings.append("DomDC is not configured; alert destinations stay a profile placeholder until set.")
    if not discovery_range.addresses:
        warnings.append("Default iLO discovery range could not be derived from the active subnet.")
    if current_state.get("license_status") == "unknown":
        warnings.append("iLO license status is unknown and does not block preview.")
    return _unique(warnings)


def _source_metadata(
    probe_result: dict[str, Any] | None,
    probe_checked_at: str | None,
    now: datetime,
) -> dict[str, str | None]:
    if probe_result is None:
        return {"source_type": "not_checked", "checked_at": None, "freshness": "not_checked"}
    checked = _parse_datetime(probe_checked_at)
    freshness = "stale"
    if checked is not None and now - checked <= STALE_AFTER:
        freshness = "live"
    return {"source_type": "live_cached", "checked_at": probe_checked_at, "freshness": freshness}


def _section(
    section_id: str,
    title: str,
    items: dict[str, Any],
    *,
    secret_refs: list[str] | None = None,
    notes: list[str] | None = None,
) -> IloBaselineSectionRead:
    return IloBaselineSectionRead(
        id=section_id,
        title=title,
        status="preview_only",
        items=items,
        secret_refs=secret_refs or [],
        notes=notes or [],
    )


def _readiness_check(
    name: str,
    status: str,
    current: str,
    desired: str,
    source_type: str,
    checked_at: str | None,
    freshness: str,
    message: str,
    next_action: str,
) -> IloBaselineReadinessCheckRead:
    return IloBaselineReadinessCheckRead(
        name=name,
        status=status,
        current=current,
        desired=desired,
        source_type=source_type,
        checked_at=checked_at,
        freshness=freshness,
        message=message,
        next_action=next_action,
    )


def _row(
    section: str,
    item: str,
    current: Any,
    desired: Any,
    action: str,
    severity: str,
    message: str,
) -> IloBaselinePlanRowRead:
    return IloBaselinePlanRowRead(
        section=section,
        item=item,
        current=current,
        desired=desired,
        action=action,  # type: ignore[arg-type]
        severity=severity,
        message=message,
    )


def _kit_id(profile: dict[str, Any]) -> str:
    candidate = _clean(profile.get("kit_id") or profile.get("name"))
    if not candidate:
        return "Kit"
    normalized = "".join(char if char.isalnum() else "_" for char in candidate).strip("_")
    return normalized or "Kit"


def _network_from_profile(value: str | None) -> IPv4Network | None:
    if not value or value == "not_configured":
        return None
    try:
        network = ip_network(value, strict=False)
    except ValueError:
        return None
    return network if isinstance(network, IPv4Network) else None


def _derived_subnet(
    gateway: str,
    subnet_mask: str,
    fallback_network: IPv4Network | None,
) -> str:
    if gateway != "not_configured":
        try:
            gateway_ip = ip_address(gateway)
            if isinstance(gateway_ip, IPv4Address) and subnet_mask != "not_configured":
                return str(ip_network(f"{gateway_ip}/{subnet_mask}", strict=False))
        except ValueError:
            pass
    return str(fallback_network) if fallback_network else "not_configured"


def _first_ip_or_placeholder(values: list[str], placeholder: str) -> str:
    for value in values:
        try:
            ip_address(value)
        except ValueError:
            continue
        return value
    return placeholder


def _alert_destinations(kit_profile: IloBaselineKitProfileRead) -> list[str]:
    if kit_profile.dom_dc == "not_configured":
        return ["profile:DomDC"]
    try:
        ip_address(kit_profile.dom_dc)
    except ValueError:
        return ["profile:DomDC"]
    return [kit_profile.dom_dc]


def _https_status(endpoint_detection: dict[str, Any]) -> str:
    redfish_status = str(endpoint_detection.get("redfish_status") or "not_checked")
    web_status = str(endpoint_detection.get("web_status") or "not_checked")
    if redfish_status == "available" or web_status == "available":
        return "available"
    return "not_checked"


def _license_status(probe_result: dict[str, Any] | None) -> str:
    if not probe_result:
        return "unknown"
    value = _dict(probe_result).get("license_status")
    text = str(value or "unknown").lower()
    return text if text in {"unknown", "ok", "missing", "error"} else "unknown"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _presence(value: Any) -> str:
    return "configured" if bool(value) else "missing"


def _dict(value: Any = None) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
