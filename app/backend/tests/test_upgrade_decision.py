from __future__ import annotations

from fastapi.testclient import TestClient

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
    assert payload["current_state"]["redfish_endpoint_detected"] == "detected"
    assert payload["current_state"]["legacy_endpoint_status"] == "unknown/not_checked"
    assert payload["current_state"]["media_inventory_mode"] == "sample"
    assert payload["upgrade_decision_status"] == payload["firmware_readiness"]["decision"]["status"]
    assert payload["desired_setup_sections"]
    assert all(section["status"] == "plan_only" for section in payload["desired_setup_sections"])
    assert all(not section["apply_enabled"] for section in payload["desired_setup_sections"])
    assert payload["reports_artifacts"]
    assert payload["disabled_dangerous_actions"]
    assert all(not action["enabled"] for action in payload["disabled_dangerous_actions"])
    clear_probe_results()
