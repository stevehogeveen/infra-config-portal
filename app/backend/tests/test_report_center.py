from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from app.api import routes
from app.services import report_center


def _fresh_checked_at() -> str:
    return datetime.now(UTC).isoformat()


def _build_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider_id": "build-verification",
        "checked_at": _fresh_checked_at(),
        "source_type": "live_probe",
        "status": "blocked",
        "message": "Build Verification completed with redacted findings.",
        "certification_state": "hard_fail",
        "artifacts": {
            "report": "artifacts/codex-runs/build-verification-report.md",
            "summary_json": "artifacts/codex-runs/build-verification-summary-redacted.json",
        },
        "lab_ip_profile": {
            "status": "ready",
            "classification": "passed",
            "active_lab_profile": {
                "name": "Example Lab",
                "source": "saved",
            },
            "mismatches": [],
            "stale_10_10_8_values": [],
            "stale_artifact_evidence": [],
            "next_action": "Lab profile is aligned.",
        },
        "toolchain": {
            "status": "ready",
            "required_missing": [],
            "optional_missing": [],
            "next_safe_action": "Use staged readiness checks.",
        },
        "failures": [],
        "blockers": [],
        "warnings": [],
        "next_safe_action": "Review findings.",
    }
    payload.update(overrides)
    return payload


def test_report_center_aggregates_build_verification_failures(monkeypatch) -> None:
    monkeypatch.setattr(
        report_center,
        "get_lab_build_verification",
        lambda: _build_payload(
            failures=[
                {
                    "category": "protocol",
                    "classification": "hard_fail",
                    "ui_message": "Cisco SSH/SCP is hard_fail.",
                    "report_detail": "Cisco SSH/SCP required port is not reachable.",
                    "next_action": "Complete console bootstrap, then rerun verification.",
                }
            ]
        ),
    )

    payload = report_center.get_report_center(
        source_ids=("build_verification", "lab_profile", "toolchain")
    )

    issue = next(item for item in payload["issues"] if item["source"] == "build_verification")
    assert issue["severity"] == "critical"
    assert issue["classification"] == "hard_fail"
    assert issue["next_action"] == "Complete console bootstrap, then rerun verification."


def test_report_center_firmware_unknown_version_issue_is_warning(monkeypatch) -> None:
    monkeypatch.setattr(
        report_center,
        "get_firmware_compliance",
        lambda **_: {
            "provider_id": "firmware-compliance",
            "checked_at": _fresh_checked_at(),
            "source_type": "live_probe",
            "status": "blocked",
            "components": [
                {
                    "id": "cisco_ios_xe_version",
                    "device": "Cisco",
                    "label": "Cisco IOS XE version",
                    "status": "blocked",
                    "current_version": None,
                    "required_version": "17.9",
                    "reason": "Current firmware or OS version is unknown.",
                    "next_action": "Run Cisco firmware inventory from console.",
                }
            ],
            "reports": {"compliance": "artifacts/codex-runs/firmware-compliance-report.md"},
        },
    )

    payload = report_center.get_report_center(source_ids=("firmware",))

    issue = payload["issues"][0]
    assert issue["source"] == "firmware"
    assert issue["severity"] == "warning"
    assert issue["classification"] == "warning"


def test_report_center_firmware_observed_below_minimum_stays_critical(monkeypatch) -> None:
    monkeypatch.setattr(
        report_center,
        "get_firmware_compliance",
        lambda **_: {
            "provider_id": "firmware-compliance",
            "checked_at": _fresh_checked_at(),
            "source_type": "live_probe",
            "status": "blocked",
            "components": [
                {
                    "id": "cisco_ios_xe_version",
                    "device": "Cisco",
                    "label": "Cisco IOS XE version",
                    "status": "blocked",
                    "current_version": "16.12.05",
                    "required_version": "17.9",
                    "reason": "Current version 16.12.05 is below minimum 17.9.",
                    "next_action": "Review firmware baseline and live inventory.",
                }
            ],
            "reports": {"compliance": "artifacts/codex-runs/firmware-compliance-report.md"},
        },
    )

    payload = report_center.get_report_center(source_ids=("firmware",))

    issue = payload["issues"][0]
    assert issue["source"] == "firmware"
    assert issue["severity"] == "critical"
    assert issue["classification"] == "hard_fail"


