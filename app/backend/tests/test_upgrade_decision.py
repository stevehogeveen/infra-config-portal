from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from app.providers.base import ProviderStatus
from app.models import IloSetupIntent
from app.providers.probe_cache import clear_probe_results, record_probe_result
from app.schemas import (
    IloUpgradeReadinessRead,
    UpgradeCandidateRead,
    UpgradeDecisionRead,
    UpgradeRuleRead,
    UpgradeSubjectRead,
)
from app.services import ilo_readiness
from app.services.upgrade_decision import decide_upgrade


def _subject(
    *,
    current_version: str | None = "2.00",
    generation: str | None = "ilo5",
) -> UpgradeSubjectRead:
    return UpgradeSubjectRead(
        provider_type="ilo",
        product="hpe-ilo",
        generation=generation,
        model="ProLiant DL360 Gen10",
        current_version=current_version,
        discovery_confidence="exact" if current_version and generation else "weak",
    )


def _candidate(
    version: str | None,
    *,
    generation_hint: str | None = "ilo5",
    product_hint: str | None = "hpe-ilo",
    confidence: str = "exact",
) -> UpgradeCandidateRead:
    return UpgradeCandidateRead(
        id=f"firmware-{version or 'unknown'}",
        category="firmware",
        product_hint=product_hint,
        generation_hint=generation_hint,
        version=version,
        source="test-catalog",
        redacted_label=f"firmware-{version or 'unknown'}.fwpkg",
        match_confidence=confidence,
    )


def _rule(
    *,
    from_constraint: str = ">=2.00,<3.00",
    to_constraint: str = "3.00",
    requires_intermediate: list[str] | None = None,
) -> UpgradeRuleRead:
    return UpgradeRuleRead(
        product="hpe-ilo",
        generation="ilo5",
        from_constraint=from_constraint,
        to_constraint=to_constraint,
        requires_intermediate=requires_intermediate or [],
        source="test-rule",
        confidence="exact",
    )


def test_no_current_version_gives_discovery_incomplete_blocker() -> None:
    decision = decide_upgrade(_subject(current_version=None), [_candidate("3.00")], [_rule()])

    assert decision.status == "discovery_incomplete"
    assert "Current firmware version is unknown." in decision.blockers
    assert decision.apply_enabled is False


def test_no_candidate_gives_no_candidate_found() -> None:
    decision = decide_upgrade(_subject(), [], [_rule()])

    assert decision.status == "no_candidate_found"
    assert decision.blockers == ["No firmware candidate media was found in the metadata inventory."]
    assert decision.apply_enabled is False


def test_weak_filename_match_creates_warning_and_manual_review() -> None:
    decision = decide_upgrade(
        _subject(),
        [_candidate("3.00", generation_hint=None, product_hint=None, confidence="weak")],
        [_rule()],
    )

    assert decision.status == "manual_review_required"
    assert decision.recommended_target == "3.00"
    assert any("redacted filename hints" in warning for warning in decision.removable_warnings)
    assert decision.apply_enabled is False


def test_candidate_incompatible_with_generation_is_blocked() -> None:
    decision = decide_upgrade(_subject(), [_candidate("3.00", generation_hint="ilo6")], [_rule()])

    assert decision.status == "blocked_incompatible"
    assert decision.blockers == [
        "Firmware candidates do not match the discovered device generation."
    ]
    assert any("ilo6" in warning for warning in decision.removable_warnings)
    assert decision.apply_enabled is False


def test_missing_intermediate_blocks_unknown_path() -> None:
    decision = decide_upgrade(
        _subject(current_version="1.00"),
        [_candidate("3.00")],
        [_rule(from_constraint=">=1.00,<3.00", requires_intermediate=["2.00"])],
    )

    assert decision.status == "blocked_unknown_path"
    assert decision.required_intermediate_versions == ["2.00"]
    assert "2.00" in decision.blockers[0]
    assert decision.apply_enabled is False


def test_valid_simple_upgrade_path_returns_upgrade_available() -> None:
    decision = decide_upgrade(_subject(), [_candidate("3.00")], [_rule()])

    assert decision.status == "upgrade_available"
    assert decision.recommended_target == "3.00"
    assert [candidate.version for candidate in decision.candidate_chain] == ["3.00"]
    assert decision.apply_enabled is False


def test_current_version_equal_newest_returns_current() -> None:
    decision = decide_upgrade(_subject(current_version="3.00"), [_candidate("2.00"), _candidate("3.00")])

    assert decision.status == "current"
    assert decision.recommended_target == "3.00"
    assert decision.apply_enabled is False


def test_apply_enabled_is_always_false() -> None:
    decisions = [
        decide_upgrade(_subject(current_version=None), [_candidate("3.00")], [_rule()]),
        decide_upgrade(_subject(), [], [_rule()]),
        decide_upgrade(_subject(), [_candidate("3.00")], [_rule()]),
    ]

    assert all(decision.apply_enabled is False for decision in decisions)


def test_ilo_upgrade_readiness_response_includes_decision(client: TestClient) -> None:
    clear_probe_results()
    record_probe_result(
        "ilo-redfish",
        {
            "provider_id": "ilo-redfish",
            "status": "ok",
            "managers": [{"Name": "HPE iLO 5", "FirmwareVersion": "2.80"}],
            "systems": [{"Model": "ProLiant DL360 Gen10"}],
            "chassis": [],
            "firmware": [],
            "endpoint_detection": {
                "classification": "redfish_available",
                "message": "Redfish root is available. GET-only inventory discovery can continue.",
                "checks": [
                    {
                        "path": "/redfish/v1/",
                        "status_code": 200,
                        "content_type": "application/json",
                        "classification": "redfish_available",
                    }
                ],
                "redfish_status": "available",
                "legacy_status": "not_checked",
                "web_status": "not_checked",
                "next_safe_action": "Continue with GET-only Redfish inventory discovery. No settings were changed.",
            },
            "warnings": [],
            "blockers": [],
        },
    )

    response = client.get("/api/v1/providers/ilo-redfish/upgrade-readiness")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "ilo-redfish"
    assert payload["subject"]["current_version"] == "2.80"
    assert payload["subject"]["generation"] == "ilo5"
    assert "decision" in payload
    assert payload["decision"]["apply_enabled"] is False
    assert payload["apply_enabled"] is False
    clear_probe_results()


