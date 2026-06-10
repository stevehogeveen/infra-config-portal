from __future__ import annotations

from dataclasses import replace

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
    monkeypatch.setattr(
        "app.services.build_verification.settings",
        replace(settings, cisco_target_ip="10.10.8.112", esxi_test_host="10.10.8.203"),
    )

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

    assert result["lab_ip_profile"]["configured"]["netapp_cluster_mgmt"] == "192.168.1.220"
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