def test_report_center_firmware_path_issue_preserves_upgrade_context(monkeypatch) -> None:
    monkeypatch.setattr(
        report_center,
        "get_firmware_compliance",
        lambda **_: {
            "provider_id": "firmware-compliance",
            "checked_at": _fresh_checked_at(),
            "source_type": "historical_evidence",
            "status": "warning",
            "reports": {"compliance": "artifacts/codex-runs/firmware-compliance-report.md"},
            "upgrade_paths": [
                {
                    "component_id": "hpe_bios_version",
                    "component_label": "HPE BIOS",
                    "device_label": "HPE Server",
                    "current_version": "U32 v3.30",
                    "target_version": None,
                    "path_status": "manual_review",
                    "package_available": False,
                    "package_name": None,
                    "missing_evidence": ["target baseline", "approved HPE baseline"],
                    "next_action": "Record the approved HPE BIOS baseline.",
                    "evidence_artifacts": ["artifacts/codex-runs/firmware-inventory-report.md"],
                    "last_checked": _fresh_checked_at(),
                    "source_type": "historical_evidence",
                    "freshness": "historical",
                }
            ],
        },
    )

    payload = report_center.get_report_center(source_ids=("firmware",))

    issue = payload["issues"][0]
    assert issue["source"] == "firmware"
    assert issue["classification"] == "warning"
    assert "Current U32 v3.30; target manual review; path manual review; package not available." == issue["summary"]
    assert issue["details"]["component_id"] == "hpe_bios_version"
    assert issue["details"]["path_status"] == "manual_review"
    assert issue["details"]["missing_evidence"] == ["target baseline", "approved HPE baseline"]
    assert issue["details"]["where_to_fix"] == "Firmware Upgrades"


def test_report_center_stale_config_includes_fix_details(monkeypatch) -> None:
    monkeypatch.setattr(
        report_center,
        "get_lab_build_verification",
        lambda: _build_payload(
            lab_ip_profile={
                "status": "blocked",
                "classification": "stale_config",
                "active_lab_profile": {
                    "name": "Example Lab",
                    "source": "saved",
                },
                "mismatches": [
                    {
                        "field": "cisco_management",
                        "configured": "198.51.100.20",
                        "expected": "198.51.100.30",
                    }
                ],
                "stale_10_10_8_values": [],
                "stale_artifact_evidence": [],
                "next_action": "Update provider environment inputs to match Example Lab.",
            }
        ),
    )

    payload = report_center.get_report_center(
        source_ids=("build_verification", "lab_profile", "toolchain")
    )

    issue = next(item for item in payload["issues"] if item["source"] == "lab_profile")
    assert issue["severity"] == "critical"
    assert issue["classification"] == "stale_config"
    assert issue["details"]["field"] == "cisco_management"
    assert issue["details"]["current_value"] == "198.51.100.20"
    assert issue["details"]["expected_value"] == "198.51.100.30"
    assert issue["details"]["where_to_fix"] == "Lab Setup"
    assert issue["recheck_command"] == "make provider-lab-build-verification-live"


