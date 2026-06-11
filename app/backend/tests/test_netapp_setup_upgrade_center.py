from __future__ import annotations

import json
from dataclasses import replace

from app.core.config import settings
from app.schemas import MediaInventoryItemRead, MediaInventoryRead
from app.services import netapp_setup_intent, netapp_upgrade_center


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

    assert "cluster_name" in payload["missing_fields"]
    assert "admin_access_source" in payload["missing_fields"]
    assert any(item["field_name"] == "cluster_name" for item in payload["remediation_items"])


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


def test_upgrade_inventory_reports_not_configured_before_cluster_management(monkeypatch) -> None:
    _patch_upgrade_runtime(monkeypatch, configured=False)
    _patch_upgrade_settings(monkeypatch)
    _patch_media(monkeypatch, [])

    payload = netapp_upgrade_center.build_netapp_upgrade_inventory(write_report=False)

    assert payload["status"] == "not_configured_yet"
    assert payload["current_ontap_version"] is None
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
        netapp_cluster_name="lab-ontap-cluster-01",
        netapp_node_a_name="netapp-a",
        netapp_node_b_name="netapp-b",
        netapp_svm_name="svm_esxi_nfs",
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
        netapp_cluster_name="lab-ontap-cluster-01",
        netapp_node_a_name="netapp-a",
        netapp_node_b_name="netapp-b",
        netapp_svm_name="svm_esxi_nfs",
        netapp_dns_servers=("192.168.1.1",),
        netapp_ntp_servers=("192.168.1.205",),
        netapp_search_domains=("lab.local",),
        netapp_admin_access_source="redacted env reference",
        netapp_upgrade_advisor_plan="redacted local plan reference",
    )
    monkeypatch.setattr(netapp_upgrade_center, "settings", settings_override)


def _patch_media(monkeypatch, items: list[MediaInventoryItemRead]) -> None:
    inventory = MediaInventoryRead(mode="local", configured_directories=["configured-directory-1"], items=items, warnings=[])
    monkeypatch.setattr(netapp_upgrade_center, "get_media_inventory", lambda: inventory)


def _ontap_media() -> MediaInventoryItemRead:
    return MediaInventoryItemRead(
        placeholder_name="firmware-1.tgz",
        extension=".tgz",
        size_bytes=1024,
        category="firmware",
        source="configured-directory-1",
        actual_name_redacted=True,
        product_hints=["netapp-ontap"],
        version_hint="9.14.1",
    )
