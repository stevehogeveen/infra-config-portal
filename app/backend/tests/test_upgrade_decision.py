from __future__ import annotations

from fastapi.testclient import TestClient

from app.models import IloSetupIntent
from app.providers.probe_cache import clear_probe_results, record_probe_result
from app.schemas import UpgradeCandidateRead, UpgradeRuleRead, UpgradeSubjectRead
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
                "message": "iLO web endpoint is reachable, but Redfish root was not found.",
                "checks": [
                    {
                        "path": "/redfish/v1/",
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
                ],
                "redfish_status": "not_found",
                "legacy_status": "not_found",
                "web_status": "available",
                "next_safe_action": "Verify iLO generation, firmware, and Redfish support for this target.",
            },
            "warnings": [],
            "blockers": ["Verify iLO generation, firmware, and Redfish support for this target."],
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
        "iLO web endpoint is reachable, but Redfish root was not found."
    )
    assert "Verify iLO generation" in current_state["endpoint_next_safe_action"]
    assert current_state["endpoint_detection"]["checks"][0]["path"] == "/redfish/v1/"
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
        "snmp",
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
    assert payload["blockers"]
    clear_probe_results()


def test_ilo_setup_intent_can_be_saved_and_feeds_preview(client: TestClient) -> None:
    response = client.put(
        "/api/v1/providers/ilo-redfish/setup-intent",
        json={
            "network": {
                "hostname": "ilo-lab-target",
                "management_ip": "planned-management-ip",
                "subnet_mask_or_prefix": "planned-prefix",
                "gateway": "planned-gateway",
                "vlan": "planned-vlan",
            },
            "users": [{"username_label": "breakglass-admin", "role": "administrator"}],
            "snmp": {
                "enabled": True,
                "destinations": ["monitoring-placeholder"],
                "community_or_user_ref_labels": ["snmp-reference-label"],
            },
            "time": {
                "timezone": "UTC",
                "ntp_servers": ["ntp-placeholder"],
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
    assert intent["users"][0]["username_label"] == "breakglass-admin"

    read_response = client.get("/api/v1/providers/ilo-redfish/setup-intent")
    assert read_response.status_code == 200
    assert read_response.json()["network"]["hostname"] == "ilo-lab-target"

    preview_response = client.get("/api/v1/providers/ilo-redfish/setup-plan-preview")
    assert preview_response.status_code == 200
    sections = {section["id"]: section for section in preview_response.json()["sections"]}
    assert sections["network"]["status"] in {"planned", "warning"}
    assert sections["users"]["status"] == "planned"
    assert sections["snmp"]["status"] == "planned"
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
            "users": [{"username_label": "operator-label", "role": "administrator"}],
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
            "notes": "local note",
        },
    )

    response = client.get("/api/v1/providers/ilo-redfish/report-preview")

    assert response.status_code == 200
    encoded = response.text
    assert "planned-management-ip" not in encoded
    assert "planned-gateway" not in encoded
    assert "operator-label" not in encoded
    assert "snmp-ref" not in encoded
    payload = response.json()
    assert payload["desired_setup_intent"]["network"]["management_ip"] == "configured"
    assert payload["desired_setup_intent"]["users"]["desired_local_username_labels"] == "configured:1"
    assert payload["desired_setup_intent"]["snmp"]["community_or_user_ref_labels"] == "configured:1"


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
    assert payload["destructive_rebuild_preview"]["target_identity"]["serial_present"] is True
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