def test_report_center_not_configured_yet_is_neutral_not_critical(monkeypatch) -> None:
    monkeypatch.setattr(
        report_center,
        "get_firmware_compliance",
        lambda **_: {
            "provider_id": "firmware-compliance",
            "checked_at": _fresh_checked_at(),
            "source_type": "live_probe",
            "status": "warning",
            "components": [
                {
                    "id": "netapp_ontap_version",
                    "device": "NetApp",
                    "label": "ONTAP version",
                    "status": "not_configured_yet",
                    "reason": "NetApp firmware inventory is waiting for live setup validation.",
                    "next_action": "Run NetApp setup validation when ready.",
                }
            ],
            "reports": {"compliance": "artifacts/codex-runs/firmware-compliance-report.md"},
        },
    )

    payload = report_center.get_report_center(source_ids=("firmware",))

    issue = payload["issues"][0]
    assert issue["classification"] == "not_configured_yet"
    assert issue["severity"] == "info"
    assert payload["counts"]["critical"] == 0


def test_report_artifacts_are_evidence_not_main_issue_rows(monkeypatch) -> None:
    monkeypatch.setattr(report_center, "_existing_artifacts", lambda source: [f"artifact-{source}.md"])
    monkeypatch.setattr(
        report_center,
        "get_lab_build_verification",
        lambda: _build_payload(
            status="completed",
            certification_state="certified",
            failures=[],
            artifacts={"report": "artifacts/codex-runs/build-verification-report.md"},
            lab_ip_profile={},
            toolchain={},
        ),
    )

    payload = report_center.get_report_center(source_ids=("build_verification",))

    assert "artifacts/codex-runs/build-verification-report.md" in payload["evidence_artifacts"]
    assert all(issue["source"] != "artifact" for issue in payload["issues"])


def test_report_center_page_badges_map_source_counts(monkeypatch) -> None:
    monkeypatch.setattr(
        report_center,
        "get_lab_build_verification",
        lambda: _build_payload(
            failures=[
                {
                    "category": "protocol",
                    "classification": "hard_fail",
                    "ui_message": "iLO Redfish is blocked.",
                    "report_detail": "iLO required path is blocked.",
                    "next_action": "Rerun iLO reachability.",
                }
            ]
        ),
    )

    payload = report_center.get_report_center(
        source_ids=("build_verification", "lab_profile", "toolchain")
    )

    assert payload["page_badges"]["dashboard"]["critical"] >= 1
    assert payload["page_badges"]["verification"]["status"] == "critical"
    assert payload["page_badges"]["settings"]["status"] in {"critical", "success"}


def test_stale_artifact_is_evidence_not_current_blocker(monkeypatch) -> None:
    monkeypatch.setattr(
        report_center,
        "get_lab_build_verification",
        lambda: _build_payload(
            status="completed",
            certification_state="certified",
            failures=[],
            lab_ip_profile={
                "status": "ready",
                "classification": "passed",
                "active_lab_profile": {"name": "Example Lab", "source": "saved"},
                "mismatches": [],
                "stale_10_10_8_values": [],
                "stale_artifact_evidence": [
                    {
                        "artifact": "artifacts/codex-runs/old-build-verification-report.md",
                        "next_action": "Regenerate evidence.",
                    }
                ],
                "next_action": "Lab profile is aligned.",
            },
            blockers=[],
            warnings=[],
        ),
    )

    payload = report_center.get_report_center(source_ids=("build_verification", "lab_profile"))

    stale_issue = next(item for item in payload["issues"] if item["source_stage"] == "historical-artifact")
    assert stale_issue["source_type"] == "historical_artifact"
    assert stale_issue["severity"] == "warning"
    assert stale_issue["status"] == "stale"
    assert stale_issue not in payload["top_issues"]
    assert payload["counts"]["critical"] == 0


def test_fresh_live_pass_clears_stale_build_blocker(monkeypatch) -> None:
    monkeypatch.setattr(
        report_center,
        "get_lab_build_verification",
        lambda: _build_payload(
            status="completed",
            certification_state="certified",
            failures=[],
            lab_ip_profile={
                "status": "ready",
                "classification": "passed",
                "active_lab_profile": {"name": "Example Lab", "source": "saved"},
                "mismatches": [],
                "stale_10_10_8_values": [],
                "stale_artifact_evidence": [],
                "next_action": "Lab profile is aligned.",
            },
            blockers=[],
            warnings=[],
        ),
    )

    payload = report_center.get_report_center(source_ids=("build_verification", "lab_profile"))

    assert payload["counts"]["critical"] == 0
    assert any(issue["severity"] == "success" for issue in payload["issues"])


