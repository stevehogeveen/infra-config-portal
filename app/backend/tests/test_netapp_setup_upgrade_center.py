from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import httpx

from app.core.config import settings
from app.schemas import MediaInventoryItemRead, MediaInventoryRead
from app.services import (
    netapp_address_plan,
    netapp_factory_reset,
    netapp_iscsi_setup,
    netapp_nfs_setup,
    netapp_real_lab,
    netapp_setup_intent,
    netapp_upgrade_center,
)


def test_setup_preview_detects_cluster_setup_wizard(monkeypatch) -> None:
    _patch_setup_runtime(monkeypatch, detected=True)
    monkeypatch.setattr(
        netapp_setup_intent,
        "scan_planned_netapp_addresses",
        lambda *, enabled: {"status": "not_checked", "free": False, "results": [], "conflicts": []},
    )

    payload = netapp_setup_intent.build_netapp_setup_preview(write_report=False)

    assert payload["detected_state"] == "cluster_setup_wizard"
    assert payload["apply_enabled"] is False
    assert payload["setup_intent"]["cluster_mgmt_ip"] == "192.168.1.220"


def test_setup_apply_refuses_without_flags(monkeypatch) -> None:
    _patch_setup_runtime(monkeypatch, detected=True)
    _patch_setup_settings(monkeypatch)
    monkeypatch.delenv("NETAPP_SETUP_APPLY", raising=False)
    monkeypatch.delenv("NETAPP_SETUP_CONFIRM", raising=False)
    monkeypatch.delenv("NETAPP_SETUP_ALLOW_CLUSTER_CREATE", raising=False)
    monkeypatch.setattr(
        netapp_setup_intent,
        "scan_planned_netapp_addresses",
        lambda *, enabled: {"status": "ready", "free": True, "results": [], "conflicts": []},
    )

    payload = netapp_setup_intent.apply_netapp_setup(write_report=False)

    assert payload["status"] == "blocked"
    assert payload["apply_enabled"] is False
    assert payload["apply"]["serial_writes_attempted"] is False
    assert any("NETAPP_SETUP_APPLY=true" in blocker for blocker in payload["blockers"])
    assert any("NETAPP_SETUP_ALLOW_CLUSTER_CREATE=true" in blocker for blocker in payload["blockers"])


