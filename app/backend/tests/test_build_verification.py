from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from app.core.config import settings
from app.services import build_verification as build_verification_service
from app.services.build_verification import (
    build_toolchain_availability,
    build_lab_build_verification,
    find_stale_lab_ip_assumptions,
    protocol_readiness,
    validate_credential_compatibility,
    validate_mtu_consistency,
)
from app.services.lab_profiles import create_lab_profile


def test_credential_escaping_accepts_special_characters() -> None:
    result = validate_credential_compatibility("test", "P@ss word:'${value}'")

    assert result["status"] == "ready"
    assert result["classification"] == "passed"
    assert result["special_characters_present"] is True
    assert result["shell"]["safe_with_quoting"] is True
    assert result["json"]["serializable"] is True
    assert result["yaml"]["safe_when_quoted"] is True
    assert result["ansible"]["use_no_log"] is True


def test_credential_escaping_blocks_newline() -> None:
    result = validate_credential_compatibility("test", "bad\nvalue")

    assert result["status"] == "blocked"
    assert result["classification"] == "hard_fail"
    assert result["field"] == "TEST_PASSWORD"
    assert result["issues"]


def test_mtu_validation_reports_path_mismatch() -> None:
    result = validate_mtu_consistency(
        {
            "cisco_iscsi": 9000,
            "esxi_iscsi": 1500,
            "netapp_iscsi": 9000,
        }
    )

    assert result["status"] == "blocked"
    assert result["classification"] == "hard_fail"
    assert result["mismatches"][0]["group"] == "iscsi"


def test_protocol_readiness_reports_unreachable_port() -> None:
    result = protocol_readiness("Cisco SSH/SCP", configured=True, reachable=False)

    assert result["status"] == "blocked"
    assert result["classification"] == "hard_fail"
    assert "required port is not reachable" in result["blockers"][0]


def test_optional_protocol_readiness_skips_unconfigured_provider() -> None:
    result = protocol_readiness("NetApp REST", configured=False, reachable=None, required=False)

    assert result["status"] == "skipped"
    assert result["classification"] == "not_configured_yet"
    assert result["blockers"] == []


def test_protocol_readiness_can_be_blocked_by_prior_stage() -> None:
    result = protocol_readiness(
        "Cisco SSH/SCP",
        configured=True,
        reachable=None,
        classification="blocked_by_prior_stage",
        next_action="Complete Cisco console bootstrap first.",
    )

    assert result["classification"] == "blocked_by_prior_stage"
    assert result["next_action"] == "Complete Cisco console bootstrap first."


def test_stale_lab_ip_assumptions_are_flagged() -> None:
    result = find_stale_lab_ip_assumptions(
        {
            "cisco_management": "10.10.8.112",
            "ilo": "192.168.1.201",
        }
    )

    assert result == [{"field": "cisco_management", "value": "10.10.8.112"}]