def test_ilo_readiness_summary_normalizes_readonly_state(client: TestClient) -> None:
    clear_probe_results()
    record_probe_result(
        "ilo-redfish",
        {
            "provider_id": "ilo-redfish",
            "status": "ok",
            "service_root": {"@odata.id": "/redfish/v1/"},
            "managers": [{"Name": "HPE iLO 5", "FirmwareVersion": "2.80"}],
            "systems": [
                {
                    "Model": "ProLiant DL360 Gen10",
                    "SerialNumber": "SERIAL-REDACTED",
                }
            ],
            "chassis": [],
            "firmware": [],
            "warnings": [],
            "blockers": [],
        },
    )

    response = client.get("/api/v1/providers/ilo-redfish/readiness-summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "ilo-redfish"
    assert payload["connection"]["provider_mode"] == "mock"
    assert payload["connection"]["redfish_probe_available"] is False
    assert payload["current_state"]["last_probe_status"] == "ok"
    assert payload["current_state"]["model"] == "ProLiant DL360 Gen10"
    assert payload["current_state"]["serial"] == "SERIAL-REDACTED"
    assert payload["current_state"]["current_firmware"] == "2.80"
    assert payload["current_state"]["ilo_generation"] == "ilo5"
    assert payload["current_state"]["endpoint_classification"] == "redfish_available"
    assert payload["current_state"]["redfish_root_status"] == "available"
    assert payload["current_state"]["endpoint_next_safe_action"].endswith("No settings were changed.")
    assert payload["current_state"]["redfish_endpoint_detected"] == "detected"
    assert payload["current_state"]["legacy_endpoint_status"] == "not_checked"
    assert payload["current_state"]["media_inventory_mode"] == "sample"
    assert payload["upgrade_decision_status"] == payload["firmware_readiness"]["decision"]["status"]
    assert payload["desired_setup_sections"]
    assert all(section["status"] == "plan_only" for section in payload["desired_setup_sections"])
    assert all(not section["apply_enabled"] for section in payload["desired_setup_sections"])
    assert payload["reports_artifacts"]
    assert payload["disabled_dangerous_actions"]
    assert all(not action["enabled"] for action in payload["disabled_dangerous_actions"])
    clear_probe_results()


def test_ilo_readiness_summary_keeps_scalar_missing_fields_whole(monkeypatch) -> None:
    class FakeIloRedfishAdapter:
        def health(self) -> ProviderStatus:
            return ProviderStatus(
                name="HPE iLO",
                kind="oob-management",
                mode="local-readonly",
                status="missing-config",
                capabilities=[],
                message="Missing config.",
                configuration={
                    "host_configured": False,
                    "username_configured": True,
                    "password_configured": True,
                    "tls_verify": True,
                    "timeout_seconds": 1.0,
                    "missing_fields": " ILO_TEST_HOST ",
                },
            )

    monkeypatch.setattr(ilo_readiness, "IloRedfishAdapter", FakeIloRedfishAdapter)
    monkeypatch.setattr(ilo_readiness, "get_media_inventory", lambda: SimpleNamespace(mode="sample"))
    monkeypatch.setattr(
        ilo_readiness,
        "get_ilo_upgrade_readiness",
        lambda: IloUpgradeReadinessRead(
            provider_id="ilo-redfish",
            subject=_subject(current_version=None, generation=None),
            candidates=[],
            decision=UpgradeDecisionRead(
                status="discovery_incomplete",
                next_safe_action="Run read-only discovery.",
            ),
        ),
    )
    clear_probe_results()

    summary = ilo_readiness.get_ilo_readiness_summary()

    assert summary.connection.missing_fields == ["ILO_TEST_HOST"]
    assert "I" not in summary.connection.missing_fields


def test_ilo_readiness_summary_reports_inventory_collection_auth_failure(
    client: TestClient,
) -> None:
    clear_probe_results()
    record_probe_result(
        "ilo-redfish",
        {
            "provider_id": "ilo-redfish",
            "status": "failed",
            "service_root": {"@odata.id": "/redfish/v1/"},
            "managers": [],
            "systems": [],
            "chassis": [],
            "firmware": [],
            "legacy_identity": {
                "source": "/xmldata?item=All",
                "serial_present": True,
                "model": "ProLiant DL360 Gen10",
                "current_firmware": "2.80",
                "ilo_generation": "ilo5",
            },
            "endpoint_detection": {
                "classification": "redfish_inventory_auth_failed",
                "message": "Redfish root is available, but inventory collections are unauthorized.",
                "checks": [
                    {
                        "path": "/redfish/v1/",
                        "status_code": 200,
                        "content_type": "application/json",
                        "classification": "redfish_root_available",
                    },
                    {
                        "path": "/xmldata?item=All",
                        "status_code": 200,
                        "content_type": "text/xml",
                        "classification": "legacy_available",
                    },
                ],
                "redfish_status": "available",
                "legacy_status": "available",
                "web_status": "available",
                "inventory_collection_status": "unauthorized",
                "inventory_collection_classification": "redfish_collection_unauthorized",
                "inventory_collection_checks": [
                    {
                        "name": "Managers",
                        "path": "/redfish/v1/Managers/",
                        "status_code": 401,
                        "content_type": "application/json",
                        "classification": "redfish_collection_unauthorized",
                    },
                    {
                        "name": "Systems",
                        "path": "/redfish/v1/Systems/",
                        "status_code": 401,
                        "content_type": "application/json",
                        "classification": "redfish_collection_unauthorized",
                    },
                    {
                        "name": "Chassis",
                        "path": "/redfish/v1/Chassis/",
                        "status_code": 401,
                        "content_type": "application/json",
                        "classification": "redfish_collection_unauthorized",
                    },
                ],
                "auth_failure_classification": "basic_auth_rejected_or_insufficient_privilege",
                "auth_recovery_hint": "session_auth_may_be_required",
                "next_safe_action": (
                    "Review iLO account permissions or Redfish authentication method. "
                    "No settings were changed."
                ),
            },
            "warnings": [],
            "blockers": [
                "Review iLO account permissions or Redfish authentication method. No settings were changed."
            ],
        },
    )

    response = client.get("/api/v1/providers/ilo-redfish/readiness-summary")

    assert response.status_code == 200
    payload = response.json()
    current_state = payload["current_state"]
    detection = current_state["endpoint_detection"]
    assert current_state["endpoint_classification"] == "redfish_inventory_auth_failed"
    assert current_state["model"] == "ProLiant DL360 Gen10"
    assert current_state["serial"] == "SERIAL-REDACTED"
    assert current_state["current_firmware"] == "2.80"
    assert current_state["ilo_generation"] == "ilo5"
    assert current_state["redfish_root_status"] == "available"
    assert current_state["legacy_endpoint_status"] == "available"
    assert current_state["endpoint_next_safe_action"] == (
        "Review iLO account permissions or Redfish authentication method. No settings were changed."
    )
    assert current_state["redfish_endpoint_detected"] == "redfish_inventory_auth_failed"
    assert detection["inventory_collection_status"] == "unauthorized"
    assert detection["inventory_collection_classification"] == "redfish_collection_unauthorized"
    assert [check["name"] for check in detection["inventory_collection_checks"]] == [
        "Managers",
        "Systems",
        "Chassis",
    ]
    assert detection["auth_failure_classification"] == "basic_auth_rejected_or_insufficient_privilege"
    assert detection["auth_recovery_hint"] == "session_auth_may_be_required"
    assert current_state["endpoint_next_safe_action"] in payload["blockers"]
    clear_probe_results()


def test_ilo_readiness_summary_reports_web_available_redfish_not_found(
    client: TestClient,
) -> None:
    clear_probe_results()
    record_probe_result(
        "ilo-redfish",
        {
            "provider_id": "ilo-redfish",
            "status": "failed",
            "service_root": {},
            "managers": [],
            "systems": [],
            "chassis": [],
            "firmware": [],
            "endpoint_detection": {
                "classification": "web_available_redfish_not_found",
                "message": (
                    "The web root responded, but Redfish root was not found. HTTP web "
                    "reachability alone does not prove this target supports Redfish. Verify "
                    "the address is iLO, check for a legacy iLO generation, confirm Redfish is "
                    "available, and rule out an unrelated web server."
                ),
                "checks": [
                    {
                        "path": "/redfish/v1/",
                        "status_code": 404,
                        "content_type": "text/plain",
                        "classification": "redfish_not_found",
                    },
                    {
                        "path": "/redfish/v1",
                        "status_code": 404,
                        "content_type": "text/plain",
                        "classification": "redfish_not_found",
                    },
                    {
                        "path": "/",
                        "status_code": 200,
                        "content_type": "text/html",
                        "classification": "web_available",
                    },
                    {
                        "path": "/xmldata?item=All",
                        "status_code": 404,
                        "content_type": "text/plain",
                        "classification": "legacy_not_found",
                    },
                ],
                "redfish_status": "not_found",
                "legacy_status": "not_found",
                "web_status": "available",
                "next_safe_action": (
                    "Verify target identity in trusted records or the web UI, confirm iLO "
                    "generation and Redfish support, then retry GET-only endpoint detection. "
                    "No settings were changed."
                ),
                "diagnostic_hints": [
                    "Wrong IP: the responding web server may be a server OS, proxy, or another device.",
                    "Legacy iLO: older generations may not expose Redfish at /redfish/v1.",
                    "Redfish unavailable: the management UI may be reachable while the API is disabled or unsupported.",
                    "Non-iLO web server: the root page responds, but iLO-specific probes did not.",
                    "Keep using GET-only endpoint detection until target identity and Redfish support are confirmed.",
                ],
            },
            "warnings": [],
            "blockers": [
                "Verify target identity in trusted records or the web UI, confirm iLO "
                "generation and Redfish support, then retry GET-only endpoint detection. "
                "No settings were changed."
            ],
        },
    )

    response = client.get("/api/v1/providers/ilo-redfish/readiness-summary")

    assert response.status_code == 200
    payload = response.json()
    current_state = payload["current_state"]
    assert current_state["endpoint_classification"] == "web_available_redfish_not_found"
    assert current_state["redfish_root_status"] == "not_found"
    assert current_state["legacy_endpoint_status"] == "not_found"
    assert current_state["web_endpoint_status"] == "available"
    assert current_state["legacy_endpoint_message"] == (
        "The web root responded, but Redfish root was not found. HTTP web "
        "reachability alone does not prove this target supports Redfish. Verify "
        "the address is iLO, check for a legacy iLO generation, confirm Redfish is "
        "available, and rule out an unrelated web server."
    )
    assert "Verify target identity" in current_state["endpoint_next_safe_action"]
    assert "No settings were changed." in current_state["endpoint_next_safe_action"]
    assert all(
        token not in current_state["endpoint_next_safe_action"].lower()
        for token in ("apply", "write")
    )
    assert "Legacy iLO" in current_state["endpoint_detection"]["diagnostic_hints"][1]
    assert "Non-iLO web server" in current_state["endpoint_detection"]["diagnostic_hints"][3]
    assert current_state["endpoint_detection"]["checks"][0]["path"] == "/redfish/v1/"
    assert current_state["endpoint_detection"]["checks"][1]["path"] == "/redfish/v1"
    assert current_state["endpoint_detection"]["checks"][2]["content_type"] == "text/html"
    assert current_state["endpoint_detection"]["checks"][3]["path"] == "/xmldata?item=All"
    report_statuses = {
        artifact["kind"]: artifact["status"]
        for artifact in payload["reports_artifacts"]
    }
    assert report_statuses["readiness-report"] == "current"
    assert report_statuses["preview-plan"] == "planned"
    clear_probe_results()


def test_ilo_setup_plan_preview_is_plan_only(client: TestClient) -> None:
    clear_probe_results()
    record_probe_result(
        "ilo-redfish",
        {
            "provider_id": "ilo-redfish",
            "status": "ok",
            "service_root": {"@odata.id": "/redfish/v1/"},
            "managers": [{"Name": "HPE iLO 5", "FirmwareVersion": "2.80"}],
            "systems": [{"Model": "ProLiant DL360 Gen10"}],
            "chassis": [],
            "firmware": [],
            "endpoint_detection": {
                "classification": "redfish_available",
                "message": "Redfish root is available. GET-only inventory discovery can continue.",
                "checks": [],
                "redfish_status": "available",
                "legacy_status": "not_checked",
                "web_status": "not_checked",
                "next_safe_action": "Continue with GET-only Redfish inventory discovery. No settings were changed.",
            },
            "warnings": [],
            "blockers": [],
        },
    )

    response = client.get("/api/v1/providers/ilo-redfish/setup-plan-preview")

    assert response.status_code == 200
    payload = response.json()
    section_ids = {section["id"] for section in payload["sections"]}
    assert {
        "network",
        "users",
        "license",
        "snmp",
        "ipv6",
        "time",
        "dns_domain",
        "firmware_readiness",
        "reports_artifacts",
        "destructive_rebuild_handoff",
    } == section_ids
    assert payload["plan_only"] is True
    assert payload["apply_enabled"] is False
    assert payload["firmware_readiness_handoff"]["apply_enabled"] is False
    assert {section["status"] for section in payload["sections"]}.issuperset(
        {"missing_intent", "planned"}
    )
    assert all(not section["apply_enabled"] for section in payload["sections"])
    assert payload["reports_artifacts"]
    assert payload["disabled_dangerous_actions"]
    assert all(not action["enabled"] for action in payload["disabled_dangerous_actions"])
    clear_probe_results()


def test_ilo_destructive_rebuild_preview_is_blocked_handoff(client: TestClient) -> None:
    clear_probe_results()
    record_probe_result(
        "ilo-redfish",
        {
            "provider_id": "ilo-redfish",
            "status": "ok",
            "service_root": {"@odata.id": "/redfish/v1/"},
            "managers": [{"Name": "HPE iLO 5", "FirmwareVersion": "2.80"}],
            "systems": [
                {
                    "Model": "ProLiant DL360 Gen10",
                    "SerialNumber": "SERIAL-REDACTED",
                }
            ],
            "chassis": [],
            "firmware": [],
            "endpoint_detection": {
                "classification": "redfish_available",
                "message": "Redfish root is available. GET-only inventory discovery can continue.",
                "checks": [],
                "redfish_status": "available",
                "legacy_status": "not_checked",
                "web_status": "not_checked",
                "next_safe_action": "Continue with GET-only Redfish inventory discovery. No settings were changed.",
            },
            "warnings": [],
            "blockers": [],
        },
    )

    response = client.get("/api/v1/providers/ilo-redfish/destructive-rebuild-preview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked_out_of_scope"
    assert payload["destructive_enabled"] is False
    assert payload["apply_enabled"] is False
    assert "dedicated bare-metal rebuild workflow" in payload["safe_next_action"]
    assert payload["target_identity"]["identity_verified"] is True
    assert payload["target_identity"]["serial_present"] is True
    assert "SERIAL-REDACTED" not in response.text
    assert "wipe existing drives" in payload["intended_scope"]
    assert "create new RAID/logical drives" in payload["intended_scope"]
    assert "install ESXi" in payload["intended_scope"]
    assert payload["confirmation_requirements"]["operator_phrase"] == "DESTROY AND REBUILD"
    assert any(
        requirement["id"] == "dedicated_workflow"
        and requirement["status"] == "blocked"
        for requirement in payload["required_capabilities"]
    )
    assert any(
        requirement["id"] == "verified_ilo_identity"
        and requirement["status"] == "satisfied"
        for requirement in payload["required_capabilities"]
    )
    lanes = {lane["id"]: lane for lane in payload["real_change_lanes"]}
    assert set(lanes) == {
        "authenticated_inventory_reads",
        "ilo_settings_writes",
        "firmware_updates",
        "storage_raid_changes",
        "esxi_install",
    }
    assert all(lane["execution_enabled"] is False for lane in lanes.values())
    assert lanes["authenticated_inventory_reads"]["status"] == "ready_to_plan"
    assert lanes["ilo_settings_writes"]["status"] == "blocked"
    assert "users" in lanes["ilo_settings_writes"]["blocked_actions"]
    assert "drive wipe" in lanes["storage_raid_changes"]["blocked_actions"]
    assert "ESXi install" in lanes["esxi_install"]["blocked_actions"]
    assert payload["blockers"]
    clear_probe_results()


def test_ilo_setup_intent_can_be_saved_and_feeds_preview(client: TestClient) -> None:
    response = client.put(
        "/api/v1/providers/ilo-redfish/setup-intent",
        json={
            "network": {
                "dhcp_enabled": False,
                "hostname": "ilo-lab-target",
                "management_ip": "planned-management-ip",
                "subnet_mask_or_prefix": "planned-prefix",
                "gateway": "planned-gateway",
                "vlan": "planned-vlan",
            },
            "users": [
                {
                    "password_ref_label": "breakglass-password-ref",
                    "role": "administrator",
                    "username_label": "breakglass-admin",
                }
            ],
            "license": {
                "advanced_license_key_ref": "ilo-advanced-license-ref",
                "expected_status": "iLO Advanced OK",
            },
            "snmp": {
                "enabled": True,
                "version": "v3",
                "system_location": "X666",
                "system_contact": "Operations",
                "system_role": "iLO Admin Server",
                "destinations": ["monitoring-placeholder"],
                "community_or_user_ref_labels": ["snmp-reference-label"],
                "snmpv3_security_name": "monitor",
                "snmpv3_auth_protocol": "MD5",
                "snmpv3_auth_passphrase_ref": "snmp-auth-ref",
                "snmpv3_privacy_protocol": "DES",
                "snmpv3_privacy_passphrase_ref": "snmp-privacy-ref",
            },
            "ipv6": {
                "disable_all": True,
                "disable_dhcpv6_dns_server": True,
                "disable_dhcpv6_domain_name": True,
                "disable_dhcpv6_sntp_settings": True,
                "disable_dhcpv6_stateful_mode": True,
                "disable_dhcpv6_stateless_mode": True,
            },
            "time": {
                "use_dhcp_supplied_time_settings": False,
                "timezone": "UTC",
                "ntp_servers": ["ntp-placeholder"],
                "interface_type": "iLO Dedicated Network Port",
            },
            "dns_domain": {
                "domain_name": "lab.example",
                "dns_servers": ["dns-placeholder"],
            },
            "notes": "save only",
        },
    )

    assert response.status_code == 200
    intent = response.json()
    assert intent["provider_id"] == "ilo-redfish"
    assert intent["apply_enabled"] is False
    assert intent["network"]["dhcp_enabled"] is False
    assert intent["users"][0]["username_label"] == "breakglass-admin"
    assert intent["license"]["advanced_license_key_ref"] == "ilo-advanced-license-ref"
    assert intent["snmp"]["system_location"] == "X666"
    assert intent["snmp"]["snmpv3_security_name"] == "monitor"
    assert intent["ipv6"]["disable_all"] is True
    assert intent["time"]["use_dhcp_supplied_time_settings"] is False

    read_response = client.get("/api/v1/providers/ilo-redfish/setup-intent")
    assert read_response.status_code == 200
    assert read_response.json()["network"]["hostname"] == "ilo-lab-target"

    preview_response = client.get("/api/v1/providers/ilo-redfish/setup-plan-preview")
    assert preview_response.status_code == 200
    sections = {section["id"]: section for section in preview_response.json()["sections"]}
    assert sections["network"]["status"] in {"planned", "warning"}
    assert sections["users"]["status"] == "planned"
    assert sections["license"]["status"] == "planned"
    assert sections["snmp"]["status"] == "planned"
    assert sections["ipv6"]["status"] == "planned"
    assert sections["time"]["status"] == "planned"
    assert sections["dns_domain"]["status"] == "planned"
    assert all(not section["apply_enabled"] for section in sections.values())


def test_ilo_setup_intent_rejects_secret_like_values(client: TestClient) -> None:
    response = client.put(
        "/api/v1/providers/ilo-redfish/setup-intent",
        json={
            "snmp": {
                "enabled": True,
                "destinations": ["monitoring-placeholder"],
                "community_or_user_ref_labels": ["password=not-allowed"],
            }
        },
    )

    assert response.status_code == 422


def test_hpe_storage_discovery_without_cached_probe_is_blocked(
    client: TestClient,
) -> None:
    clear_probe_results()

    response = client.get("/api/v1/providers/ilo-redfish/hpe-storage-discovery")

    assert response.status_code == 200
    payload = response.json()
    assert payload["storage_inventory_available"] is False
    assert payload["controllers"] == []
    assert payload["blockers"]
    assert "GET-only probe" in payload["next_safe_action"]


def test_hpe_raid_intent_feeds_plan_preview(client: TestClient) -> None:
    clear_probe_results()
    record_probe_result(
        "ilo-redfish",
        {
            "provider_id": "ilo-redfish",
            "status": "ok",
            "systems": [
                {
                    "Model": "ProLiant DL360 Gen10",
                    "PowerState": "On",
                    "Status": {"Health": "Warning"},
                    "serial_number_present": True,
                }
            ],
            "storage": {
                "status": "ok",
                "controllers": [
                    {
                        "Id": "controller-1",
                        "Name": "HPE Smart Array P408i-a SR Gen10",
                        "Status": {"Health": "OK"},
                    }
                ],
                "physical_drives": [
                    {
                        "Id": f"drive-{bay}",
                        "Name": f"Drive {bay}",
                        "Bay": bay,
                        "CapacityBytes": 1200 * 1000 * 1000 * 1000,
                        "MediaType": "HDD",
                        "InterfaceType": "SAS",
                        "Status": {"Health": "OK"},
                    }
                    for bay in range(1, 9)
                ],
                "logical_drives": [
                    {
                        "Id": "logical-1",
                        "LogicalDriveName": "OS",
                        "LogicalDriveNumber": 1,
                        "RAIDType": "RAID1",
                        "CapacityMiB": 1140000,
                        "Status": {"Health": "OK"},
                    }
                ],
                "warnings": [],
            },
            "warnings": [],
            "blockers": [],
        },
    )

    save_response = client.put(
        "/api/v1/providers/ilo-redfish/hpe-raid-intent",
        json={
            "controller_ref": "controller-1",
            "wipe_existing_logical_drives": True,
            "volumes": [
                {
                    "name": "ESXi-OS",
                    "purpose": "ESXi install",
                    "raid_level": "RAID1",
                    "drive_bays": ["1", "2"],
                    "size_policy": "max",
                    "bootable": True,
                },
                {
                    "name": "VM-Datastore",
                    "purpose": "VM datastore",
                    "raid_level": "RAID6",
                    "drive_bays": ["3", "4", "5", "6", "7", "8"],
                    "size_policy": "max",
                    "bootable": False,
                },
            ],
            "notes": "plan only",
        },
    )

    assert save_response.status_code == 200
    intent = save_response.json()
    assert intent["apply_enabled"] is False
    assert intent["volumes"][0]["drive_bays"] == ["1", "2"]

    discovery_response = client.get("/api/v1/providers/ilo-redfish/hpe-storage-discovery")
    assert discovery_response.status_code == 200
    discovery = discovery_response.json()
    assert discovery["storage_inventory_available"] is True
    assert discovery["physical_drives"][0]["bay_id"] == "1"

    preview_response = client.get("/api/v1/providers/ilo-redfish/hpe-raid-plan-preview")
    assert preview_response.status_code == 200
    preview = preview_response.json()
    assert preview["apply_enabled"] is False
    assert preview["destructive_actions_requested"] is True
    assert preview["destructive_actions_enabled"] is False
    assert preview["impact"]["logical_drives_to_delete"] == 1
    assert preview["planned_layout"]["volume_count"] == 2
    assert any("RAID" in action for action in preview["disabled_actions"])


def test_hpe_local_storage_recommends_simple_two_drive_layout(client: TestClient) -> None:
    clear_probe_results()
    record_probe_result("ilo-redfish", _storage_probe_with_drives(2))

    response = client.get("/api/v1/providers/ilo-redfish/hpe-raid-plan-preview")

    assert response.status_code == 200
    readiness = response.json()["local_storage_readiness"]
    assert readiness["status"] == "recommendation"
    assert readiness["facts"]["usable_drive_count"] == 2
    assert readiness["candidate_volumes"] == [
        {
            "name": "ESXi-local",
            "purpose": "ESXi boot and local datastore",
            "raid_level": "RAID1",
            "drive_bays": ["1", "2"],
            "spare_bays": [],
            "size_policy": "max",
            "bootable": True,
        }
    ]


def test_hpe_local_storage_recommends_os_and_datastore_for_larger_servers(client: TestClient) -> None:
    clear_probe_results()
    record_probe_result("ilo-redfish", _storage_probe_with_drives(8))

    response = client.get("/api/v1/providers/ilo-redfish/hpe-raid-plan-preview")

    assert response.status_code == 200
    readiness = response.json()["local_storage_readiness"]
    assert readiness["status"] == "recommendation"
    assert readiness["facts"]["usable_drive_count"] == 8
    assert readiness["candidate_volumes"][0]["raid_level"] == "RAID1"
    assert readiness["candidate_volumes"][0]["drive_bays"] == ["1", "2"]
    assert readiness["candidate_volumes"][1]["raid_level"] == "RAID6"
    assert readiness["candidate_volumes"][1]["drive_bays"] == ["3", "4", "5", "6", "7", "8"]


def test_hpe_local_storage_warns_and_uses_largest_matching_drive_group(client: TestClient) -> None:
    clear_probe_results()
    probe = _storage_probe_with_drives(6)
    probe["storage"]["physical_drives"][4]["CapacityBytes"] = 600 * 1000 * 1000 * 1000
    probe["storage"]["physical_drives"][5]["MediaType"] = "SSD"
    record_probe_result("ilo-redfish", probe)

    response = client.get("/api/v1/providers/ilo-redfish/hpe-raid-plan-preview")

    assert response.status_code == 200
    readiness = response.json()["local_storage_readiness"]
    assert readiness["status"] == "recommendation"
    assert readiness["facts"]["usable_drive_count"] == 4
    assert readiness["candidate_layout"]["selected_drive_bays"] == ["1", "2", "3", "4"]
    assert any("Mixed drive media or capacity" in warning for warning in readiness["warnings"])


def test_hpe_local_storage_blocks_failed_drives(client: TestClient) -> None:
    clear_probe_results()
    probe = _storage_probe_with_drives(4)
    probe["storage"]["physical_drives"][2]["Status"] = {"Health": "Critical"}
    record_probe_result("ilo-redfish", probe)

    response = client.get("/api/v1/providers/ilo-redfish/hpe-raid-plan-preview")

    assert response.status_code == 200
    readiness = response.json()["local_storage_readiness"]
    assert readiness["status"] == "blocked"
    assert any("Drive health needs review" in blocker for blocker in readiness["blockers"])


def test_hpe_raid_apply_plan_is_gated(client: TestClient) -> None:
    response = client.get("/api/v1/providers/ilo-redfish/hpe-raid-apply-plan")

    assert response.status_code == 200
    payload = response.json()
    assert payload["apply_enabled"] is False
    assert payload["confirmation_phrase"] == "APPLY HPE RAID PLAN"
    assert payload["apply_mechanism"] == "redfish-smartstorageconfig-settings"
    assert payload["last_apply"]["status"] in {"never", "blocked", "failed", "succeeded"}
    assert payload["blockers"]


def test_hpe_raid_intent_rejects_secret_like_values(client: TestClient) -> None:
    response = client.put(
        "/api/v1/providers/ilo-redfish/hpe-raid-intent",
        json={
            "controller_ref": "controller-1",
            "volumes": [
                {
                    "name": "password=not-allowed",
                    "purpose": "ESXi install",
                    "raid_level": "RAID1",
                    "drive_bays": ["1", "2"],
                }
            ],
        },
    )

    assert response.status_code == 422


def _storage_probe_with_drives(count: int) -> dict[str, Any]:
    return {
        "provider_id": "ilo-redfish",
        "status": "ok",
        "systems": [
            {
                "Model": "Generic rack server",
                "PowerState": "On",
                "Status": {"Health": "OK"},
                "serial_number_present": True,
            }
        ],
        "storage": {
            "status": "ok",
            "controllers": [
                {
                    "Id": "controller-1",
                    "Name": "Generic RAID Controller",
                    "Status": {"Health": "OK"},
                }
            ],
            "physical_drives": [
                {
                    "Id": f"drive-{bay}",
                    "Name": f"Drive {bay}",
                    "Bay": bay,
                    "CapacityBytes": 1200 * 1000 * 1000 * 1000,
                    "MediaType": "HDD",
                    "InterfaceType": "SAS",
                    "Status": {"Health": "OK"},
                }
                for bay in range(1, count + 1)
            ],
            "logical_drives": [],
            "warnings": [],
        },
        "warnings": [],
        "blockers": [],
    }


def test_ilo_setup_compare_empty_intent_reports_missing_and_unknown(
    client: TestClient,
) -> None:
    clear_probe_results()

    response = client.get("/api/v1/providers/ilo-redfish/setup-compare")

    assert response.status_code == 200
    payload = response.json()
    sections = {section["id"]: section for section in payload["sections"]}
    assert payload["apply_enabled"] is False
    assert sections["network"]["status"] == "desired_missing"
    assert sections["users"]["status"] == "desired_missing"
    assert sections["snmp"]["status"] == "desired_missing"
    assert sections["time"]["status"] == "desired_missing"
    assert sections["dns_domain"]["status"] == "desired_missing"
    assert sections["firmware"]["status"] == "discovered_unknown"
    assert all(not row["apply_enabled"] for section in sections.values() for row in section["rows"])
    assert all(not action["enabled"] for action in payload["disabled_dangerous_actions"])


def test_ilo_setup_compare_saved_intent_reports_discovered_unknown(
    client: TestClient,
) -> None:
    clear_probe_results()
    client.put(
        "/api/v1/providers/ilo-redfish/setup-intent",
        json={
            "network": {
                "hostname": "ilo-lab-target",
                "management_ip": "planned-management-ip",
                "subnet_mask_or_prefix": "planned-prefix",
                "gateway": "planned-gateway",
            },
            "users": [{"username_label": "operator-label", "role": "readonly"}],
            "snmp": {
                "enabled": True,
                "destinations": ["monitoring-placeholder"],
                "community_or_user_ref_labels": ["snmp-ref"],
            },
            "time": {"timezone": "UTC", "ntp_servers": ["ntp-placeholder"]},
            "dns_domain": {
                "domain_name": "lab.example",
                "dns_servers": ["dns-placeholder"],
            },
        },
    )

    response = client.get("/api/v1/providers/ilo-redfish/setup-compare")

    assert response.status_code == 200
    sections = {section["id"]: section for section in response.json()["sections"]}
    assert sections["network"]["status"] == "discovered_unknown"
    assert sections["users"]["status"] == "discovered_unknown"
    assert sections["snmp"]["status"] == "discovered_unknown"
    assert sections["time"]["status"] == "discovered_unknown"
    assert sections["dns_domain"]["status"] == "discovered_unknown"
    network_ip = next(row for row in sections["network"]["rows"] if row["field"] == "management_ip")
    assert network_ip["desired"] == "configured"
    assert network_ip["discovered"] == "unknown"


def test_ilo_setup_compare_cached_discovery_reports_firmware_context(
    client: TestClient,
) -> None:
    clear_probe_results()
    record_probe_result(
        "ilo-redfish",
        {
            "provider_id": "ilo-redfish",
            "status": "ok",
            "service_root": {"@odata.id": "/redfish/v1/"},
            "managers": [{"Name": "HPE iLO 5", "FirmwareVersion": "2.80"}],
            "systems": [{"Model": "ProLiant DL360 Gen10"}],
            "chassis": [],
            "firmware": [],
            "warnings": [],
            "blockers": [],
        },
    )

    response = client.get("/api/v1/providers/ilo-redfish/setup-compare")

    assert response.status_code == 200
    firmware = {section["id"]: section for section in response.json()["sections"]}["firmware"]
    assert firmware["status"] == "not_comparable"
    current = next(row for row in firmware["rows"] if row["field"] == "current_firmware")
    assert current["discovered"] == "2.80"
    assert current["desired"] == "no firmware apply intent"
    assert current["apply_enabled"] is False
    clear_probe_results()


def test_ilo_setup_compare_unknown_discovery_is_not_mismatch(client: TestClient) -> None:
    clear_probe_results()
    response = client.get("/api/v1/providers/ilo-redfish/setup-compare")

    assert response.status_code == 200
    statuses = {
        row["status"]
        for section in response.json()["sections"]
        for row in section["rows"]
    }
    assert "mismatch" not in statuses
    assert "discovered_unknown" in statuses


def test_ilo_setup_compare_network_identity_reports_match_and_mismatch(
    client: TestClient,
) -> None:
    clear_probe_results()
    client.put(
        "/api/v1/providers/ilo-redfish/setup-intent",
        json={
            "network": {
                "dhcp_enabled": False,
                "hostname": "ilo-lab-target",
                "management_ip": "192.168.1.201",
                "subnet_mask_or_prefix": "255.255.255.0",
                "gateway": "192.168.1.1",
                "vlan": "10",
            },
        },
    )
    record_probe_result(
        "ilo-redfish",
        {
            "provider_id": "ilo-redfish",
            "status": "ok",
            "network_identity": {
                "status": "ok",
                "dns_name": "ilo-lab-target",
                "ip_address": "192.168.1.11",
                "subnet_mask": "255.255.255.0",
                "gateway": "192.168.1.1",
                "dhcp_enabled": False,
                "vlan_enabled": True,
                "vlan_id": 20,
            },
            "warnings": [],
            "blockers": [],
        },
    )

    response = client.get("/api/v1/providers/ilo-redfish/setup-compare")

    assert response.status_code == 200
    network = {section["id"]: section for section in response.json()["sections"]}["network"]
    rows = {row["field"]: row for row in network["rows"]}

    assert rows["dhcp_enabled"]["status"] == "match"
    assert rows["dhcp_enabled"]["discovered"] == "disabled"

    assert rows["hostname"]["status"] == "match"
    assert rows["hostname"]["desired"] == "configured"
    assert rows["hostname"]["discovered"] == "matches saved intent"

    assert rows["management_ip"]["status"] == "mismatch"
    assert rows["management_ip"]["desired"] == "configured"
    assert rows["management_ip"]["discovered"] == "differs from saved intent"
    assert "192.168.1.11" not in response.text
    assert "192.168.1.201" not in response.text

    assert rows["subnet_mask_or_prefix"]["status"] == "match"
    assert rows["gateway"]["status"] == "match"

    assert rows["vlan"]["status"] == "mismatch"
    assert rows["vlan"]["discovered"] == "20"

    assert network["status"] == "mismatch"
    clear_probe_results()


def test_ilo_setup_compare_license_status_reports_match(client: TestClient) -> None:
    clear_probe_results()
    client.put(
        "/api/v1/providers/ilo-redfish/setup-intent",
        json={"license": {"expected_status": "Enabled"}},
    )
    record_probe_result(
        "ilo-redfish",
        {
            "provider_id": "ilo-redfish",
            "status": "ok",
            "licenses": [
                {"name": "iLO Advanced", "product_type": "Perpetual", "status_state": "Enabled"}
            ],
            "warnings": [],
            "blockers": [],
        },
    )

    response = client.get("/api/v1/providers/ilo-redfish/setup-compare")

    assert response.status_code == 200
    license_section = {
        section["id"]: section for section in response.json()["sections"]
    }["license"]
    status_row = next(
        row for row in license_section["rows"] if row["field"] == "expected_status"
    )
    assert status_row["status"] == "match"
    assert status_row["discovered"] == "Enabled"
    clear_probe_results()


def test_ilo_setup_compare_time_and_dns_reports_match_and_mismatch(
    client: TestClient,
) -> None:
    clear_probe_results()
    client.put(
        "/api/v1/providers/ilo-redfish/setup-intent",
        json={
            "time": {"timezone": "UTC", "ntp_servers": ["ntp1.lab.example", "ntp2.lab.example"]},
            "dns_domain": {
                "domain_name": "lab.example",
                "dns_servers": ["10.0.0.53"],
            },
        },
    )
    record_probe_result(
        "ilo-redfish",
        {
            "provider_id": "ilo-redfish",
            "status": "ok",
            "time_and_dns": {
                "status": "ok",
                "timezone": "UTC",
                "ntp_servers": ["ntp2.lab.example", "ntp1.lab.example"],
                "ntp_protocol_enabled": True,
                "domain_name": "example.com",
                "dns_servers": ["10.0.0.53"],
            },
            "warnings": [],
            "blockers": [],
        },
    )

    response = client.get("/api/v1/providers/ilo-redfish/setup-compare")

    assert response.status_code == 200
    sections = {section["id"]: section for section in response.json()["sections"]}
    time_section = sections["time"]
    dns_section = sections["dns_domain"]
    time_rows = {row["field"]: row for row in time_section["rows"]}
    dns_rows = {row["field"]: row for row in dns_section["rows"]}

    assert time_rows["timezone"]["status"] == "match"
    assert time_rows["timezone"]["discovered"] == "UTC"

    assert time_rows["ntp_servers"]["status"] == "match"
    assert time_rows["ntp_servers"]["desired"] == "configured"
    assert time_rows["ntp_servers"]["discovered"] == "matches saved intent"

    assert dns_rows["domain_name"]["status"] == "mismatch"
    assert dns_rows["domain_name"]["discovered"] == "differs from saved intent"
    assert "example.com" not in response.text
    assert "lab.example" not in response.text

    assert dns_rows["dns_servers"]["status"] == "match"
    clear_probe_results()


def test_ilo_report_preview_empty_intent(client: TestClient) -> None:
    clear_probe_results()

    response = client.get("/api/v1/providers/ilo-redfish/report-preview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "ilo-redfish"
    assert payload["apply_enabled"] is False
    assert payload["desired_setup_intent"]["network"]["management_ip"] == "missing"
    assert payload["setup_compare_report"]["apply_enabled"] is False
    assert payload["destructive_rebuild_preview"]["apply_enabled"] is False
    assert payload["destructive_rebuild_preview"]["destructive_enabled"] is False
    assert payload["destructive_rebuild_preview"]["status"] == "blocked_out_of_scope"
    assert payload["media_inventory_summary"]["mode"] == "sample"
    assert all(not action["enabled"] for action in payload["disabled_dangerous_actions"])


def test_ilo_report_preview_saved_intent_is_redacted(client: TestClient) -> None:
    client.put(
        "/api/v1/providers/ilo-redfish/setup-intent",
        json={
            "network": {
                "hostname": "ilo-lab-target",
                "management_ip": "planned-management-ip",
                "subnet_mask_or_prefix": "planned-prefix",
                "gateway": "planned-gateway",
                "vlan": "planned-vlan",
            },
            "users": [
                {
                    "password_ref_label": "operator-password-ref",
                    "role": "administrator",
                    "username_label": "operator-label",
                }
            ],
            "license": {
                "advanced_license_key_ref": "ilo-advanced-license-ref",
                "expected_status": "iLO Advanced OK",
            },
            "snmp": {
                "enabled": True,
                "version": "v3",
                "system_location": "X666",
                "system_contact": "Operations",
                "system_role": "iLO Admin Server",
                "destinations": ["monitoring-placeholder"],
                "community_or_user_ref_labels": ["snmp-ref"],
                "snmpv3_security_name": "monitor",
                "snmpv3_auth_passphrase_ref": "snmp-auth-ref",
                "snmpv3_privacy_passphrase_ref": "snmp-privacy-ref",
            },
            "time": {"timezone": "UTC", "ntp_servers": ["ntp-placeholder"]},
            "dns_domain": {
                "domain_name": "lab.example",
                "dns_servers": ["dns-placeholder"],
            },
            "notes": "local note",
        },
    )

    response = client.get("/api/v1/providers/ilo-redfish/report-preview")

    assert response.status_code == 200
    encoded = response.text
    assert "planned-management-ip" not in encoded
    assert "planned-gateway" not in encoded
    assert "operator-label" not in encoded
    assert "operator-password-ref" not in encoded
    assert "ilo-advanced-license-ref" not in encoded
    assert "snmp-ref" not in encoded
    assert "snmp-auth-ref" not in encoded
    assert "snmp-privacy-ref" not in encoded
    payload = response.json()
    assert payload["desired_setup_intent"]["network"]["management_ip"] == "configured"
    assert payload["desired_setup_intent"]["users"]["desired_local_username_labels"] == "configured:1"
    assert payload["desired_setup_intent"]["users"]["password_reference_labels"] == "configured:1"
    assert payload["desired_setup_intent"]["license"]["advanced_license_key_ref"] == "configured"
    assert payload["desired_setup_intent"]["snmp"]["community_or_user_ref_labels"] == "configured:1"
    assert payload["desired_setup_intent"]["snmp"]["snmpv3_auth_passphrase_ref"] == "configured"


def test_ilo_report_preview_cached_discovery(client: TestClient) -> None:
    clear_probe_results()
    record_probe_result(
        "ilo-redfish",
        {
            "provider_id": "ilo-redfish",
            "status": "ok",
            "service_root": {"@odata.id": "/redfish/v1/"},
            "managers": [{"Name": "HPE iLO 5", "FirmwareVersion": "2.80"}],
            "systems": [
                {
                    "Model": "ProLiant DL360 Gen10",
                    "SerialNumber": "SERIAL-REDACTED",
                }
            ],
            "chassis": [],
            "firmware": [],
            "warnings": [],
            "blockers": [],
        },
    )

    response = client.get("/api/v1/providers/ilo-redfish/report-preview")

    assert response.status_code == 200
    payload = response.json()
    current_state = payload["readiness_summary"]["current_state"]
    assert current_state["current_firmware"] == "2.80"
    assert current_state["ilo_generation"] == "ilo5"
    assert current_state["serial_present"] is True
    assert current_state["endpoint_classification"] == "redfish_available"
    assert current_state["redfish_root_status"] == "available"
    assert "SERIAL-REDACTED" not in response.text
    assert payload["destructive_rebuild_preview"]["target_identity"]["identity_verified"] is True
    assert payload["destructive_rebuild_preview"]["target_identity"]["serial_present"] is True
    assert all(
        lane["execution_enabled"] is False
        for lane in payload["destructive_rebuild_preview"]["real_change_lanes"]
    )
    clear_probe_results()


def test_ilo_report_preview_redacts_secret_like_persisted_values(
    client: TestClient,
    db_session,
) -> None:
    db_session.add(
        IloSetupIntent(
            provider_id="ilo-redfish",
            intent_json={
                "network": {"management_ip": "secret=do-not-print"},
                "users": [{"username_label": "token=do-not-print", "role": "administrator"}],
                "snmp": {
                    "enabled": True,
                    "destinations": ["password=do-not-print"],
                    "community_or_user_ref_labels": ["bearer do-not-print"],
                },
                "time": {},
                "dns_domain": {},
                "notes": "private_key do-not-print",
            },
        )
    )
    db_session.commit()

    response = client.get("/api/v1/providers/ilo-redfish/report-preview")

    assert response.status_code == 200
    encoded = response.text.lower()
    assert "do-not-print" not in encoded
    assert "secret=" not in encoded
    assert "token=" not in encoded
    assert "password=" not in encoded
    assert "bearer " not in encoded