def test_cisco_live_configured_result_clears_older_management_blocker(monkeypatch) -> None:
    def read_artifact(path: str) -> dict[str, Any] | None:
        if path == "artifacts/codex-runs/cisco-4h-lab-run-details-redacted.json":
            return {
                "checked_at": _fresh_checked_at(),
                "source_type": "live_probe",
                "status": "ready",
                "blockers": [],
                "warnings": [],
                "stages": {
                    "console_prompt_detection": {"status": "ready", "blockers": [], "warnings": []},
                    "ethernet_management_validation": {"status": "ready", "blockers": [], "warnings": []},
                    "bootstrap_plan": {"status": "ready", "blockers": [], "warnings": []},
                },
            }
        return None

    monkeypatch.setattr(report_center, "_read_json_artifact", read_artifact)
    monkeypatch.setattr(
        report_center,
        "_existing_artifacts",
        lambda source: ["artifacts/codex-runs/cisco-console-ethernet-readiness-report.md"] if source == "cisco" else [],
    )

    payload = report_center.get_report_center(source_ids=("cisco",))

    assert payload["counts"]["critical"] == 0
    assert all("SSH/SCP readiness requires console bootstrap" not in issue["summary"] for issue in payload["issues"])
    assert any(issue["source"] == "cisco" and issue["severity"] == "success" for issue in payload["issues"])


def test_newer_cisco_ssh_scp_reports_supersede_old_management_failures(monkeypatch) -> None:
    def read_artifact(path: str) -> dict[str, Any] | None:
        if path == "artifacts/codex-runs/cisco-4h-lab-run-details-redacted.json":
            return {
                "checked_at": "2026-06-10T22:30:38+00:00",
                "source_type": "live_probe",
                "status": "blocked",
                "blockers": [
                    "SSH TCP/22 to Cisco management IP failed.",
                    "SCP readiness over TCP/22 to Cisco management IP failed.",
                ],
                "warnings": [],
                "stages": {
                    "ethernet_management_validation": {
                        "status": "blocked",
                        "blockers": [
                            "SSH TCP/22 to Cisco management IP failed.",
                            "SCP readiness over TCP/22 to Cisco management IP failed.",
                        ],
                        "warnings": [],
                    }
                },
            }
        return None

    monkeypatch.setattr(report_center, "_read_json_artifact", read_artifact)
    monkeypatch.setattr(report_center, "_existing_artifacts", lambda source: [])
    monkeypatch.setattr(report_center, "_cisco_ssh_scp_validations_newer_than", lambda checked_at: True)

    payload = report_center.get_report_center(source_ids=("cisco",))

    assert payload["counts"]["critical"] == 0
    stale_issue = next(
        issue for issue in payload["issues"] if issue["title"] == "Historical Cisco SSH/SCP failure superseded"
    )
    assert stale_issue["severity"] == "warning"
    assert stale_issue["status"] == "stale"
    assert all(
        not (
            issue["severity"] == "critical"
            and (
                "SSH TCP/22 to Cisco management IP failed." in issue["problem"]
                or "SCP readiness over TCP/22 to Cisco management IP failed." in issue["problem"]
            )
        )
        for issue in payload["issues"]
    )