def test_setup_apply_exposes_missing_intent_fields(monkeypatch) -> None:
    _patch_setup_runtime(monkeypatch, detected=False)
    for name in (
        "NETAPP_CONSOLE_USERNAME",
        "NETAPP_CONSOLE_PASSWORD",
        "NETAPP_API_USERNAME",
        "NETAPP_API_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)
    settings_override = replace(
        settings,
        provider_mode="local-lab-readwrite",
        lab_environment="isolated-real-lab",
        lab_acknowledge_real_hardware=True,
        lab_acknowledge_device_reconfiguration=True,
        lab_acknowledge_data_loss_risk=True,
        lab_acknowledge_lab_only=True,
        netapp_cluster_name=None,
        netapp_node_a_name=None,
        netapp_node_b_name=None,
        netapp_svm_name=None,
        netapp_dns_servers=(),
        netapp_ntp_servers=(),
        netapp_search_domains=(),
        netapp_admin_access_source=None,
        netapp_api_username=None,
        netapp_api_password=None,
    )
    monkeypatch.setattr(netapp_setup_intent, "settings", settings_override)
    monkeypatch.setattr(
        netapp_setup_intent,
        "scan_planned_netapp_addresses",
        lambda *, enabled: {"status": "ready", "free": True, "results": [], "conflicts": []},
    )

    payload = netapp_setup_intent.apply_netapp_setup(write_report=False)

    assert "cluster_name" not in payload["missing_fields"]
    assert payload["intent"]["cluster_name"] == "lab-netapp-cluster"
    assert payload["intent"]["node_a_name"] == "lab-netapp-node-a"
    assert payload["intent"]["node_b_name"] == "lab-netapp-node-b"
    assert payload["intent"]["svm_name"] == "esxi_svm"
    assert payload["intent"]["dns_servers"]
    assert payload["intent"]["ntp_servers"]
    assert payload["intent"]["search_domains"] == ["lab.local"]
    assert "admin_access_source" in payload["missing_fields"]
    assert any(item["field_name"] == "admin_access_source" for item in payload["remediation_items"])


def test_setup_intent_string_list_dedupes_and_ignores_junk() -> None:
    assert netapp_setup_intent._string_list(" 192.168.1.1, ,192.168.1.1,192.168.1.2 ") == [
        "192.168.1.1",
        "192.168.1.2",
    ]
    assert netapp_setup_intent._string_list(("lab.local", " lab.local ", "", None, "corp.local")) == [
        "lab.local",
        "corp.local",
    ]
    assert sorted(netapp_setup_intent._string_list({"b.example", "a.example"})) == ["a.example", "b.example"]
    assert netapp_setup_intent._string_list(123) == []


def test_setup_preview_reports_apply_command_and_confirmations(monkeypatch) -> None:
    _patch_setup_runtime(monkeypatch, detected=True)
    _patch_setup_settings(monkeypatch)
    monkeypatch.setattr(
        netapp_setup_intent,
        "scan_planned_netapp_addresses",
        lambda *, enabled: {"status": "ready", "free": True, "results": [], "conflicts": []},
    )

    payload = netapp_setup_intent.build_netapp_setup_preview(write_report=False)

    assert 'NETAPP_SETUP_CONFIRM="APPLY NETAPP CLUSTER SETUP"' in payload["apply_command"]
    assert "NETAPP_SETUP_APPLY=true" in payload["required_flags"]
    assert 'NETAPP_SETUP_CONFIRM="APPLY NETAPP CLUSTER SETUP"' in payload["required_flags"]


def test_address_plan_uses_console_discovered_addresses(monkeypatch, tmp_path) -> None:
    console_json = tmp_path / "netapp-console-login-state-redacted.json"
    console_json.write_text(
        json.dumps(
            {
                "checked_at": "2026-06-13T00:00:00+00:00",
                "identified_state": "ontap_shell",
                "command_results": [
                    {
                        "id": "network_interface_summary",
                        "output_excerpt": "\n".join(
                            [
                                "network interface show -fields vserver,lif,address,role,home-node,home-port,status-admin,status-oper",
                                "vserver lif role address home-node home-port status-oper status-admin",
                                "------- ------------ ------- --------------- --------- --------- ----------- ------------",
                                "X20     X20-01_mgmt1 node-mgmt",
                                "                             10.10.8.46      X20-01    e0M       -           up",
                                "X20     X20-02_mgmt1 node-mgmt",
                                "                             10.10.8.47      X20-02    e0M       up          up",
                                "X20     cluster_mgmt cluster-mgmt",
                                "                             10.10.8.45      X20-01    e0M       up          up",
                                "stage_nfs",
                                "        nfs_lif_01   data    10.10.8.48      X20-01    e0b       up          up",
                            ]
                        ),
                    },
                    {
                        "id": "cluster_status",
                        "output_excerpt": "\n".join(
                            [
                                "cluster show",
                                "Node                  Health  Eligibility",
                                "--------------------- ------- ------------",
                                "X20-01                false   true",
                                "X20-02                true    true",
                                "Warning: Cluster HA is not working correctly.",
                            ]
                        ),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    settings_override = replace(
        settings,
        provider_mode="local-lab-readwrite",
        netapp_cluster_mgmt_ip="192.168.1.220",
        netapp_node_a_mgmt_ip="192.168.1.221",
        netapp_node_b_mgmt_ip="192.168.1.222",
        netapp_svm_mgmt_ip="192.168.1.223",
        netapp_nfs_lifs=("192.168.1.230", "192.168.1.231"),
    )
    monkeypatch.setattr(netapp_address_plan, "settings", settings_override)
    monkeypatch.setattr(netapp_address_plan, "CONSOLE_LOGIN_STATE_JSON", console_json)
    monkeypatch.setattr(
        netapp_address_plan,
        "get_netapp_runtime_state",
        lambda: {
            "configured": False,
            "configured_state": "ontap_detected",
            "source": "console_discovery",
        },
    )

    payload = netapp_address_plan.build_netapp_address_remediation_plan(write_report=False)

    assert payload["current_targets"]["cluster_mgmt"] == "10.10.8.45"
    assert payload["current_targets"]["node_a_mgmt"] == "10.10.8.46"
    assert payload["current_targets"]["node_b_mgmt"] == "10.10.8.47"
    assert payload["current_targets"]["nfs_lifs"] == ["10.10.8.48"]
    assert payload["planned_targets"]["cluster_mgmt"] == "192.168.1.220"
    assert any(item["id"] == "cluster_mgmt" and item["status"] == "mismatch" for item in payload["address_comparisons"])
    assert payload["console_facts"]["cluster_ha_warning"] is True


def test_address_plan_self_heals_corrupt_console_state(monkeypatch, tmp_path) -> None:
    console_json = tmp_path / "netapp-console-login-state-redacted.json"
    console_json.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(netapp_address_plan, "CONSOLE_LOGIN_STATE_JSON", console_json)

    facts = netapp_address_plan.latest_console_network_facts()

    assert facts["identified_state"] == "not_checked"
    assert facts["source"] == "not_available"
    assert any("has not run yet" in blocker for blocker in facts["blockers"])
    assert facts["current_targets"]["cluster_mgmt"] is None


def test_address_plan_ignores_non_object_console_state(monkeypatch, tmp_path) -> None:
    console_json = tmp_path / "netapp-console-login-state-redacted.json"
    console_json.write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setattr(netapp_address_plan, "CONSOLE_LOGIN_STATE_JSON", console_json)

    context = netapp_address_plan._console_context()
    cluster_name = netapp_address_plan._cluster_name_from_console()

    assert context["selected_port"] == netapp_address_plan.settings.netapp_console_port
    assert cluster_name == (netapp_address_plan.settings.netapp_cluster_name or "")


def test_address_comparisons_keep_scalar_nfs_lifs_whole() -> None:
    comparisons = netapp_address_plan._address_comparisons(
        {"nfs_lifs": " 10.10.8.48 "},
        {"nfs_lifs": " 10.10.8.49 "},
    )
    nfs_rows = [row for row in comparisons if row["id"].startswith("nfs_lif_")]

    assert len(nfs_rows) == 1
    assert nfs_rows[0]["current"] == "10.10.8.48"
    assert nfs_rows[0]["planned"] == "10.10.8.49"


def test_address_blockers_keep_scalar_console_blocker_whole() -> None:
    blockers = netapp_address_plan._blockers(
        {
            "identified_state": "ontap_shell",
            "blockers": " Console login state is stale. ",
            "node_health": {"unhealthy_nodes": " node-01 "},
        },
        [],
        {"checks": [{"id": "current_cluster_mgmt", "tcp_443": True, "tcp_22": False}]},
    )

    assert "Console login state is stale." in blockers
    assert not any(blocker == "C" for blocker in blockers)
    assert "NetApp node health is not clean: node-01." in blockers


def test_address_validation_checks_keep_scalar_planned_nfs_lif_whole(monkeypatch) -> None:
    monkeypatch.setattr(netapp_address_plan, "_tcp", lambda *_args: True)

    checks = netapp_address_plan._target_validation_checks(
        {"planned_targets": {"nfs_lifs": " 10.10.8.49 "}}
    )
    nfs_checks = [check for check in checks if check["id"].startswith("nfs_lif_")]

    assert len(nfs_checks) == 1
    assert nfs_checks[0]["address"] == "10.10.8.49"


def test_nfs_setup_preview_blocks_until_cluster_and_access_are_ready(monkeypatch) -> None:
    _patch_nfs_runtime(monkeypatch, configured=False)

    payload = netapp_nfs_setup.build_netapp_nfs_setup_preview(write_report=False)

    assert payload["status"] == "blocked"
    assert payload["apply_enabled"] is False
    assert payload["nfs_plan"]["storage_protocol"] == "nfs"
    assert payload["nfs_plan"]["volume"] == "esxi_datastore_01"
    assert payload["nfs_plan"]["preferred_nfs_lif"] == "192.168.1.230"
    assert any("prior cluster setup" in blocker for blocker in payload["blockers"])
    assert any("iSCSI" in item for item in payload["not_attempted"])


def test_iscsi_setup_preview_surfaces_lif_plan_without_apply(monkeypatch) -> None:
    _patch_iscsi_runtime(monkeypatch, protocol_ready=True)
    settings_override = replace(
        settings,
        netapp_api_username="admin",
        netapp_api_password="configured-value",
        netapp_storage_protocol="iscsi",
        netapp_cluster_mgmt_ip="192.168.1.220",
        netapp_svm_name="esxi_svm",
        netapp_iscsi_lifs=("192.168.1.240", "192.168.1.241"),
    )
    monkeypatch.setattr(netapp_iscsi_setup, "settings", settings_override)
    monkeypatch.setenv("ESXI_ISCSI_INITIATOR_IQNS", "iqn.1998-01.com.vmware:host-a, iqn.1998-01.com.vmware:host-b")

    payload = netapp_iscsi_setup.build_netapp_iscsi_setup_preview(write_report=False)

    assert payload["status"] == "preview_only"
    assert payload["apply_enabled"] is False
    assert payload["iscsi_plan"]["preferred_iscsi_lif"] == "192.168.1.240"
    assert payload["iscsi_plan"]["lun_name"] == "esxi_lun_01"
    assert payload["protocol_readiness"]["ready"] is True
    assert any("LUN" in item for item in payload["not_attempted"])


def test_iscsi_setup_validation_blocks_on_missing_lun_igroup_map(monkeypatch) -> None:
    _patch_iscsi_runtime(monkeypatch, protocol_ready=True)
    settings_override = replace(
        settings,
        netapp_api_username="admin",
        netapp_api_password="configured-value",
        netapp_storage_protocol="iscsi",
        netapp_cluster_mgmt_ip="192.168.1.220",
        netapp_svm_name="esxi_svm",
        netapp_iscsi_lifs=("192.168.1.240", "192.168.1.241"),
    )
    monkeypatch.setattr(netapp_iscsi_setup, "settings", settings_override)
    monkeypatch.setenv("ESXI_ISCSI_INITIATOR_IQNS", "iqn.1998-01.com.vmware:host-a")
    monkeypatch.setattr(netapp_iscsi_setup, "_iscsi_inventory", lambda plan: _missing_iscsi_inventory())

    payload = netapp_iscsi_setup.validate_netapp_iscsi_setup(write_report=False)

    assert payload["status"] == "blocked"
    assert payload["protocol_readiness"]["reachable_lif_count"] == 2
    assert "NetApp iSCSI LUN is missing." in payload["blockers"]
    assert "NetApp iSCSI igroup is missing." in payload["blockers"]
    assert "NetApp iSCSI LUN map is missing." in payload["blockers"]
    assert payload["apply_enabled"] is False
    assert payload["source_type"] == "live_probe"
    assert "artifacts/codex-runs/netapp-iscsi-setup-validation-redacted.json" in payload["report_artifacts"]


def test_iscsi_setup_apply_refuses_without_flags_before_writes(monkeypatch) -> None:
    _patch_iscsi_runtime(monkeypatch, protocol_ready=True)
    settings_override = replace(
        settings,
        provider_mode="local-lab-readwrite",
        lab_environment="isolated-real-lab",
        lab_acknowledge_real_hardware=True,
        lab_acknowledge_device_reconfiguration=True,
        lab_acknowledge_data_loss_risk=True,
        lab_acknowledge_lab_only=True,
        netapp_api_username="admin",
        netapp_api_password="configured-value",
        netapp_storage_protocol="iscsi",
        netapp_cluster_mgmt_ip="192.168.1.220",
        netapp_svm_name="esxi_svm",
        netapp_iscsi_lifs=("192.168.1.240", "192.168.1.241"),
    )
    monkeypatch.setattr(netapp_iscsi_setup, "settings", settings_override)
    monkeypatch.setenv("ESXI_ISCSI_INITIATOR_IQNS", "iqn.1998-01.com.vmware:host-a")
    monkeypatch.delenv("NETAPP_ISCSI_SETUP_APPLY", raising=False)
    monkeypatch.delenv("NETAPP_ISCSI_SETUP_CONFIRM", raising=False)
    monkeypatch.delenv("NETAPP_ISCSI_SETUP_ALLOW_STORAGE_CREATE", raising=False)
    monkeypatch.setattr(netapp_iscsi_setup, "_iscsi_inventory", lambda plan: _missing_iscsi_inventory())

    def fail_if_write_attempted(plan, inventory):  # noqa: ANN001
        raise AssertionError("iSCSI apply attempted ONTAP writes without flags")

    monkeypatch.setattr(netapp_iscsi_setup, "_ensure_iscsi_lun_igroup_map", fail_if_write_attempted)

    payload = netapp_iscsi_setup.apply_netapp_iscsi_setup(write_report=False)

    assert payload["status"] == "blocked"
    assert payload["apply_enabled"] is False
    assert payload["apply"]["ontap_writes_attempted"] is False
    assert "NETAPP_ISCSI_SETUP_APPLY=true is required." in payload["blockers"]
    assert 'NETAPP_ISCSI_SETUP_CONFIRM="APPLY NETAPP ISCSI SETUP" is required.' in payload["blockers"]
    assert "NETAPP_ISCSI_SETUP_ALLOW_STORAGE_CREATE=true is required." in payload["blockers"]


def test_nfs_setup_apply_refuses_without_flags(monkeypatch) -> None:
    _patch_nfs_runtime(monkeypatch, configured=True)
    settings_override = replace(
        settings,
        provider_mode="local-lab-readwrite",
        lab_environment="isolated-real-lab",
        lab_acknowledge_real_hardware=True,
        lab_acknowledge_device_reconfiguration=True,
        lab_acknowledge_data_loss_risk=True,
        lab_acknowledge_lab_only=True,
        netapp_api_username="admin",
        netapp_api_password="configured-value",
    )
    monkeypatch.setattr(netapp_nfs_setup, "settings", settings_override)
    monkeypatch.delenv("NETAPP_NFS_SETUP_APPLY", raising=False)
    monkeypatch.delenv("NETAPP_NFS_SETUP_CONFIRM", raising=False)
    monkeypatch.delenv("NETAPP_NFS_SETUP_ALLOW_STORAGE_CREATE", raising=False)

    payload = netapp_nfs_setup.apply_netapp_nfs_setup(write_report=False)

    assert payload["status"] == "blocked"
    assert payload["apply_enabled"] is False
    assert payload["apply"]["ontap_writes_attempted"] is False
    assert any("NETAPP_NFS_SETUP_APPLY=true" in blocker for blocker in payload["blockers"])
    assert any("NETAPP_NFS_SETUP_ALLOW_STORAGE_CREATE=true" in blocker for blocker in payload["blockers"])


def test_nfs_setup_apply_gates_accept_common_true_like_env_values(monkeypatch) -> None:
    _patch_nfs_runtime(monkeypatch, configured=True)
    settings_override = replace(
        settings,
        provider_mode="local-lab-readwrite",
        lab_environment="isolated-real-lab",
        lab_acknowledge_real_hardware=True,
        lab_acknowledge_device_reconfiguration=True,
        lab_acknowledge_data_loss_risk=True,
        lab_acknowledge_lab_only=True,
        netapp_api_username="admin",
        netapp_api_password="configured-value",
    )
    monkeypatch.setattr(netapp_nfs_setup, "settings", settings_override)
    monkeypatch.setenv("NETAPP_NFS_SETUP_APPLY", " YES ")
    monkeypatch.setenv("NETAPP_NFS_SETUP_CONFIRM", netapp_nfs_setup.NFS_SETUP_CONFIRM_PHRASE)
    monkeypatch.setenv("NETAPP_NFS_SETUP_ALLOW_STORAGE_CREATE", "ON")

    gates = netapp_nfs_setup._apply_gates(
        {"configured": True},
        {"missing_fields": []},
    )

    assert gates["flag_state"]["netapp_nfs_setup_apply"] is True
    assert gates["flag_state"]["netapp_nfs_setup_allow_storage_create"] is True
    assert not any("NETAPP_NFS_SETUP_APPLY=true" in blocker for blocker in gates["blockers"])
    assert not any("NETAPP_NFS_SETUP_ALLOW_STORAGE_CREATE=true" in blocker for blocker in gates["blockers"])


def test_nfs_setup_apply_gates_keep_scalar_policy_blocker_whole(monkeypatch) -> None:
    class ScalarPolicy:
        def action_blockers(self, _action_id, _category):
            return " policy blocker "

    _patch_nfs_runtime(monkeypatch, configured=True)
    settings_override = replace(
        settings,
        provider_mode="local-lab-readwrite",
        lab_environment="isolated-real-lab",
        lab_acknowledge_real_hardware=True,
        lab_acknowledge_device_reconfiguration=True,
        lab_acknowledge_data_loss_risk=True,
        lab_acknowledge_lab_only=True,
        netapp_api_username="admin",
        netapp_api_password="configured-value",
    )
    monkeypatch.setattr(netapp_nfs_setup, "settings", settings_override)
    monkeypatch.setattr(netapp_nfs_setup, "current_lab_action_policy", lambda _mode=None: ScalarPolicy())
    monkeypatch.setenv("NETAPP_NFS_SETUP_APPLY", "true")
    monkeypatch.setenv("NETAPP_NFS_SETUP_CONFIRM", netapp_nfs_setup.NFS_SETUP_CONFIRM_PHRASE)
    monkeypatch.setenv("NETAPP_NFS_SETUP_ALLOW_STORAGE_CREATE", "true")

    gates = netapp_nfs_setup._apply_gates(
        {"configured": True},
        {"missing_fields": []},
    )

    assert gates["blockers"] == ["policy blocker"]
    assert "p" not in gates["blockers"]


def test_nfs_setup_apply_self_heals_scalar_rest_apply_lists(monkeypatch) -> None:
    _patch_nfs_runtime(monkeypatch, configured=True)
    settings_override = replace(
        settings,
        provider_mode="local-lab-readwrite",
        lab_environment="isolated-real-lab",
        lab_acknowledge_real_hardware=True,
        lab_acknowledge_device_reconfiguration=True,
        lab_acknowledge_data_loss_risk=True,
        lab_acknowledge_lab_only=True,
        netapp_storage_protocol="nfs",
        netapp_cluster_mgmt_ip="192.168.1.220",
        netapp_svm_mgmt_ip="192.168.1.221",
        netapp_nfs_lifs=("192.168.1.230", "192.168.1.231"),
        netapp_nfs_volume="esxi_datastore_01",
        netapp_nfs_mount_path="/esxi_datastore_01",
        netapp_nfs_export_policy="esxi_export",
        netapp_nfs_client_match="192.168.1.0/24",
        netapp_nfs_datastore_name="netapp_nfs_ds01",
        netapp_api_username="admin",
        netapp_api_password="configured-value",
    )
    monkeypatch.setattr(netapp_nfs_setup, "settings", settings_override)
    monkeypatch.setenv("NETAPP_NFS_SETUP_APPLY", "true")
    monkeypatch.setenv("NETAPP_NFS_SETUP_CONFIRM", netapp_nfs_setup.NFS_SETUP_CONFIRM_PHRASE)
    monkeypatch.setenv("NETAPP_NFS_SETUP_ALLOW_STORAGE_CREATE", "true")
    monkeypatch.setattr(netapp_nfs_setup, "current_lab_action_policy", lambda _mode=None: _AllowPolicy())
    monkeypatch.setattr(
        netapp_nfs_setup,
        "_ensure_nfs_export_rule",
        lambda _plan: {
            "status": "failed",
            "message": "REST failed.",
            "ontap_writes_attempted": False,
            "transcript_summary": " created export rule ",
            "blockers": " REST failed. ",
        },
    )

    payload = netapp_nfs_setup.apply_netapp_nfs_setup(write_report=False)

    assert payload["apply"]["transcript_summary"] == ["created export rule"]
    assert payload["blockers"] == ["REST failed."]


def test_nfs_setup_not_attempted_tracks_actual_ontap_writes() -> None:
    no_write = netapp_nfs_setup._not_attempted(False)
    write = netapp_nfs_setup._not_attempted(True)

    assert "ONTAP REST write" in no_write
    assert "SVM, LIF, NFS service, volume, export policy, or export rule creation" in no_write
    assert "ONTAP REST write" not in write
    assert "SVM, LIF, NFS service, volume, export policy, or export rule creation" not in write
    assert "ESXi datastore mount" in write


def test_iscsi_setup_not_attempted_tracks_actual_ontap_writes() -> None:
    no_write = netapp_iscsi_setup._not_attempted(False)
    write = netapp_iscsi_setup._not_attempted(True)

    assert "ONTAP REST write" in no_write
    assert "iSCSI service, LIF, LUN, igroup, or initiator creation" in no_write
    assert "ONTAP REST write" not in write
    assert "iSCSI service, LIF, LUN, igroup, or initiator creation" not in write
    assert "VMFS datastore creation or mount" in write


def test_nfs_export_policy_lookup_reports_malformed_json(monkeypatch) -> None:
    def malformed_response(*_args, **_kwargs):
        return httpx.Response(
            200,
            request=httpx.Request("GET", "https://netapp.example/api"),
            headers={"content-type": "application/json"},
            content=b"{not-json",
        )

    monkeypatch.setattr(netapp_nfs_setup, "_ontap_request", malformed_response)

    try:
        netapp_nfs_setup._get_export_policy("esxi_export")
    except ValueError as exc:
        assert "Invalid JSON response" in str(exc)
    else:
        raise AssertionError("expected malformed JSON to be reported as ValueError")


def test_nfs_export_policy_lookup_reports_non_object_json(monkeypatch) -> None:
    def array_response(*_args, **_kwargs):
        return httpx.Response(
            200,
            request=httpx.Request("GET", "https://netapp.example/api"),
            headers={"content-type": "application/json"},
            json=[],
        )

    monkeypatch.setattr(netapp_nfs_setup, "_ontap_request", array_response)

    try:
        netapp_nfs_setup._get_export_policy("esxi_export")
    except ValueError as exc:
        assert "Unexpected JSON response" in str(exc)
    else:
        raise AssertionError("expected non-object JSON to be reported as ValueError")


def test_nfs_setup_validation_self_heals_scalar_readiness_lists(monkeypatch) -> None:
    monkeypatch.setattr(
        netapp_nfs_setup,
        "get_netapp_nfs_vcenter_readiness",
        lambda **_kwargs: {
            "status": "blocked",
            "blockers": " ESXi datastore is missing. ",
            "warnings": " Retry after NetApp returns. ",
        },
    )

    payload = netapp_nfs_setup.validate_netapp_nfs_setup(write_report=False)

    assert payload["status"] == "blocked"
    assert payload["blockers"] == ["ESXi datastore is missing."]
    assert payload["warnings"] == ["Retry after NetApp returns."]


def test_nfs_setup_validation_suppresses_vcenter_warning_for_direct_netapp_profile(monkeypatch) -> None:
    monkeypatch.setattr(
        netapp_nfs_setup,
        "active_lab_profile_context",
        lambda: {"enabled_features": {"netapp_enabled": True, "vcenter_enabled": False}},
    )
    monkeypatch.setattr(
        netapp_nfs_setup,
        "get_netapp_nfs_vcenter_readiness",
        lambda **_kwargs: {
            "status": "not_in_scope",
            "blockers": [],
            "warnings": [
                "NetApp or vCenter is disabled by the active lab profile; this is not a blocker.",
                "Keep this direct warning.",
            ],
        },
    )
    monkeypatch.setattr(
        netapp_nfs_setup,
        "_live_nfs_validation",
        lambda _plan: {"status": "ready", "blockers": [], "warnings": []},
    )

    payload = netapp_nfs_setup.validate_netapp_nfs_setup(write_report=False)

    assert payload["status"] == "ready"
    assert payload["warnings"] == ["Keep this direct warning."]


def test_nfs_setup_report_paths_use_posix_separators(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(netapp_nfs_setup, "REPO_ROOT", tmp_path)

    assert netapp_nfs_setup._rel(tmp_path / "artifacts" / "codex-runs" / "report.md") == "artifacts/codex-runs/report.md"


def test_nfs_setup_preview_writes_json_atomically(monkeypatch, tmp_path: Path) -> None:
    _redirect_nfs_reports(monkeypatch, tmp_path)
    _patch_nfs_runtime(monkeypatch, configured=False)

    payload = netapp_nfs_setup.build_netapp_nfs_setup_preview(write_report=True)

    saved = json.loads(netapp_nfs_setup.NFS_PREVIEW_JSON.read_text(encoding="utf-8"))
    assert saved["action"] == payload["action"]
    assert saved["status"] == "blocked"
    assert netapp_nfs_setup.NFS_PREVIEW_REPORT.read_text(encoding="utf-8").strip()
    assert not list(netapp_nfs_setup.CODEX_RUN_DIR.glob("*.tmp"))


def test_nfs_setup_apply_writes_json_atomically(monkeypatch, tmp_path: Path) -> None:
    _redirect_nfs_reports(monkeypatch, tmp_path)
    _patch_nfs_runtime(monkeypatch, configured=True)
    settings_override = replace(
        settings,
        provider_mode="local-lab-readwrite",
        lab_environment="isolated-real-lab",
        lab_acknowledge_real_hardware=True,
        lab_acknowledge_device_reconfiguration=True,
        lab_acknowledge_data_loss_risk=True,
        lab_acknowledge_lab_only=True,
        netapp_storage_protocol="nfs",
        netapp_cluster_mgmt_ip="192.168.1.220",
        netapp_svm_mgmt_ip="192.168.1.221",
        netapp_nfs_lifs=("192.168.1.230", "192.168.1.231"),
        netapp_nfs_volume="esxi_datastore_01",
        netapp_nfs_mount_path="/esxi_datastore_01",
        netapp_nfs_export_policy="esxi_export",
        netapp_nfs_client_match="192.168.1.0/24",
        netapp_nfs_datastore_name="netapp_nfs_ds01",
        netapp_api_username="admin",
        netapp_api_password="configured-value",
    )
    monkeypatch.setattr(netapp_nfs_setup, "settings", settings_override)
    monkeypatch.delenv("NETAPP_NFS_SETUP_APPLY", raising=False)
    monkeypatch.delenv("NETAPP_NFS_SETUP_CONFIRM", raising=False)
    monkeypatch.delenv("NETAPP_NFS_SETUP_ALLOW_STORAGE_CREATE", raising=False)

    payload = netapp_nfs_setup.apply_netapp_nfs_setup(write_report=True)

    saved = json.loads(netapp_nfs_setup.NFS_APPLY_JSON.read_text(encoding="utf-8"))
    assert saved["action"] == payload["action"]
    assert saved["status"] == "blocked"
    assert netapp_nfs_setup.NFS_APPLY_REPORT.read_text(encoding="utf-8").strip()
    assert not list(netapp_nfs_setup.CODEX_RUN_DIR.glob("*.tmp"))


def test_nfs_setup_validation_writes_json_atomically(monkeypatch, tmp_path: Path) -> None:
    _redirect_nfs_reports(monkeypatch, tmp_path)
    monkeypatch.setattr(
        netapp_nfs_setup,
        "get_netapp_nfs_vcenter_readiness",
        lambda **_kwargs: {
            "status": "ready",
            "blockers": [],
            "warnings": [],
            "planned_nfs": {"svm_name": "esxi_svm", "nfs_lifs": ["192.168.1.230"]},
        },
    )

    payload = netapp_nfs_setup.validate_netapp_nfs_setup(write_report=True)

    saved = json.loads(netapp_nfs_setup.NFS_VALIDATION_JSON.read_text(encoding="utf-8"))
    assert saved["action"] == payload["action"]
    assert saved["status"] == "ready"
    assert netapp_nfs_setup.NFS_VALIDATION_REPORT.read_text(encoding="utf-8").strip()
    assert not list(netapp_nfs_setup.CODEX_RUN_DIR.glob("*.tmp"))


def test_nfs_vcenter_readiness_not_in_scope_writes_report_atomically(monkeypatch, tmp_path: Path) -> None:
    codex_runs = tmp_path / "artifacts" / "codex-runs"
    codex_runs.mkdir(parents=True)
    monkeypatch.setattr(netapp_real_lab, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(netapp_real_lab, "CODEX_RUN_DIR", codex_runs)
    monkeypatch.setattr(netapp_real_lab, "NFS_VCENTER_READINESS_REPORT", codex_runs / "netapp-nfs-vcenter-readiness-report.md")
    monkeypatch.setattr(netapp_real_lab, "NFS_VCENTER_READINESS_JSON", codex_runs / "netapp-nfs-vcenter-readiness-redacted.json")
    monkeypatch.setattr(
        netapp_real_lab,
        "active_lab_profile_context",
        lambda: {
            "enabled_features": {"netapp_enabled": False, "vcenter_enabled": False},
            "resolved_address_plan": {"subnet": "192.168.1.0/24", "esxi_management": "192.168.1.205"},
        },
    )

    payload = netapp_real_lab.get_netapp_nfs_vcenter_readiness(check_ports=False, write_report=True)

    saved = json.loads(netapp_real_lab.NFS_VCENTER_READINESS_JSON.read_text(encoding="utf-8"))
    assert saved["action"] == payload["action"]
    assert payload["status"] == "not_in_scope"
    assert netapp_real_lab.NFS_VCENTER_READINESS_REPORT.read_text(encoding="utf-8").strip()
    assert not list(codex_runs.glob("*.tmp"))


def test_factory_reset_report_paths_use_posix_separators(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(netapp_factory_reset, "REPO_ROOT", tmp_path)

    assert netapp_factory_reset._rel(tmp_path / "artifacts" / "codex-runs" / "report.md") == "artifacts/codex-runs/report.md"


def test_factory_reset_preview_writes_json_atomically(monkeypatch, tmp_path: Path) -> None:
    _redirect_factory_reset_reports(monkeypatch, tmp_path)
    monkeypatch.setattr(netapp_factory_reset, "build_netapp_address_remediation_plan", lambda **_kwargs: _factory_address_plan())

    payload = netapp_factory_reset.build_netapp_factory_reset_preview(write_report=True)

    saved = json.loads(netapp_factory_reset.FACTORY_RESET_PLAN_JSON.read_text(encoding="utf-8"))
    assert saved["action"] == payload["action"]
    assert saved["destructive"] is True
    assert netapp_factory_reset.FACTORY_RESET_PLAN_REPORT.read_text(encoding="utf-8").strip()
    assert not list(netapp_factory_reset.CODEX_RUN_DIR.glob("*.tmp"))


def test_factory_reset_apply_writes_json_atomically(monkeypatch, tmp_path: Path) -> None:
    _redirect_factory_reset_reports(monkeypatch, tmp_path)
    monkeypatch.setattr(netapp_factory_reset, "build_netapp_address_remediation_plan", lambda **_kwargs: _factory_address_plan())
    monkeypatch.delenv("NETAPP_FACTORY_RESET_APPLY", raising=False)
    monkeypatch.delenv("NETAPP_FACTORY_RESET_CONFIRM", raising=False)
    monkeypatch.delenv("NETAPP_FACTORY_RESET_EXECUTOR_ENABLED", raising=False)

    payload = netapp_factory_reset.apply_netapp_factory_reset(write_report=True)

    saved = json.loads(netapp_factory_reset.FACTORY_RESET_APPLY_JSON.read_text(encoding="utf-8"))
    assert saved["action"] == payload["action"]
    assert saved["status"] == "blocked"
    assert netapp_factory_reset.FACTORY_RESET_APPLY_REPORT.read_text(encoding="utf-8").strip()
    assert not list(netapp_factory_reset.CODEX_RUN_DIR.glob("*.tmp"))


def test_factory_reset_apply_gates_accept_common_true_like_env_values(monkeypatch) -> None:
    settings_override = replace(settings, provider_mode="local-lab-readwrite")
    monkeypatch.setattr(netapp_factory_reset, "settings", settings_override)
    monkeypatch.setattr(netapp_factory_reset, "current_lab_action_policy", lambda _mode=None: _AllowPolicy())
    monkeypatch.setenv("NETAPP_FACTORY_RESET_APPLY", " YES ")
    monkeypatch.setenv("NETAPP_FACTORY_RESET_CONFIRM", netapp_factory_reset.FACTORY_RESET_CONFIRM_PHRASE)
    monkeypatch.setenv("NETAPP_FACTORY_RESET_EXECUTOR_ENABLED", "ON")

    gates = netapp_factory_reset._apply_gates()

    assert gates["blockers"] == []
    assert gates["flag_state"]["netapp_factory_reset_apply"] is True
    assert gates["flag_state"]["netapp_factory_reset_executor_enabled"] is True


def test_factory_reset_apply_gates_keep_scalar_policy_blocker_whole(monkeypatch) -> None:
    class ScalarPolicy:
        allow_factory_reset = True

        def action_blockers(self, _action_id, _category):
            return " policy blocker "

    settings_override = replace(settings, provider_mode="local-lab-readwrite")
    monkeypatch.setattr(netapp_factory_reset, "settings", settings_override)
    monkeypatch.setattr(netapp_factory_reset, "current_lab_action_policy", lambda _mode=None: ScalarPolicy())
    monkeypatch.setenv("NETAPP_FACTORY_RESET_APPLY", "true")
    monkeypatch.setenv("NETAPP_FACTORY_RESET_CONFIRM", netapp_factory_reset.FACTORY_RESET_CONFIRM_PHRASE)
    monkeypatch.setenv("NETAPP_FACTORY_RESET_EXECUTOR_ENABLED", "true")

    gates = netapp_factory_reset._apply_gates()

    assert gates["blockers"] == ["policy blocker"]
    assert "p" not in gates["blockers"]


def test_factory_reset_validation_writes_json_atomically(monkeypatch, tmp_path: Path) -> None:
    _redirect_factory_reset_reports(monkeypatch, tmp_path)
    monkeypatch.setattr(
        netapp_factory_reset,
        "build_netapp_address_remediation_plan",
        lambda **_kwargs: {
            **_factory_address_plan(),
            "console_facts": {"identified_state": "cluster_setup_wizard"},
        },
    )

    payload = netapp_factory_reset.validate_netapp_factory_reset(write_report=True)

    saved = json.loads(netapp_factory_reset.FACTORY_RESET_VALIDATION_JSON.read_text(encoding="utf-8"))
    assert saved["action"] == payload["action"]
    assert saved["status"] == "ready"
    assert netapp_factory_reset.FACTORY_RESET_VALIDATION_REPORT.read_text(encoding="utf-8").strip()
    assert not list(netapp_factory_reset.CODEX_RUN_DIR.glob("*.tmp"))


def test_setup_report_paths_use_posix_separators(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(netapp_setup_intent, "REPO_ROOT", tmp_path)

    assert netapp_setup_intent._rel(tmp_path / "artifacts" / "codex-runs" / "report.md") == "artifacts/codex-runs/report.md"


def test_setup_existing_reports_skips_paths_that_error(monkeypatch) -> None:
    class ReportPath:
        def __init__(self, *, exists: bool = True, exists_error: Exception | None = None) -> None:
            self._exists = exists
            self._exists_error = exists_error

        def exists(self) -> bool:
            if self._exists_error:
                raise self._exists_error
            return self._exists

    class RepoRoot:
        def __truediv__(self, path: str) -> ReportPath:
            return reports[path]

    reports = {
        "artifacts/ready.md": ReportPath(),
        "artifacts/locked.md": ReportPath(exists_error=OSError("locked")),
        "artifacts/missing.md": ReportPath(exists=False),
    }
    monkeypatch.setattr(netapp_setup_intent, "REPO_ROOT", RepoRoot())

    assert netapp_setup_intent._existing_reports(list(reports)) == ["artifacts/ready.md"]


def test_setup_preview_writes_json_atomically(monkeypatch, tmp_path: Path) -> None:
    _redirect_setup_reports(monkeypatch, tmp_path)
    _patch_setup_runtime(monkeypatch, detected=True)
    _patch_setup_settings(monkeypatch)
    monkeypatch.setattr(
        netapp_setup_intent,
        "scan_planned_netapp_addresses",
        lambda *, enabled: {"status": "ready", "free": True, "results": [], "conflicts": []},
    )

    payload = netapp_setup_intent.build_netapp_setup_preview(write_report=True)

    saved = json.loads(netapp_setup_intent.SETUP_PREVIEW_JSON.read_text(encoding="utf-8"))
    assert saved["action"] == payload["action"]
    assert netapp_setup_intent.SETUP_PREVIEW_REPORT.read_text(encoding="utf-8").strip()
    assert not list(netapp_setup_intent.CODEX_RUN_DIR.glob("*.tmp"))


def test_setup_baseline_writes_report_atomically(monkeypatch, tmp_path: Path) -> None:
    _redirect_setup_reports(monkeypatch, tmp_path)
    _patch_setup_runtime(monkeypatch, detected=True)
    _patch_setup_settings(monkeypatch)
    monkeypatch.setattr(
        netapp_setup_intent,
        "scan_planned_netapp_addresses",
        lambda *, enabled: {"status": "ready", "free": True, "results": [], "conflicts": []},
    )

    payload = netapp_setup_intent.build_netapp_setup_baseline(write_report=True)

    assert payload["action"] == "setup-upgrade-baseline"
    assert netapp_setup_intent.BASELINE_REPORT.read_text(encoding="utf-8").strip()
    assert not list(netapp_setup_intent.CODEX_RUN_DIR.glob("*.tmp"))


def test_setup_apply_writes_json_atomically(monkeypatch, tmp_path: Path) -> None:
    _redirect_setup_reports(monkeypatch, tmp_path)
    _patch_setup_runtime(monkeypatch, detected=True)
    _patch_setup_settings(monkeypatch)
    monkeypatch.delenv("NETAPP_SETUP_APPLY", raising=False)
    monkeypatch.delenv("NETAPP_SETUP_CONFIRM", raising=False)
    monkeypatch.delenv("NETAPP_SETUP_ALLOW_CLUSTER_CREATE", raising=False)
    monkeypatch.setattr(
        netapp_setup_intent,
        "scan_planned_netapp_addresses",
        lambda *, enabled: {"status": "ready", "free": True, "results": [], "conflicts": []},
    )

    payload = netapp_setup_intent.apply_netapp_setup(write_report=True)

    saved = json.loads(netapp_setup_intent.SETUP_APPLY_JSON.read_text(encoding="utf-8"))
    assert saved["action"] == payload["action"]
    assert saved["status"] == "blocked"
    assert netapp_setup_intent.SETUP_APPLY_REPORT.read_text(encoding="utf-8").strip()
    assert not list(netapp_setup_intent.CODEX_RUN_DIR.glob("*.tmp"))


def test_setup_apply_gates_accept_common_true_like_env_values(monkeypatch) -> None:
    _patch_setup_settings(monkeypatch)
    monkeypatch.setenv("NETAPP_SETUP_APPLY", " YES ")
    monkeypatch.setenv("NETAPP_SETUP_CONFIRM", netapp_setup_intent.SETUP_CONFIRM_PHRASE)
    monkeypatch.setenv("NETAPP_SETUP_ALLOW_CLUSTER_CREATE", "TRUE")

    gates = netapp_setup_intent._setup_apply_gates(
        "cluster_setup_wizard",
        {"missing_fields": []},
        {"free": True},
    )

    assert gates["flag_state"]["netapp_setup_apply"] is True
    assert gates["flag_state"]["netapp_setup_allow_cluster_create"] is True
    assert not any("NETAPP_SETUP_APPLY=true" in blocker for blocker in gates["blockers"])
    assert not any("NETAPP_SETUP_ALLOW_CLUSTER_CREATE=true" in blocker for blocker in gates["blockers"])


def test_setup_apply_gates_keep_scalar_policy_blocker_whole(monkeypatch) -> None:
    class ScalarPolicy:
        def action_blockers(self, _action_id, _category):
            return " policy blocker "

    _patch_setup_settings(monkeypatch)
    monkeypatch.setattr(netapp_setup_intent, "current_lab_action_policy", lambda _mode: ScalarPolicy())
    monkeypatch.setenv("NETAPP_SETUP_APPLY", "true")
    monkeypatch.setenv("NETAPP_SETUP_CONFIRM", netapp_setup_intent.SETUP_CONFIRM_PHRASE)
    monkeypatch.setenv("NETAPP_SETUP_ALLOW_CLUSTER_CREATE", "true")

    gates = netapp_setup_intent._setup_apply_gates(
        "cluster_setup_wizard",
        {"missing_fields": []},
        {"free": True},
    )

    assert gates["blockers"] == ["policy blocker"]
    assert "p" not in gates["blockers"]


def test_post_setup_validation_writes_json_atomically(monkeypatch, tmp_path: Path) -> None:
    _redirect_setup_reports(monkeypatch, tmp_path)
    monkeypatch.setattr(netapp_setup_intent, "_netapp_in_scope", lambda: True)
    monkeypatch.setattr(
        netapp_setup_intent,
        "validate_netapp_setup",
        lambda **_kwargs: {
            "provider_id": "netapp-ontap",
            "status": "ready",
            "message": "Validated.",
            "blockers": [],
            "warnings": [],
            "artifacts": {},
        },
    )

    payload = netapp_setup_intent.run_netapp_post_setup_validation(write_report=True)

    saved = json.loads(netapp_setup_intent.POST_SETUP_VALIDATION_JSON.read_text(encoding="utf-8"))
    assert saved["action"] == payload["action"]
    assert saved["status"] == "ready"
    assert netapp_setup_intent.POST_SETUP_VALIDATION_REPORT.read_text(encoding="utf-8").strip()
    assert not list(netapp_setup_intent.CODEX_RUN_DIR.glob("*.tmp"))


def test_address_plan_report_paths_use_posix_separators(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(netapp_address_plan, "REPO_ROOT", tmp_path)

    assert netapp_address_plan._rel(tmp_path / "artifacts" / "codex-runs" / "report.md") == "artifacts/codex-runs/report.md"


def test_address_apply_gates_accept_common_true_like_env_values(monkeypatch) -> None:
    settings_override = replace(
        settings,
        provider_mode="local-lab-readwrite",
        netapp_api_username="admin",
        netapp_api_password="configured-value",
    )
    monkeypatch.setattr(netapp_address_plan, "settings", settings_override)
    monkeypatch.setattr(netapp_address_plan, "current_lab_action_policy", lambda _mode=None: _AllowPolicy())
    monkeypatch.setenv("NETAPP_ADDRESS_APPLY", " YES ")
    monkeypatch.setenv("NETAPP_ADDRESS_CONFIRM", netapp_address_plan.ADDRESS_CONFIRM_PHRASE)
    monkeypatch.setenv("NETAPP_ADDRESS_ALLOW_CONSOLE_WRITES", "ON")
    monkeypatch.setenv("NETAPP_ADDRESS_ALLOW_LIF_CREATE", "1")
    monkeypatch.setenv("NETAPP_ADDRESS_ACCEPT_HA_WARNING", "TRUE")
    preview = {
        "command_plan": {
            "requires_lif_create": True,
            "commands": [{"enabled": True, "command": "network interface create -vserver esxi_svm"}],
        },
        "console_facts": {"identified_state": "ontap_shell", "cluster_ha_warning": False},
        "address_conflict_scan": {"free": True, "conflicts": []},
    }

    gates = netapp_address_plan._address_apply_gates(preview)

    assert gates["blockers"] == []
    assert gates["flag_state"]["netapp_address_apply"] is True
    assert gates["flag_state"]["netapp_address_allow_console_writes"] is True
    assert gates["flag_state"]["netapp_address_allow_lif_create"] is True
    assert gates["flag_state"]["netapp_address_accept_ha_warning"] is True


def test_address_apply_gates_do_not_allow_ha_warning_override(monkeypatch) -> None:
    settings_override = replace(
        settings,
        provider_mode="local-lab-readwrite",
        netapp_api_username="admin",
        netapp_api_password="configured-value",
    )
    monkeypatch.setattr(netapp_address_plan, "settings", settings_override)
    monkeypatch.setattr(netapp_address_plan, "current_lab_action_policy", lambda _mode=None: _AllowPolicy())
    monkeypatch.setenv("NETAPP_ADDRESS_APPLY", "true")
    monkeypatch.setenv("NETAPP_ADDRESS_CONFIRM", netapp_address_plan.ADDRESS_CONFIRM_PHRASE)
    monkeypatch.setenv("NETAPP_ADDRESS_ALLOW_CONSOLE_WRITES", "true")
    monkeypatch.setenv("NETAPP_ADDRESS_ACCEPT_HA_WARNING", "true")
    preview = {
        "command_plan": {
            "requires_lif_create": False,
            "commands": [{"enabled": True, "command": "network interface modify -vserver X20"}],
        },
        "console_facts": {
            "identified_state": "ontap_shell",
            "cluster_ha_warning": True,
            "node_health": {"unhealthy_nodes": ["X20-01"]},
        },
        "address_conflict_scan": {"free": True, "conflicts": []},
    }

    gates = netapp_address_plan._address_apply_gates(preview)

    assert "NetApp node health must be clean before address writes; unhealthy: X20-01." in gates["blockers"]
    assert "NetApp cluster HA warning must be resolved before address writes." in gates["blockers"]


def test_address_apply_gates_keep_scalar_policy_blocker_whole(monkeypatch) -> None:
    class ScalarPolicy:
        def action_blockers(self, _action_id, _category):
            return " policy blocker "

    settings_override = replace(
        settings,
        provider_mode="local-lab-readwrite",
        netapp_api_username="admin",
        netapp_api_password="configured-value",
    )
    monkeypatch.setattr(netapp_address_plan, "settings", settings_override)
    monkeypatch.setattr(netapp_address_plan, "current_lab_action_policy", lambda _mode=None: ScalarPolicy())
    monkeypatch.setenv("NETAPP_ADDRESS_APPLY", "true")
    monkeypatch.setenv("NETAPP_ADDRESS_CONFIRM", netapp_address_plan.ADDRESS_CONFIRM_PHRASE)
    monkeypatch.setenv("NETAPP_ADDRESS_ALLOW_CONSOLE_WRITES", "true")
    monkeypatch.setenv("NETAPP_ADDRESS_ALLOW_LIF_CREATE", "true")
    monkeypatch.setenv("NETAPP_ADDRESS_ACCEPT_HA_WARNING", "true")
    preview = {
        "command_plan": {
            "requires_lif_create": False,
            "commands": [{"enabled": True, "command": "network interface modify -vserver esxi_svm"}],
        },
        "console_facts": {"identified_state": "ontap_shell"},
        "address_conflict_scan": {"free": True, "conflicts": []},
    }

    gates = netapp_address_plan._address_apply_gates(preview)

    assert gates["blockers"] == ["policy blocker"]
    assert "p" not in gates["blockers"]


def test_address_plan_json_uses_atomic_store(monkeypatch, tmp_path: Path) -> None:
    _redirect_address_reports(monkeypatch, tmp_path)
    settings_override = replace(
        settings,
        provider_mode="local-lab-readwrite",
        netapp_cluster_mgmt_ip="192.168.1.220",
        netapp_node_a_mgmt_ip="192.168.1.221",
        netapp_node_b_mgmt_ip="192.168.1.222",
        netapp_svm_mgmt_ip="192.168.1.223",
        netapp_nfs_lifs=("192.168.1.230", "192.168.1.231"),
    )
    monkeypatch.setattr(netapp_address_plan, "settings", settings_override)
    monkeypatch.setattr(
        netapp_address_plan,
        "get_netapp_runtime_state",
        lambda: {"configured": False, "configured_state": "not_detected", "source": "test"},
    )

    payload = netapp_address_plan.build_netapp_address_remediation_plan(write_report=True)

    saved = json.loads(netapp_address_plan.ADDRESS_PLAN_JSON.read_text(encoding="utf-8"))
    assert saved["action"] == payload["action"]
    assert netapp_address_plan.ADDRESS_PLAN_REPORT.read_text(encoding="utf-8").strip()
    assert list(netapp_address_plan.CODEX_RUN_DIR.glob("*.tmp")) == []


def test_upgrade_report_paths_use_posix_separators(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(netapp_upgrade_center, "REPO_ROOT", tmp_path)

    assert netapp_upgrade_center._rel(tmp_path / "artifacts" / "codex-runs" / "report.md") == "artifacts/codex-runs/report.md"


def test_upgrade_inventory_reports_not_configured_before_cluster_management(monkeypatch) -> None:
    _patch_upgrade_runtime(monkeypatch, configured=False)
    _patch_upgrade_settings(monkeypatch)
    _patch_media(monkeypatch, [])

    payload = netapp_upgrade_center.build_netapp_upgrade_inventory(write_report=False)

    assert payload["status"] == "not_configured_yet"
    assert payload["current_ontap_version"] is None
    assert any("cluster management" in blocker for blocker in payload["blockers"])


def test_upgrade_inventory_uses_console_version_before_cluster_management(monkeypatch) -> None:
    _patch_upgrade_runtime(monkeypatch, configured=False)
    _patch_upgrade_settings(monkeypatch)
    _patch_media(monkeypatch, [_ontap_media(version_hint="9.17.1")])
    monkeypatch.setattr(
        netapp_upgrade_center,
        "latest_console_ontap_version",
        lambda: {
            "version": "9.17.1",
            "source": "console_read_only",
            "checked_at": "2026-06-13T00:00:00+00:00",
        },
    )

    payload = netapp_upgrade_center.build_netapp_upgrade_inventory(write_report=False)

    assert payload["status"] == "not_configured_yet"
    assert payload["current_ontap_version"] == "9.17.1"
    assert payload["current_version_source"] == "console_read_only"
    assert payload["cluster_image_repository"]["source_type"] == "console_read_only"
    assert not any("Current ONTAP version is unknown" in blocker for blocker in payload["blockers"])
    assert any("cluster management" in blocker for blocker in payload["blockers"])


def test_upgrade_apply_disabled_before_setup(monkeypatch) -> None:
    _patch_upgrade_runtime(monkeypatch, configured=False)
    _patch_upgrade_settings(monkeypatch)
    _patch_media(monkeypatch, [_ontap_media()])

    payload = netapp_upgrade_center.apply_netapp_upgrade(write_report=False)

    assert payload["status"] == "blocked"
    assert payload["apply_enabled"] is False
    assert any("cluster management" in blocker for blocker in payload["blockers"])


def test_upgrade_apply_disabled_without_image(monkeypatch, tmp_path) -> None:
    _patch_upgrade_runtime(monkeypatch, configured=True)
    _patch_upgrade_settings(monkeypatch, current_version="9.13.1")
    _patch_media(monkeypatch, [])
    monkeypatch.setattr(netapp_upgrade_center, "UPGRADE_VALIDATION_JSON", tmp_path / "missing.json")

    payload = netapp_upgrade_center.apply_netapp_upgrade(write_report=False)

    assert payload["apply_enabled"] is False
    assert any("image/package" in blocker for blocker in payload["blockers"])


def test_upgrade_apply_disabled_without_validation(monkeypatch, tmp_path) -> None:
    _patch_upgrade_runtime(monkeypatch, configured=True)
    _patch_upgrade_settings(monkeypatch, current_version="9.13.1")
    _patch_media(monkeypatch, [_ontap_media()])
    monkeypatch.setattr(netapp_upgrade_center, "UPGRADE_VALIDATION_JSON", tmp_path / "missing.json")

    payload = netapp_upgrade_center.apply_netapp_upgrade(write_report=False)

    assert payload["apply_enabled"] is False
    assert any("validation" in blocker.lower() for blocker in payload["blockers"])


def test_upgrade_plan_treats_validation_probe_errors_as_not_run(monkeypatch, tmp_path) -> None:
    _patch_upgrade_runtime(monkeypatch, configured=True)
    _patch_upgrade_settings(monkeypatch, current_version="9.13.1")
    _patch_media(monkeypatch, [_ontap_media()])
    validation = tmp_path / "validation.json"
    monkeypatch.setattr(netapp_upgrade_center, "UPGRADE_VALIDATION_JSON", validation)
    original_exists = Path.exists

    def flaky_exists(path: Path) -> bool:
        if path == validation:
            raise OSError("validation artifact path is unavailable")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    payload = netapp_upgrade_center.build_netapp_upgrade_plan(write_report=False)

    assert payload["pre_upgrade_validation"]["status"] == "not_run"
    assert payload["pre_upgrade_validation"]["validation_passed"] is False
    assert payload["button_state"] == "Disabled: validation not run"


def test_upgrade_plan_treats_corrupt_validation_as_unreadable(monkeypatch, tmp_path) -> None:
    _patch_upgrade_runtime(monkeypatch, configured=True)
    _patch_upgrade_settings(monkeypatch, current_version="9.13.1")
    _patch_media(monkeypatch, [_ontap_media()])
    validation = tmp_path / "validation.json"
    validation.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(netapp_upgrade_center, "UPGRADE_VALIDATION_JSON", validation)

    payload = netapp_upgrade_center.build_netapp_upgrade_plan(write_report=False)

    assert payload["pre_upgrade_validation"]["status"] == "unreadable"
    assert payload["pre_upgrade_validation"]["validation_passed"] is False
    assert payload["button_state"] == "Disabled: validation failed"


def test_upgrade_plan_self_heals_scalar_inventory_lists(monkeypatch) -> None:
    monkeypatch.setattr(netapp_upgrade_center, "_netapp_in_scope", lambda: True)
    monkeypatch.setattr(
        netapp_upgrade_center,
        "build_netapp_upgrade_inventory",
        lambda *, write_report: {
            "current_ontap_version": "9.13.1",
            "current_version_source": "test",
            "local_image_packages": "not-a-package-list",
            "supported_path_state": "ready",
            "blockers": " Inventory blocked. ",
        },
    )
    monkeypatch.setattr(netapp_upgrade_center, "_latest_validation", lambda: {"validation_passed": True})
    monkeypatch.setattr(
        netapp_upgrade_center,
        "settings",
        replace(settings, netapp_target_ontap_version="9.14.1", netapp_upgrade_advisor_plan="attached"),
    )

    payload = netapp_upgrade_center.build_netapp_upgrade_plan(write_report=False)

    assert "Inventory blocked." in payload["blockers"]
    assert not any(blocker == "I" for blocker in payload["blockers"])
    assert payload["selected_package"] is None
    assert "No local ONTAP image/package is selected." in payload["blockers"]


def test_upgrade_validation_self_heals_scalar_inventory_blockers(monkeypatch) -> None:
    monkeypatch.setattr(netapp_upgrade_center, "_netapp_in_scope", lambda: True)
    monkeypatch.setattr(
        netapp_upgrade_center,
        "build_netapp_upgrade_inventory",
        lambda *, write_report: {
            "cluster_management_configured": True,
            "access_configured": True,
            "current_ontap_version": "9.13.1",
            "local_image_packages": "not-a-package-list",
            "supported_path_state": "ready",
            "blockers": " Inventory blocked. ",
        },
    )
    monkeypatch.setattr(netapp_upgrade_center, "get_netapp_setup_intent", lambda: {"missing_fields": []})
    monkeypatch.setattr(
        netapp_upgrade_center,
        "settings",
        replace(settings, netapp_target_ontap_version="9.14.1"),
    )

    payload = netapp_upgrade_center.validate_netapp_upgrade(write_report=False)

    assert "Inventory blocked." in payload["blockers"]
    assert not any(blocker == "I" for blocker in payload["blockers"])
    assert "No ONTAP image/package is selected." in payload["blockers"]


def test_upgrade_apply_blockers_self_heals_scalar_plan_blockers(monkeypatch) -> None:
    monkeypatch.setattr(netapp_upgrade_center, "current_lab_action_policy", lambda _mode=None: _AllowPolicy())

    blockers = netapp_upgrade_center._upgrade_apply_blockers(
        {
            "blockers": " Pre-upgrade validation has not passed. ",
            "current_version": "9.13.1",
            "target_version": "9.14.1",
            "selected_package": {"path": "ontap.tgz"},
        },
        {"validation_passed": False},
        {"active": True},
        {
            "netapp_ontap_upgrade_apply": True,
            "netapp_ontap_upgrade_confirm": True,
        },
    )

    assert blockers == []


def test_upgrade_apply_blockers_keep_scalar_policy_blocker_whole(monkeypatch) -> None:
    class ScalarPolicy:
        def action_blockers(self, _action_id, _category):
            return " policy blocker "

    monkeypatch.setattr(netapp_upgrade_center, "current_lab_action_policy", lambda _mode=None: ScalarPolicy())

    blockers = netapp_upgrade_center._upgrade_apply_blockers(
        {
            "blockers": [],
            "current_version": "9.13.1",
            "target_version": "9.14.1",
            "selected_package": {"path": "ontap.tgz"},
        },
        {"validation_passed": True},
        {"active": False},
        {
            "netapp_ontap_upgrade_apply": True,
            "netapp_ontap_upgrade_confirm": True,
        },
    )

    assert blockers == ["policy blocker"]
    assert "p" not in blockers


def test_upgrade_apply_disabled_when_validation_has_errors(monkeypatch, tmp_path) -> None:
    _patch_upgrade_runtime(monkeypatch, configured=True)
    _patch_upgrade_settings(monkeypatch, current_version="9.13.1")
    _patch_media(monkeypatch, [_ontap_media()])
    validation = tmp_path / "validation.json"
    validation.write_text(json.dumps({"status": "blocked", "validation_passed": False}), encoding="utf-8")
    monkeypatch.setattr(netapp_upgrade_center, "UPGRADE_VALIDATION_JSON", validation)

    payload = netapp_upgrade_center.apply_netapp_upgrade(write_report=False)

    assert payload["apply_enabled"] is False
    assert any("validation" in blocker.lower() for blocker in payload["blockers"])


def test_upgrade_reports_use_atomic_store(monkeypatch, tmp_path) -> None:
    _patch_upgrade_runtime(monkeypatch, configured=True)
    _patch_upgrade_settings(monkeypatch, current_version="9.13.1")
    _patch_media(monkeypatch, [_ontap_media()])
    monkeypatch.setattr(netapp_upgrade_center, "REPO_ROOT", tmp_path)
    json_path = tmp_path / "artifacts" / "codex-runs" / "netapp-upgrade-inventory-redacted.json"
    report_path = tmp_path / "artifacts" / "codex-runs" / "inventory.md"
    monkeypatch.setattr(netapp_upgrade_center, "UPGRADE_INVENTORY_JSON", json_path)
    monkeypatch.setattr(
        netapp_upgrade_center,
        "UPGRADE_INVENTORY_REPORT",
        report_path,
    )

    payload = netapp_upgrade_center.build_netapp_upgrade_inventory(write_report=True)

    assert json.loads(json_path.read_text(encoding="utf-8"))["action"] == payload["action"]
    assert report_path.read_text(encoding="utf-8").strip()
    assert list(json_path.parent.glob("*.tmp")) == []


def test_upgrade_validation_waiver_removes_validation_blocker(monkeypatch, tmp_path) -> None:
    _patch_upgrade_runtime(monkeypatch, configured=True)
    _patch_upgrade_settings(monkeypatch, current_version="9.13.1")
    _patch_media(monkeypatch, [_ontap_media()])
    validation = tmp_path / "validation.json"
    validation.write_text(json.dumps({"status": "blocked", "validation_passed": False}), encoding="utf-8")
    monkeypatch.setattr(netapp_upgrade_center, "UPGRADE_VALIDATION_JSON", validation)
    monkeypatch.setenv("NETAPP_ONTAP_UPGRADE_VALIDATION_WAIVER", " YES ")
    monkeypatch.setenv("NETAPP_ONTAP_UPGRADE_WAIVER_CONFIRM", "WAIVE ONTAP VALIDATION")

    payload = netapp_upgrade_center.apply_netapp_upgrade(write_report=False)

    assert payload["validation_waiver"]["active"] is True
    assert not any(
        "Pre-upgrade validation has not passed" in blocker
        for blocker in payload["blockers"]
    )


def test_upgrade_apply_accepts_common_true_like_env_values(monkeypatch, tmp_path) -> None:
    _patch_upgrade_runtime(monkeypatch, configured=True)
    _patch_upgrade_settings(monkeypatch, current_version="9.13.1")
    _patch_media(monkeypatch, [_ontap_media()])
    validation = tmp_path / "validation.json"
    validation.write_text(json.dumps({"status": "passed", "validation_passed": True}), encoding="utf-8")
    monkeypatch.setattr(netapp_upgrade_center, "UPGRADE_VALIDATION_JSON", validation)
    monkeypatch.setenv("NETAPP_ONTAP_UPGRADE_APPLY", "ON")
    monkeypatch.setenv("NETAPP_ONTAP_UPGRADE_CONFIRM", "UPGRADE ONTAP")

    payload = netapp_upgrade_center.apply_netapp_upgrade(write_report=False)

    assert payload["flag_state"]["netapp_ontap_upgrade_apply"] is True
    assert not any("NETAPP_ONTAP_UPGRADE_APPLY=true" in blocker for blocker in payload["blockers"])


def test_netapp_upgrade_payload_redacts_access_values(monkeypatch) -> None:
    _patch_upgrade_runtime(monkeypatch, configured=True)
    _patch_upgrade_settings(monkeypatch, current_version="9.13.1", access_value="super-secret-value")
    _patch_media(monkeypatch, [_ontap_media()])
    monkeypatch.setenv("NETAPP_API_PASSWORD", "super-secret-value")

    payload = netapp_upgrade_center.build_netapp_upgrade_inventory(write_report=False)

    assert "super-secret-value" not in json.dumps(payload)


def test_upgrade_button_state_variants(monkeypatch, tmp_path) -> None:
    _patch_upgrade_runtime(monkeypatch, configured=False)
    _patch_upgrade_settings(monkeypatch)
    _patch_media(monkeypatch, [_ontap_media()])
    monkeypatch.setattr(netapp_upgrade_center, "UPGRADE_VALIDATION_JSON", tmp_path / "missing.json")
    assert netapp_upgrade_center.build_netapp_upgrade_plan(write_report=False)["button_state"] == "Disabled: NetApp not configured"

    _patch_upgrade_runtime(monkeypatch, configured=True)
    _patch_media(monkeypatch, [])
    assert netapp_upgrade_center.build_netapp_upgrade_plan(write_report=False)["button_state"] == "Disabled: no ONTAP image/package"

    _patch_media(monkeypatch, [_ontap_media()])
    assert netapp_upgrade_center.build_netapp_upgrade_plan(write_report=False)["button_state"] == "Disabled: validation not run"

    validation = tmp_path / "validation.json"
    validation.write_text(json.dumps({"status": "blocked", "validation_passed": False}), encoding="utf-8")
    monkeypatch.setattr(netapp_upgrade_center, "UPGRADE_VALIDATION_JSON", validation)
    assert netapp_upgrade_center.build_netapp_upgrade_plan(write_report=False)["button_state"] == "Disabled: validation failed"


def test_upgrade_validation_current_when_target_matches_running_version(monkeypatch) -> None:
    _patch_upgrade_runtime(monkeypatch, configured=True)
    _patch_upgrade_settings(monkeypatch, current_version="9.17.1", target_version="9.17.1")
    _patch_media(monkeypatch, [_ontap_media(version_hint="9.17.1")])
    monkeypatch.setattr(netapp_upgrade_center, "get_netapp_setup_intent", lambda: {"missing_fields": []})

    payload = netapp_upgrade_center.validate_netapp_upgrade(write_report=False)

    assert payload["status"] == "current"
    assert payload["validation_passed"] is True
    assert payload["blockers"] == []
    assert payload["current_version"] == "9.17.1"
    assert payload["target_version"] == "9.17.1"
    assert any("no upgrade" in warning.lower() for warning in payload["warnings"])


def test_upgrade_plan_current_disables_upgrade_button_without_blocker(monkeypatch, tmp_path) -> None:
    _patch_upgrade_runtime(monkeypatch, configured=True)
    _patch_upgrade_settings(monkeypatch, current_version="9.17.1", target_version="9.17.1")
    _patch_media(monkeypatch, [_ontap_media(version_hint="9.17.1")])
    validation = tmp_path / "validation.json"
    validation.write_text(json.dumps({"status": "current", "validation_passed": True}), encoding="utf-8")
    monkeypatch.setattr(netapp_upgrade_center, "UPGRADE_VALIDATION_JSON", validation)

    payload = netapp_upgrade_center.build_netapp_upgrade_plan(write_report=False)

    assert payload["status"] == "current"
    assert payload["button_state"] == "Current: no ONTAP upgrade needed"
    assert payload["blockers"] == []
    assert payload["expected_commands_or_api_calls"] == []


def test_upgrade_apply_current_does_not_attempt_upgrade(monkeypatch, tmp_path) -> None:
    _patch_upgrade_runtime(monkeypatch, configured=True)
    _patch_upgrade_settings(monkeypatch, current_version="9.17.1", target_version="9.17.1")
    _patch_media(monkeypatch, [_ontap_media(version_hint="9.17.1")])
    validation = tmp_path / "validation.json"
    validation.write_text(json.dumps({"status": "current", "validation_passed": True}), encoding="utf-8")
    monkeypatch.setattr(netapp_upgrade_center, "UPGRADE_VALIDATION_JSON", validation)

    payload = netapp_upgrade_center.apply_netapp_upgrade(write_report=False)

    assert payload["status"] == "current"
    assert payload["apply_enabled"] is False
    assert payload["upgrade_writes_attempted"] is False
    assert payload["blockers"] == []


def _patch_setup_runtime(monkeypatch, *, detected: bool) -> None:
    monkeypatch.setattr(
        netapp_setup_intent,
        "get_netapp_runtime_state",
        lambda: {
            "configured": False,
            "configured_state": "setup_wizard" if detected else "not_detected",
            "source": "test",
            "console": {
                "discovered_port": "/dev/ttyUSB0",
                "baud": 115200,
                "prompt_state": "cluster_setup_prompt" if detected else None,
                "prompt_label": "NetApp cluster setup wizard" if detected else None,
                "confidence": "high",
                "source": "test",
            },
        },
    )


def _patch_setup_settings(monkeypatch) -> None:
    settings_override = replace(
        settings,
        provider_mode="local-lab-readwrite",
        lab_environment="isolated-real-lab",
        lab_acknowledge_real_hardware=True,
        lab_acknowledge_device_reconfiguration=True,
        lab_acknowledge_data_loss_risk=True,
        lab_acknowledge_lab_only=True,
        netapp_cluster_name="lab-netapp-cluster",
        netapp_node_a_name="lab-netapp-node-a",
        netapp_node_b_name="lab-netapp-node-b",
        netapp_svm_name="esxi_svm",
        netapp_dns_servers=("192.168.1.1",),
        netapp_ntp_servers=("192.168.1.205",),
        netapp_search_domains=("lab.local",),
        netapp_admin_access_source="redacted env reference",
        netapp_api_username="admin",
        netapp_api_password="configured-value",
    )
    monkeypatch.setattr(netapp_setup_intent, "settings", settings_override)


def _redirect_setup_reports(monkeypatch, tmp_path: Path) -> None:
    codex_runs = tmp_path / "artifacts" / "codex-runs"
    codex_runs.mkdir(parents=True)
    monkeypatch.setattr(netapp_setup_intent, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(netapp_setup_intent, "CODEX_RUN_DIR", codex_runs)
    monkeypatch.setattr(netapp_setup_intent, "BASELINE_REPORT", codex_runs / "netapp-setup-upgrade-baseline-report.md")
    monkeypatch.setattr(netapp_setup_intent, "SETUP_PLAN_REPORT", codex_runs / "netapp-setup-plan-report.md")
    monkeypatch.setattr(netapp_setup_intent, "SETUP_PREVIEW_REPORT", codex_runs / "netapp-setup-preview-report.md")
    monkeypatch.setattr(netapp_setup_intent, "SETUP_PREVIEW_JSON", codex_runs / "netapp-setup-preview-redacted.json")
    monkeypatch.setattr(netapp_setup_intent, "SETUP_APPLY_REPORT", codex_runs / "netapp-cluster-setup-apply-report.md")
    monkeypatch.setattr(netapp_setup_intent, "SETUP_APPLY_JSON", codex_runs / "netapp-cluster-setup-apply-redacted.json")
    monkeypatch.setattr(netapp_setup_intent, "POST_SETUP_VALIDATION_REPORT", codex_runs / "netapp-post-setup-validation-report.md")
    monkeypatch.setattr(netapp_setup_intent, "POST_SETUP_VALIDATION_JSON", codex_runs / "netapp-post-setup-validation-redacted.json")


def _redirect_nfs_reports(monkeypatch, tmp_path: Path) -> None:
    codex_runs = tmp_path / "artifacts" / "codex-runs"
    codex_runs.mkdir(parents=True)
    monkeypatch.setattr(netapp_nfs_setup, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(netapp_nfs_setup, "CODEX_RUN_DIR", codex_runs)
    monkeypatch.setattr(netapp_nfs_setup, "NFS_PREVIEW_REPORT", codex_runs / "netapp-nfs-setup-preview-report.md")
    monkeypatch.setattr(netapp_nfs_setup, "NFS_PREVIEW_JSON", codex_runs / "netapp-nfs-setup-preview-redacted.json")
    monkeypatch.setattr(netapp_nfs_setup, "NFS_APPLY_REPORT", codex_runs / "netapp-nfs-setup-apply-report.md")
    monkeypatch.setattr(netapp_nfs_setup, "NFS_APPLY_JSON", codex_runs / "netapp-nfs-setup-apply-redacted.json")
    monkeypatch.setattr(netapp_nfs_setup, "NFS_VALIDATION_REPORT", codex_runs / "netapp-nfs-setup-validation-report.md")
    monkeypatch.setattr(netapp_nfs_setup, "NFS_VALIDATION_JSON", codex_runs / "netapp-nfs-setup-validation-redacted.json")


def _redirect_factory_reset_reports(monkeypatch, tmp_path: Path) -> None:
    codex_runs = tmp_path / "artifacts" / "codex-runs"
    codex_runs.mkdir(parents=True)
    monkeypatch.setattr(netapp_factory_reset, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(netapp_factory_reset, "CODEX_RUN_DIR", codex_runs)
    monkeypatch.setattr(netapp_factory_reset, "FACTORY_RESET_PLAN_REPORT", codex_runs / "netapp-factory-reset-plan-report.md")
    monkeypatch.setattr(netapp_factory_reset, "FACTORY_RESET_PLAN_JSON", codex_runs / "netapp-factory-reset-plan-redacted.json")
    monkeypatch.setattr(netapp_factory_reset, "FACTORY_RESET_APPLY_REPORT", codex_runs / "netapp-factory-reset-apply-report.md")
    monkeypatch.setattr(netapp_factory_reset, "FACTORY_RESET_APPLY_JSON", codex_runs / "netapp-factory-reset-apply-redacted.json")
    monkeypatch.setattr(netapp_factory_reset, "FACTORY_RESET_VALIDATION_REPORT", codex_runs / "netapp-factory-reset-validation-report.md")
    monkeypatch.setattr(netapp_factory_reset, "FACTORY_RESET_VALIDATION_JSON", codex_runs / "netapp-factory-reset-validation-redacted.json")
    monkeypatch.setattr(netapp_factory_reset, "ADDRESS_VALIDATION_REPORT", codex_runs / "netapp-address-remediation-validation-report.md")


def _redirect_address_reports(monkeypatch, tmp_path: Path) -> None:
    codex_runs = tmp_path / "artifacts" / "codex-runs"
    codex_runs.mkdir(parents=True)
    monkeypatch.setattr(netapp_address_plan, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(netapp_address_plan, "CODEX_RUN_DIR", codex_runs)
    monkeypatch.setattr(netapp_address_plan, "CONSOLE_LOGIN_STATE_JSON", codex_runs / "netapp-console-login-state-redacted.json")
    monkeypatch.setattr(netapp_address_plan, "ADDRESS_PLAN_REPORT", codex_runs / "netapp-address-remediation-plan-report.md")
    monkeypatch.setattr(netapp_address_plan, "ADDRESS_PLAN_JSON", codex_runs / "netapp-address-remediation-plan-redacted.json")
    monkeypatch.setattr(netapp_address_plan, "ADDRESS_PREVIEW_REPORT", codex_runs / "netapp-address-remediation-preview-report.md")
    monkeypatch.setattr(netapp_address_plan, "ADDRESS_PREVIEW_JSON", codex_runs / "netapp-address-remediation-preview-redacted.json")
    monkeypatch.setattr(netapp_address_plan, "ADDRESS_APPLY_REPORT", codex_runs / "netapp-address-remediation-apply-report.md")
    monkeypatch.setattr(netapp_address_plan, "ADDRESS_APPLY_JSON", codex_runs / "netapp-address-remediation-apply-redacted.json")
    monkeypatch.setattr(netapp_address_plan, "ADDRESS_VALIDATION_REPORT", codex_runs / "netapp-address-remediation-validation-report.md")
    monkeypatch.setattr(netapp_address_plan, "ADDRESS_VALIDATION_JSON", codex_runs / "netapp-address-remediation-validation-redacted.json")
    monkeypatch.setattr(netapp_address_plan, "HA_NODE_REPORT", codex_runs / "netapp-ha-node-remediation-report.md")
    monkeypatch.setattr(netapp_address_plan, "HA_NODE_JSON", codex_runs / "netapp-ha-node-remediation-redacted.json")


def _factory_address_plan() -> dict:
    return {
        "current_targets": {
            "cluster_mgmt": "192.168.1.220",
            "node_a_mgmt": "192.168.1.221",
            "node_b_mgmt": "192.168.1.222",
            "svm_mgmt": "192.168.1.223",
            "nfs_lifs": ["192.168.1.230"],
        },
        "planned_targets": {"cluster_mgmt": "192.168.1.220"},
        "console_facts": {
            "node_health": "degraded",
            "cluster_ha_warning": "warning",
            "identified_state": "existing_cluster_shell",
        },
    }


class _AllowPolicy:
    allow_factory_reset = True

    def action_blockers(self, _action_id, _category):
        return []


def _patch_upgrade_runtime(monkeypatch, *, configured: bool) -> None:
    monkeypatch.setattr(
        netapp_upgrade_center,
        "get_netapp_runtime_state",
        lambda: {
            "configured": configured,
            "configured_state": "configured" if configured else "setup_wizard",
            "source": "test",
            "console": {"prompt_state": "existing_cluster_shell" if configured else "cluster_setup_prompt"},
        },
    )


def _patch_nfs_runtime(monkeypatch, *, configured: bool) -> None:
    monkeypatch.setattr(
        netapp_nfs_setup,
        "get_netapp_runtime_state",
        lambda: {
            "configured": configured,
            "configured_state": "configured" if configured else "login_required",
            "source": "test",
        },
    )


def _patch_iscsi_runtime(monkeypatch, *, protocol_ready: bool) -> None:
    checks = [
        {"address": "192.168.1.240", "port": 3260, "reachable": True},
        {"address": "192.168.1.241", "port": 3260, "reachable": True},
    ]
    monkeypatch.setattr(
        netapp_iscsi_setup,
        "get_netapp_runtime_state",
        lambda: {
            "configured": True,
            "configured_state": "configured",
            "source": "test",
            "storage": {"iscsi_lifs_detected": ["192.168.1.240", "192.168.1.241"]},
            "protocol_options": {
                "iscsi": {
                    "ready": protocol_ready,
                    "service_status": "ready" if protocol_ready else "blocked",
                    "service_enabled": protocol_ready,
                    "lifs": ["192.168.1.240", "192.168.1.241"],
                    "reachable_lif_count": 2 if protocol_ready else 0,
                    "port": 3260,
                    "checks": checks,
                    "blockers": [] if protocol_ready else ["NetApp iSCSI service is not enabled."],
                }
            },
        },
    )


def _missing_iscsi_inventory() -> dict:
    return {
        "checked": True,
        "source": "test",
        "status": "ready",
        "svm": {"exists": True, "name": "esxi_svm"},
        "iscsi_service": {"exists": True, "enabled": True, "target_iqn": "iqn.1992-08.com.netapp:test"},
        "volume": {"exists": True, "name": "esxi_datastore_01"},
        "lun": {"exists": False},
        "igroup": {"exists": False, "initiators": []},
        "lun_map": {"exists": False},
        "blockers": [],
    }


def _patch_upgrade_settings(
    monkeypatch,
    *,
    current_version: str | None = None,
    target_version: str | None = None,
    access_value: str = "configured-value",
) -> None:
    settings_override = replace(
        settings,
        provider_mode="local-lab-readwrite",
        lab_environment="isolated-real-lab",
        lab_acknowledge_real_hardware=True,
        lab_acknowledge_device_reconfiguration=True,
        lab_acknowledge_data_loss_risk=True,
        lab_acknowledge_lab_only=True,
        lab_allow_firmware_updates=True,
        netapp_current_ontap_version=current_version,
        netapp_target_ontap_version=target_version if target_version is not None else "9.14.1" if current_version else None,
        netapp_api_username="admin",
        netapp_api_password=access_value,
        netapp_cluster_name="lab-netapp-cluster",
        netapp_node_a_name="lab-netapp-node-a",
        netapp_node_b_name="lab-netapp-node-b",
        netapp_svm_name="esxi_svm",
        netapp_dns_servers=("192.168.1.1",),
        netapp_ntp_servers=("192.168.1.205",),
        netapp_search_domains=("lab.local",),
        netapp_admin_access_source="redacted env reference",
        netapp_upgrade_advisor_plan="redacted local plan reference",
    )
    monkeypatch.setattr(netapp_upgrade_center, "settings", settings_override)
    monkeypatch.setattr(
        netapp_upgrade_center,
        "latest_console_ontap_version",
        lambda: {"version": None, "source": "not_available", "checked_at": None},
    )


def _patch_media(monkeypatch, items: list[MediaInventoryItemRead]) -> None:
    inventory = MediaInventoryRead(mode="local", configured_directories=["configured-directory-1"], items=items, warnings=[])
    monkeypatch.setattr(netapp_upgrade_center, "get_media_inventory", lambda: inventory)


def _ontap_media(*, version_hint: str = "9.14.1") -> MediaInventoryItemRead:
    return MediaInventoryItemRead(
        placeholder_name="firmware-1.tgz",
        extension=".tgz",
        size_bytes=1024,
        category="firmware",
        source="configured-directory-1",
        actual_name_redacted=True,
        product_hints=["netapp-ontap"],
        version_hint=version_hint,
    )