def test_build_verification_failure_reporting(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    monkeypatch.setattr("app.services.build_verification._reachable", lambda host, port, check_ports: False if host else None)
    result = build_lab_build_verification(check_ports=True)

    assert result["provider_id"] == "build-verification"
    assert result["status"] in {"blocked", "warning", "completed"}
    assert "failures" in result
    assert result["lab_ip_profile"]["expected"]["cisco_management"] == "192.168.1.204"
    assert result["lab_ip_profile"]["expected"]["ansible_control_host"] == "192.168.1.205"
    assert result["lab_ip_profile"]["expected"]["netapp_controller_a_sp"] == "192.168.1.210"
    assert result["lab_ip_profile"]["expected"]["netapp_cluster_mgmt"] == "192.168.1.220"
    assert result["lab_ip_profile"]["expected"]["netapp_iscsi_lifs"] == (
        "192.168.1.240,192.168.1.241,192.168.1.242,192.168.1.243"
    )
    assert result["artifacts"]["report"] == "artifacts/codex-runs/build-verification-report.md"
    assert result["artifacts"]["lab_ip_profile_report"] == "artifacts/codex-runs/lab-ip-profile-update-report.md"
    assert result["artifacts"]["lab_ip_profile_hardening_report"] == "artifacts/codex-runs/lab-ip-profile-hardening-report.md"
    assert result["artifacts"]["toolchain_availability_report"] == "artifacts/codex-runs/toolchain-availability-report.md"
    assert result["toolchain"]["provider_id"] == "toolchain-readiness"
    assert all(item.get("source_type") for item in result["protocols"]["checks"])
    assert {item["classification"] for item in result["failures"]} & {
        "hard_fail",
        "blocked_by_prior_stage",
        "operator_action_required",
        "not_configured_yet",
    }


def test_build_verification_compact_profile_marks_netapp_vcenter_not_in_scope(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    create_lab_profile(
        {
            "name": "Compact Edge Lab",
            "subnet_cidr": "10.10.5.0/26",
            "address_plan": {"subnet": "10.10.5.0/26"},
        }
    )
    monkeypatch.setattr(
        "app.services.build_verification.settings",
        replace(settings, netapp_configured=False, vcenter_configured=False),
    )
    monkeypatch.setattr("app.services.build_verification._reachable", lambda host, port, check_ports: False if host else None)

    result = build_lab_build_verification(check_ports=True)
    protocols = {item["protocol"]: item for item in result["protocols"]["checks"]}

    assert result["lab_ip_profile"]["active_lab_profile"]["topology"] == "compact_edge_lab"
    assert result["lab_ip_profile"]["expected"]["netapp_cluster_mgmt"] == "not_in_scope"
    assert protocols["NetApp REST"]["classification"] == "not_in_scope"
    assert protocols["NetApp SSH"]["classification"] == "not_in_scope"
    assert protocols["NetApp NFS/vCenter"]["classification"] == "not_in_scope"
    assert not any(item["classification"] == "not_in_scope" for item in result["failures"])


def test_build_verification_reports_exact_fix_for_out_of_scope_env_override(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    monkeypatch.setenv("NETAPP_CLUSTER_MGMT_IP", "192.168.1.220")
    create_lab_profile(
        {
            "name": "Compact Edge Lab",
            "subnet_cidr": "10.10.5.0/26",
            "address_plan": {"subnet": "10.10.5.0/26"},
        }
    )

    result = build_lab_build_verification(check_ports=False)
    mismatches = {item["env_field"]: item for item in result["lab_ip_profile"]["mismatches"]}

    assert mismatches["NETAPP_CLUSTER_MGMT_IP"]["expected"] == "not_in_scope"
    assert mismatches["NETAPP_CLUSTER_MGMT_IP"]["configured"] == "192.168.1.220"
    assert "Unset NETAPP_CLUSTER_MGMT_IP" in mismatches["NETAPP_CLUSTER_MGMT_IP"]["recommended_action"]


def test_mock_provider_mode_cannot_produce_real_certification(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    live_state = _netapp_live_state(configured=True)
    monkeypatch.setattr(
        "app.services.build_verification.settings",
        replace(
            settings,
            provider_mode="mock",
            cisco_mgmt_configured=True,
            esxi_configured=True,
            netapp_configured=True,
            netapp_api_password="compatible-value",
        ),
    )
    monkeypatch.setattr("app.services.build_verification.read_netapp_live_state", lambda **_kwargs: live_state)
    monkeypatch.setattr("app.services.build_verification.get_netapp_runtime_state", lambda: live_state)
    monkeypatch.setattr("app.services.build_verification._reachable", lambda host, port, check_ports: True if host else None)

    result = build_lab_build_verification(check_ports=True)

    assert result["source_type"] == "test_fixture"
    assert result["certification_state"] == "test_fixture"
    assert result["operator_runtime_mode"] == "dev_test"
    assert result["dev_test_banner"]
    assert any(item["category"] == "runtime-mode" for item in result["failures"])


def test_cached_test_fixture_summary_is_not_current_in_real_runtime(monkeypatch, tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts" / "codex-runs"
    artifact_dir.mkdir(parents=True)
    monkeypatch.setattr(build_verification_service, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(build_verification_service, "REPORT", artifact_dir / "build-verification-report.md")
    monkeypatch.setattr(
        build_verification_service,
        "CURRENT_STATE_REPORT",
        artifact_dir / "build-verification-current-state-report.md",
    )
    monkeypatch.setattr(
        build_verification_service,
        "EVIDENCE_REPORT",
        artifact_dir / "build-verification-evidence-report.md",
    )
    monkeypatch.setattr(
        build_verification_service,
        "SUMMARY",
        artifact_dir / "build-verification-summary-redacted.json",
    )
    monkeypatch.setattr(
        "app.services.build_verification.settings",
        replace(settings, provider_mode="local-lab-readwrite"),
    )
    build_verification_service.SUMMARY.write_text(
        '{"provider_id":"build-verification","provider_mode":"mock","source_type":"test_fixture","status":"blocked"}',
        encoding="utf-8",
    )

    result = build_verification_service.get_lab_build_verification()

    assert result["status"] == "not_run"
    assert result["source_type"] == "not_checked"
    assert result["certification_state"] == "not_checked"
    assert result["blockers"] == []
    assert "historical evidence only" in result["message"]


def test_corrupt_cached_summary_self_heals_to_not_checked(monkeypatch, tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts" / "codex-runs"
    artifact_dir.mkdir(parents=True)
    monkeypatch.setattr(build_verification_service, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(build_verification_service, "REPORT", artifact_dir / "build-verification-report.md")
    monkeypatch.setattr(
        build_verification_service,
        "CURRENT_STATE_REPORT",
        artifact_dir / "build-verification-current-state-report.md",
    )
    monkeypatch.setattr(
        build_verification_service,
        "EVIDENCE_REPORT",
        artifact_dir / "build-verification-evidence-report.md",
    )
    monkeypatch.setattr(
        build_verification_service,
        "SUMMARY",
        artifact_dir / "build-verification-summary-redacted.json",
    )
    build_verification_service.SUMMARY.write_text("{not json", encoding="utf-8")

    result = build_verification_service.get_lab_build_verification()

    assert result["status"] == "not_run"
    assert result["source_type"] == "not_checked"
    assert result["artifacts"]["summary_json"] == "artifacts/codex-runs/build-verification-summary-redacted.json"


def test_build_verification_json_artifact_reader_ignores_bad_shapes(tmp_path) -> None:
    artifact = tmp_path / "artifact.json"

    artifact.write_text("{not-json", encoding="utf-8")
    assert build_verification_service._read_json_artifact(artifact) is None

    artifact.write_text('"not-an-object"', encoding="utf-8")
    assert build_verification_service._read_json_artifact(artifact) is None

    artifact.write_text('{"status": "ready"}', encoding="utf-8")
    assert build_verification_service._read_json_artifact(artifact) == {"status": "ready"}


def test_iso_media_readiness_skips_unreadable_media_directory(monkeypatch, tmp_path) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    monkeypatch.setattr(
        build_verification_service,
        "settings",
        replace(settings, media_inventory_dirs=(str(media_root),)),
    )
    original_exists = Path.exists

    def flaky_exists(path: Path) -> bool:
        if path == media_root:
            raise OSError("locked")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    result = build_verification_service._iso_media_readiness()

    assert result["classification"] == "operator_action_required"
    assert "Place the ESXi ISO" in result["next_action"]


def test_iso_media_readiness_skips_files_that_error(monkeypatch, tmp_path) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    iso = media_root / "VMware-ESXi-8.0.iso"
    iso.write_bytes(b"iso")
    monkeypatch.setattr(
        build_verification_service,
        "settings",
        replace(settings, media_inventory_dirs=(str(media_root),)),
    )
    original_is_file = Path.is_file

    def flaky_is_file(path: Path) -> bool:
        if path == iso:
            raise OSError("gone")
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", flaky_is_file)

    result = build_verification_service._iso_media_readiness()

    assert result["classification"] == "operator_action_required"
    assert "Place the ESXi ISO" in result["next_action"]


def test_iso_media_readiness_skips_recursive_scan_errors(monkeypatch, tmp_path) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    monkeypatch.setattr(
        build_verification_service,
        "settings",
        replace(settings, media_inventory_dirs=(str(media_root),)),
    )
    original_rglob = Path.rglob

    def flaky_rglob(path: Path, pattern: str):  # noqa: ANN202
        if path == media_root:
            raise OSError("recursive scan failed")
        return original_rglob(path, pattern)

    monkeypatch.setattr(Path, "rglob", flaky_rglob)

    result = build_verification_service._iso_media_readiness()

    assert result["classification"] == "operator_action_required"
    assert "Place the ESXi ISO" in result["next_action"]


def test_cisco_console_readiness_bad_artifact_self_heals_with_recovery_message(monkeypatch, tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts" / "codex-runs"
    artifact_dir.mkdir(parents=True)
    monkeypatch.setattr(build_verification_service, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(build_verification_service, "CODEX_RUN_DIR", artifact_dir)
    details = artifact_dir / "cisco-4h-lab-run-details-redacted.json"

    details.write_text("{not-json", encoding="utf-8")
    result = build_verification_service._cisco_console_readiness()

    assert result["classification"] == "operator_action_required"
    assert "Regenerate Cisco console details" in result["next_action"]

    details.write_text('{"stages":{"adapter_discovery":{"status":"ready"},"console_prompt_detection":{"prompt_detected":true}}}', encoding="utf-8")
    result = build_verification_service._cisco_console_readiness()

    assert result["classification"] == "passed"


def test_cisco_console_readiness_accepts_management_ssh_proof(monkeypatch) -> None:
    monkeypatch.setattr(
        build_verification_service,
        "settings",
        replace(settings, cisco_mgmt_configured=True),
    )
    monkeypatch.setattr(
        build_verification_service,
        "get_probe_result",
        lambda _provider_id: (
            {
                "provider_id": "cisco-ansible",
                "status": "ok",
                "fallback": "paramiko",
                "command_results": {"show version": {"version_hint": "17.15.05"}},
            },
            "2026-06-29T00:00:00+00:00",
        ),
    )

    result = build_verification_service._cisco_console_readiness()

    assert result["classification"] == "passed"
    assert result["ios_xe_version"] == "17.15.05"
    assert "management SSH proof passed" in result["next_action"]


def test_license_checks_count_redacted_license_material(monkeypatch, tmp_path) -> None:
    licenses = tmp_path / "netapp-license-keys.txt"
    licenses.write_text(
        "\n".join(
            [
                "license add NETAPP-KEY-ONE",
                "NETAPP-KEY-TWO",
                "NETAPP-KEY-TWO",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        build_verification_service,
        "settings",
        replace(
            settings,
            esxi_license_key="ESXI-KEY",
            vcenter_license_key="VCENTER-KEY",
            netapp_license_keys=(),
            netapp_license_keys_file=str(licenses),
        ),
    )

    result = build_verification_service._license_checks()

    assert result["classification"] == "passed"
    counts = {item["product"]: item["license_count"] for item in result["checks"]}
    assert counts == {"ESXi": 1, "vCenter": 1, "NetApp ONTAP": 2}
    assert all(item["value_redacted"] for item in result["checks"])


def test_cisco_console_readiness_treats_probe_errors_as_missing(monkeypatch, tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts" / "codex-runs"
    artifact_dir.mkdir(parents=True)
    monkeypatch.setattr(build_verification_service, "CODEX_RUN_DIR", artifact_dir)
    details = artifact_dir / "cisco-4h-lab-run-details-redacted.json"
    details.write_text('{"stages":{}}', encoding="utf-8")
    original_exists = Path.exists

    def flaky_exists(path: Path) -> bool:
        if path == details:
            raise OSError("details path unavailable")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    result = build_verification_service._cisco_console_readiness()

    assert result["classification"] == "operator_action_required"
    assert "Run Cisco console discovery" in result["next_action"]


def test_netapp_console_readiness_treats_probe_errors_as_missing(monkeypatch, tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts" / "codex-runs"
    artifact_dir.mkdir(parents=True)
    monkeypatch.setattr(build_verification_service, "CODEX_RUN_DIR", artifact_dir)
    monkeypatch.setattr(
        build_verification_service,
        "active_lab_profile_context",
        lambda: {"enabled_features": {"netapp_enabled": True}},
    )
    monkeypatch.setattr(build_verification_service, "get_netapp_runtime_state", lambda: {"console": {}})
    discovery = artifact_dir / "netapp-console-autodiscovery-redacted.json"
    discovery.write_text('{"status":"ready","selected_port":"COM7"}', encoding="utf-8")
    original_exists = Path.exists

    def flaky_exists(path: Path) -> bool:
        if path == discovery:
            raise OSError("discovery path unavailable")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    result = build_verification_service._netapp_console_readiness()

    assert result["classification"] == "operator_action_required"
    assert "Run NetApp console discovery" in result["next_action"]


def test_netapp_nfs_vcenter_readiness_treats_probe_errors_as_missing(monkeypatch, tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts" / "codex-runs"
    artifact_dir.mkdir(parents=True)
    monkeypatch.setattr(build_verification_service, "CODEX_RUN_DIR", artifact_dir)
    monkeypatch.setattr(
        build_verification_service,
        "active_lab_profile_context",
        lambda: {"enabled_features": {"netapp_enabled": True, "vcenter_enabled": True}},
    )
    monkeypatch.setattr(build_verification_service, "get_netapp_runtime_state", lambda: {"configured": False})
    artifact = artifact_dir / "netapp-nfs-vcenter-readiness-redacted.json"
    artifact.write_text('{"status":"ready"}', encoding="utf-8")
    original_exists = Path.exists

    def flaky_exists(path: Path) -> bool:
        if path == artifact:
            raise OSError("readiness path unavailable")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    result = build_verification_service._netapp_nfs_vcenter_readiness()

    assert result["classification"] == "operator_action_required"
    assert "Run NetApp NFS/vCenter readiness" in result["next_action"]


def test_stale_artifact_evidence_skips_probe_errors(monkeypatch, tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts" / "codex-runs"
    artifact_dir.mkdir(parents=True)
    monkeypatch.setattr(build_verification_service, "CODEX_RUN_DIR", artifact_dir)
    report = artifact_dir / "cisco-bootstrap-apply-report.md"
    report.write_text("stale 10.10.8.112 value", encoding="utf-8")
    original_exists = Path.exists

    def flaky_exists(path: Path) -> bool:
        if path == report:
            raise OSError("report path unavailable")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    assert build_verification_service._stale_artifact_evidence() == []


def test_stale_artifact_evidence_replaces_bad_encoding(monkeypatch, tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts" / "codex-runs"
    artifact_dir.mkdir(parents=True)
    monkeypatch.setattr(build_verification_service, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(build_verification_service, "CODEX_RUN_DIR", artifact_dir)
    report = artifact_dir / "cisco-bootstrap-apply-report.md"
    report.write_bytes(b"stale 10.10.8.112 value\xff")

    evidence = build_verification_service._stale_artifact_evidence()

    assert evidence == [
        {
            "artifact": "artifacts/codex-runs/cisco-bootstrap-apply-report.md",
            "classification": "stale_config",
            "next_action": "Regenerate this report after confirming the 192.168.1.0/24 lab profile.",
        }
    ]


def test_command_path_skips_unavailable_fallback_candidates(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(build_verification_service, "which", lambda _command: None)
    monkeypatch.setattr(build_verification_service.sys, "executable", str(tmp_path / "venv" / "Scripts" / "python.exe"))
    monkeypatch.setattr(build_verification_service, "REPO_ROOT", tmp_path)
    candidate = tmp_path / "venv" / "Scripts" / "missing-tool"
    original_exists = Path.exists

    def flaky_exists(path: Path) -> bool:
        if path == candidate:
            raise OSError("candidate path unavailable")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    assert build_verification_service._command_path("missing-tool") is None


def test_build_verification_summary_writes_atomically(monkeypatch, tmp_path) -> None:
    artifact_dir = tmp_path / "artifacts" / "codex-runs"
    monkeypatch.setattr(build_verification_service, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(build_verification_service, "CODEX_RUN_DIR", artifact_dir)
    monkeypatch.setattr(build_verification_service, "REPORT", artifact_dir / "build-verification-report.md")
    monkeypatch.setattr(
        build_verification_service,
        "CURRENT_STATE_REPORT",
        artifact_dir / "build-verification-current-state-report.md",
    )
    monkeypatch.setattr(
        build_verification_service,
        "EVIDENCE_REPORT",
        artifact_dir / "build-verification-evidence-report.md",
    )
    monkeypatch.setattr(build_verification_service, "LAB_IP_REPORT", artifact_dir / "lab-ip-profile-update-report.md")
    monkeypatch.setattr(
        build_verification_service,
        "LAB_IP_HARDENING_REPORT",
        artifact_dir / "lab-ip-profile-hardening-report.md",
    )
    monkeypatch.setattr(
        build_verification_service,
        "CLASSIFICATION_REPORT",
        artifact_dir / "build-verification-classification-report.md",
    )
    monkeypatch.setattr(
        build_verification_service,
        "FAILURE_CASE_REPORT",
        artifact_dir / "failure-case-hardening-report.md",
    )
    monkeypatch.setattr(
        build_verification_service,
        "TOOLCHAIN_AVAILABILITY_REPORT",
        artifact_dir / "toolchain-availability-report.md",
    )
    monkeypatch.setattr(
        build_verification_service,
        "SUMMARY",
        artifact_dir / "build-verification-summary-redacted.json",
    )
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    monkeypatch.setattr("app.services.build_verification._reachable", lambda host, port, check_ports: None)

    result = build_lab_build_verification(check_ports=False)

    saved = json.loads(build_verification_service.SUMMARY.read_text(encoding="utf-8"))
    assert saved["provider_id"] == result["provider_id"]
    report_paths = [
        build_verification_service.REPORT,
        build_verification_service.CURRENT_STATE_REPORT,
        build_verification_service.EVIDENCE_REPORT,
        build_verification_service.LAB_IP_REPORT,
        build_verification_service.LAB_IP_HARDENING_REPORT,
        build_verification_service.CLASSIFICATION_REPORT,
        build_verification_service.FAILURE_CASE_REPORT,
        build_verification_service.TOOLCHAIN_AVAILABILITY_REPORT,
    ]
    for report_path in report_paths:
        assert report_path.exists()
        assert report_path.read_text(encoding="utf-8").strip()
    assert list(artifact_dir.glob("*.tmp")) == []


def test_build_verification_dedupes_blockers_and_warnings(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(build_verification_service, "CODEX_RUN_DIR", tmp_path / "artifacts" / "codex-runs")
    monkeypatch.setattr(build_verification_service, "write_json_object", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(build_verification_service, "write_text_value", lambda *_args, **_kwargs: None)
    for renderer_name in (
        "_markdown",
        "_current_state_markdown",
        "_evidence_markdown",
        "_lab_ip_markdown",
        "_lab_ip_hardening_markdown",
        "_classification_markdown",
        "_failure_case_markdown",
    ):
        monkeypatch.setattr(build_verification_service, renderer_name, lambda _payload: "redacted report\n")
    monkeypatch.setattr(build_verification_service, "active_lab_profile_context", lambda: {"active_profile": {}})
    monkeypatch.setattr(build_verification_service, "_runtime_mode_guard", lambda: None)
    monkeypatch.setattr(build_verification_service, "_build_verification_source_type", lambda **_kwargs: "live_cached")
    monkeypatch.setattr(
        build_verification_service,
        "_netapp_state_for_verification",
        lambda **_kwargs: {"source": "none"},
    )
    monkeypatch.setattr(build_verification_service, "_credential_checks", lambda *_args, **_kwargs: {"checks": []})
    monkeypatch.setattr(
        build_verification_service,
        "_lab_ip_profile_checks",
        lambda **_kwargs: {"classification": "passed", "next_action": "No lab IP action needed."},
    )
    monkeypatch.setattr(
        build_verification_service,
        "_mtu_checks",
        lambda **_kwargs: {"classification": "passed", "next_action": "No MTU action needed."},
    )
    monkeypatch.setattr(build_verification_service, "_protocol_checks", lambda **_kwargs: {"checks": []})
    monkeypatch.setattr(build_verification_service, "build_toolchain_availability", lambda: {"status": "ready"})
    monkeypatch.setattr(build_verification_service, "_post_build_checklist", lambda _protocols: [])
    monkeypatch.setattr(
        build_verification_service,
        "_failure_classification",
        lambda *_args: [
            {
                "classification": "hard_fail",
                "next_action": "Fix cabling.",
                "source_type": "live_probe",
                "freshness": "current",
            },
            {
                "classification": "hard_fail",
                "next_action": "Fix cabling.",
                "source_type": "live_probe",
                "freshness": "current",
            },
            {
                "classification": "operator_action_required",
                "next_action": "Enter password.",
                "source_type": "live_probe",
                "freshness": "current",
            },
            {
                "classification": "warning",
                "next_action": "Review firmware.",
                "source_type": "live_cached",
                "freshness": "current",
            },
            {
                "classification": "warning",
                "next_action": "Review firmware.",
                "source_type": "live_cached",
                "freshness": "current",
            },
        ],
    )

    result = build_lab_build_verification(check_ports=False)

    assert result["blockers"] == ["Live check: Fix cabling.", "Live check: Enter password."]
    assert result["warnings"] == ["Last live result: Review firmware."]
    assert result["status"] == "blocked"


def test_build_verification_stages_unconfigured_providers(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.build_verification.settings",
        replace(settings, cisco_mgmt_configured=False, esxi_configured=False, netapp_configured=False),
    )
    monkeypatch.setattr("app.services.build_verification._reachable", lambda host, port, check_ports: False if host else None)
    monkeypatch.setattr(
        "app.services.build_verification.get_netapp_runtime_state",
        lambda: _netapp_live_state(configured=False, configured_state="not_detected", source="none", reachable=None),
    )

    result = build_lab_build_verification(check_ports=True)
    protocols = {item["protocol"]: item for item in result["protocols"]["checks"]}

    assert protocols["Cisco SSH/SCP"]["classification"] == "blocked_by_prior_stage"
    assert protocols["ESXi API"]["classification"] == "blocked_by_prior_stage"
    assert protocols["ESXi SSH"]["classification"] == "blocked_by_prior_stage"
    assert protocols["NetApp REST"]["classification"] == "not_configured_yet"
    assert protocols["NetApp SSH"]["classification"] == "not_configured_yet"


def test_build_verification_uses_live_netapp_state_before_env_false(monkeypatch) -> None:
    live_state = _netapp_live_state(configured=True)
    monkeypatch.setattr(
        "app.services.build_verification.settings",
        replace(settings, netapp_configured=False),
    )
    monkeypatch.setattr("app.services.build_verification.read_netapp_live_state", lambda **_kwargs: live_state)
    monkeypatch.setattr("app.services.build_verification.get_netapp_runtime_state", lambda: live_state)
    monkeypatch.setattr("app.services.build_verification._reachable", lambda host, port, check_ports: False if host else None)

    result = build_lab_build_verification(check_ports=True)
    protocols = {item["protocol"]: item for item in result["protocols"]["checks"]}

    assert result["netapp_live_state"]["configured"] is True
    assert protocols["NetApp REST"]["classification"] == "passed"
    assert protocols["NetApp SSH"]["classification"] == "passed"
    assert protocols["NetApp REST"]["manual_env_flag_required"] is False


def test_build_verification_env_true_live_failure_is_stale_config(monkeypatch) -> None:
    live_state = _netapp_live_state(configured=False, configured_state="blocked", reachable=False)
    monkeypatch.setattr(
        "app.services.build_verification.settings",
        replace(settings, netapp_configured=True, netapp_api_password="compatible-value"),
    )
    monkeypatch.setattr("app.services.build_verification.read_netapp_live_state", lambda **_kwargs: live_state)
    monkeypatch.setattr("app.services.build_verification.get_netapp_runtime_state", lambda: live_state)
    monkeypatch.setattr("app.services.build_verification._reachable", lambda host, port, check_ports: False if host else None)

    result = build_lab_build_verification(check_ports=True)
    protocols = {item["protocol"]: item for item in result["protocols"]["checks"]}

    assert protocols["NetApp REST"]["classification"] == "stale_config"
    assert protocols["NetApp SSH"]["classification"] == "stale_config"


def test_build_verification_login_required_is_operator_action(monkeypatch) -> None:
    live_state = _netapp_live_state(configured=False, configured_state="login_required")
    monkeypatch.setattr("app.services.build_verification.read_netapp_live_state", lambda **_kwargs: live_state)
    monkeypatch.setattr("app.services.build_verification.get_netapp_runtime_state", lambda: live_state)

    result = build_lab_build_verification(check_ports=True)
    protocols = {item["protocol"]: item for item in result["protocols"]["checks"]}

    assert protocols["NetApp REST"]["classification"] == "operator_action_required"
    assert protocols["NetApp REST"]["configured"] is False


def test_build_verification_marks_stale_active_ip(monkeypatch) -> None:
    monkeypatch.setenv("CISCO_TARGET_IP", "10.10.8.112")
    monkeypatch.setenv("ESXI_TEST_HOST", "10.10.8.203")

    result = build_lab_build_verification(check_ports=False)

    assert result["lab_ip_profile"]["classification"] == "stale_config"
    stale_fields = {item["field"] for item in result["lab_ip_profile"]["stale_10_10_8_values"]}
    assert {"cisco_management", "esxi_management"} <= stale_fields


def test_build_verification_flags_stale_netapp_raw_env(monkeypatch) -> None:
    monkeypatch.setenv("NETAPP_CLUSTER_MGMT_IP", "10.10.8.45")
    monkeypatch.setattr(
        "app.services.build_verification.settings",
        replace(settings, netapp_cluster_mgmt_ip="192.168.1.220"),
    )

    result = build_lab_build_verification(check_ports=False)

    assert result["lab_ip_profile"]["configured"]["netapp_cluster_mgmt"] == "10.10.8.45"
    stale_fields = {item["field"] for item in result["lab_ip_profile"]["stale_10_10_8_values"]}
    assert "netapp_cluster_mgmt_ip_env" in stale_fields


def test_toolchain_availability_reports_local_checks() -> None:
    result = build_toolchain_availability()
    tool_names = {tool["name"] for tool in result["tools"]}

    assert result["provider_id"] == "toolchain-readiness"
    assert "pyserial" in tool_names
    assert "netmiko" in tool_names
    assert "ansible" in tool_names
    assert "govc" in tool_names
    assert "pyATS/Genie" in tool_names
    assert "NAPALM" not in tool_names
    assert result["artifacts"]["report"] == "artifacts/codex-runs/toolchain-availability-report.md"
    assert "cisco" in result["managed_state"]
    assert result["managed_state"]["cisco"]["primary_tools"] == [
        "local_serial",
        "tcp_console/ser2net",
        "Ansible cisco.ios",
        "Netmiko",
    ]
    assert result["managed_state"]["cisco"]["optional_tools"] == ["pyATS/Genie"]
    assert result["managed_state"]["hpe_ilo"]["primary_tools"] == ["Redfish direct", "HPE iLOrest"]
    assert result["managed_state"]["esxi_vsphere"]["primary_tools"] == ["Kickstart", "govc"]
    assert result["managed_state"]["netapp"]["primary_tools"] == [
        "local serial console",
        "netapp-ontap Python client",
        "ONTAP REST",
        "govc",
    ]


def _netapp_live_state(
    *,
    configured: bool,
    configured_state: str = "configured",
    reachable: bool | None = True,
    source: str | None = None,
) -> dict:
    return {
        "provider_id": "netapp-ontap",
        "device_role": "storage-controller",
        "checked_at": "2026-06-08T12:00:00+00:00",
        "source_type": "live_probe",
        "freshness": "current",
        "is_current": True,
        "is_operator_visible": True,
        "status": "ready" if configured else "blocked",
        "configured": configured,
        "configured_state": configured_state,
        "source": source or ("live_verification" if configured else "console_read_state"),
        "manual_env_flag_required": False,
        "legacy_env": {
            "netapp_configured_env": False,
            "netapp_configured_env_role": "legacy_override_or_desired_flag",
            "manual_state_tracking_required": False,
        },
        "console": {
            "discovered_port": "/dev/ttyUSB0",
            "baud": 115200,
            "confidence": "high",
            "last_seen": "2026-06-08T12:00:00+00:00",
            "source": "autodiscovery",
        },
        "management": {
            "rest_443_reachable": reachable,
            "ssh_22_reachable": reachable,
        },
        "api": {"authenticated": configured},
        "storage": {"protocol": "nfs", "ready": configured},
        "blockers": [] if configured else ["NetApp live validation failed."],
        "next_safe_action": "Manual env flag not required.",
    }
