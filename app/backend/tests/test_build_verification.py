from __future__ import annotations

from dataclasses import replace

from app.core.config import settings
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


def test_build_verification_failure_reporting(monkeypatch) -> None:
    monkeypatch.setattr("app.services.build_verification._reachable", lambda host, port, check_ports: False if host else None)
    result = build_lab_build_verification(check_ports=True)

    assert result["provider_id"] == "build-verification"
    assert result["status"] in {"blocked", "warning", "completed"}
    assert "failures" in result
    assert result["lab_ip_profile"]["expected"]["cisco_management"] == "192.168.1.204"
    assert result["lab_ip_profile"]["expected"]["ansible_control_host"] == "192.168.1.205"
    assert result["lab_ip_profile"]["expected"]["netapp_controller_a_sp"] == "192.168.1.206"
    assert result["lab_ip_profile"]["expected"]["netapp_cluster_mgmt"] == "192.168.1.208"
    assert result["lab_ip_profile"]["expected"]["netapp_iscsi_lifs"] == (
        "192.168.1.212,192.168.1.213,192.168.1.214,192.168.1.215"
    )
    assert result["artifacts"]["report"] == "artifacts/codex-runs/build-verification-report.md"
    assert result["artifacts"]["lab_ip_profile_report"] == "artifacts/codex-runs/lab-ip-profile-update-report.md"
    assert result["artifacts"]["lab_ip_profile_hardening_report"] == "artifacts/codex-runs/lab-ip-profile-hardening-report.md"
    assert result["artifacts"]["toolchain_availability_report"] == "artifacts/codex-runs/toolchain-availability-report.md"
    assert result["toolchain"]["provider_id"] == "toolchain-readiness"
    assert {item["classification"] for item in result["failures"]} & {
        "hard_fail",
        "blocked_by_prior_stage",
        "operator_action_required",
        "not_configured_yet",
    }


def test_build_verification_stages_unconfigured_providers(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.build_verification.settings",
        replace(settings, cisco_mgmt_configured=False, esxi_configured=False, netapp_configured=False),
    )
    monkeypatch.setattr("app.services.build_verification._reachable", lambda host, port, check_ports: False if host else None)

    result = build_lab_build_verification(check_ports=True)
    protocols = {item["protocol"]: item for item in result["protocols"]["checks"]}

    assert protocols["Cisco SSH/SCP"]["classification"] == "blocked_by_prior_stage"
    assert protocols["ESXi API"]["classification"] == "blocked_by_prior_stage"
    assert protocols["ESXi SSH"]["classification"] == "blocked_by_prior_stage"
    assert protocols["NetApp REST"]["classification"] == "not_configured_yet"
    assert protocols["NetApp SSH"]["classification"] == "not_configured_yet"


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
        replace(settings, netapp_cluster_mgmt_ip="192.168.1.208"),
    )

    result = build_lab_build_verification(check_ports=False)

    assert result["lab_ip_profile"]["configured"]["netapp_cluster_mgmt"] == "192.168.1.208"
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
