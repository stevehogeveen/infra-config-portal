from __future__ import annotations

import json
from dataclasses import replace

from app.core.config import settings
from app.schemas import MediaInventoryItemRead, MediaInventoryRead
from app.services import netapp_address_plan, netapp_nfs_setup, netapp_setup_intent, netapp_upgrade_center


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


def test_upgrade_validation_waiver_removes_validation_blocker(monkeypatch, tmp_path) -> None:
    _patch_upgrade_runtime(monkeypatch, configured=True)
    _patch_upgrade_settings(monkeypatch, current_version="9.13.1")
    _patch_media(monkeypatch, [_ontap_media()])
    validation = tmp_path / "validation.json"
    validation.write_text(json.dumps({"status": "blocked", "validation_passed": False}), encoding="utf-8")
    monkeypatch.setattr(netapp_upgrade_center, "UPGRADE_VALIDATION_JSON", validation)
    monkeypatch.setenv("NETAPP_ONTAP_UPGRADE_VALIDATION_WAIVER", "true")
    monkeypatch.setenv("NETAPP_ONTAP_UPGRADE_WAIVER_CONFIRM", "WAIVE ONTAP VALIDATION")

    payload = netapp_upgrade_center.apply_netapp_upgrade(write_report=False)

    assert payload["validation_waiver"]["active"] is True
    assert not any(
        "Pre-upgrade validation has not passed" in blocker
        for blocker in payload["blockers"]
    )


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


def _patch_upgrade_settings(
    monkeypatch,
    *,
    current_version: str | None = None,
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
        netapp_target_ontap_version="9.14.1" if current_version else None,
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