def test_report_issue_severity_mapping_by_source() -> None:
    fresh_checked_at = _fresh_checked_at()

    live_failure = report_center._issue(
        source="build_verification",
        source_stage="protocol",
        classification="hard_fail",
        title="Live failure",
        summary="Live check failed.",
        problem="Live check failed.",
        next_action="Run live check.",
        last_checked=fresh_checked_at,
        source_type="live_probe",
    )
    stale_evidence = report_center._issue(
        source="build_verification",
        source_stage="protocol",
        classification="hard_fail",
        title="Stale failure",
        summary="Old check failed.",
        problem="Old check failed.",
        next_action="Run live check.",
        last_checked=fresh_checked_at,
        source_type="historical_artifact",
    )
    not_checked = report_center._issue(
        source="build_verification",
        source_stage="protocol",
        classification="hard_fail",
        title="Not checked",
        summary="No live check.",
        problem="No live check.",
        next_action="Run live check.",
        source_type="not_checked",
    )
    live_pass = report_center._issue(
        source="build_verification",
        source_stage="protocol",
        classification="passed",
        title="Live pass",
        summary="Live check passed.",
        problem="No active problem reported.",
        next_action="Keep current.",
        last_checked=fresh_checked_at,
        source_type="live_probe",
    )

    assert live_failure["severity"] == "critical"
    assert stale_evidence["severity"] == "warning"
    assert stale_evidence["status"] == "stale"
    assert not_checked["severity"] == "info"
    assert live_pass["severity"] == "success"


def test_missing_optional_report_does_not_create_critical_failure(monkeypatch) -> None:
    monkeypatch.setattr(report_center, "_read_json_artifact", lambda path: None)
    monkeypatch.setattr(report_center, "_existing_artifacts", lambda source: [])

    payload = report_center.get_report_center(source_ids=("cisco",))

    assert payload["counts"]["critical"] == 0
    assert payload["issues"][0]["classification"] == "not_configured_yet"
    assert payload["issues"][0]["severity"] == "info"


def test_report_center_redacts_secret_like_values(monkeypatch) -> None:
    monkeypatch.setattr(
        report_center,
        "get_lab_build_verification",
        lambda: _build_payload(
            failures=[
                {
                    "category": "credential",
                    "classification": "hard_fail",
                    "ui_message": "Credential compatibility needs attention.",
                    "report_detail": "password=super-secret-value should not be returned.",
                    "next_action": "Fix password=super-secret-value locally.",
                }
            ]
        ),
    )

    payload = report_center.get_report_center(
        source_ids=("build_verification", "lab_profile", "toolchain")
    )

    text = json.dumps(payload)
    assert "super-secret-value" not in text
    assert "REDACTED" in text


def test_reports_issues_endpoint_returns_contract(client: TestClient, monkeypatch) -> None:
    sample = {
        "checked_at": _fresh_checked_at(),
        "overall_status": "warning",
        "counts": {"critical": 0, "warning": 1, "info": 0, "success": 0},
        "classification_counts": {"warning": 1},
        "top_issues": [],
        "issues": [
            {
                "id": "sample",
                "source": "firmware",
                "source_stage": "compliance",
                "severity": "warning",
                "classification": "warning",
                "status": "open",
                "source_type": "live_probe",
                "freshness": "current",
                "ttl_seconds": 86400,
                "stale_after_seconds": 86400,
                "is_current": True,
                "is_operator_visible": True,
                "title": "Sample",
                "summary": "Sample warning",
                "problem": "Sample problem",
                "next_action": "Review sample",
                "recheck_command": "make provider-lab-firmware-compliance",
                "source_report": None,
                "evidence_artifacts": [],
                "linked_page": "/firmware",
                "last_checked": None,
                "can_auto_fix": False,
                "auto_fix_action_id": None,
                "details": {},
            }
        ],
        "sources": [],
        "evidence_artifacts": [],
        "last_reports": {},
        "page_badges": {},
    }
    monkeypatch.setattr(routes, "get_report_center", lambda session: sample)

    response = client.get("/api/v1/reports/issues")

    assert response.status_code == 200
    assert response.json()["issues"][0]["source"] == "firmware"
