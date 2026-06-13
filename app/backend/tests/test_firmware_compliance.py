from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.providers.probe_cache import clear_probe_results, record_probe_result
from app.services import firmware_compliance as fc


@pytest.fixture(autouse=True)
def clear_probe_cache(monkeypatch) -> None:
    clear_probe_results()
    monkeypatch.setattr(
        fc,
        "latest_console_ontap_version",
        lambda: {"version": None, "source": "not_available", "checked_at": None},
    )


@pytest.fixture()
def firmware_settings(tmp_path):
    return SimpleNamespace(
        provider_mode="local-lab-readwrite",
        media_inventory_dirs=(str(tmp_path),),
        cisco_mgmt_configured=True,
        netapp_configured=True,
        netapp_current_ontap_version="9.14",
        ilo_test_host="192.168.1.201",
        ilo_test_username="admin",
        ilo_test_password="ilo-secret",
        cisco_target_ip="192.168.1.204",
        cisco_test_username="operator",
        cisco_test_password="cisco-secret",
        cisco_enable_password="enable-secret",
        esxi_configured=True,
        netapp_api_username="netapp-admin",
        netapp_api_password="netapp-secret",
        vcenter_configured=False,
    )


def test_compliant_firmware_passes(monkeypatch, firmware_settings) -> None:
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("hpe_ilo_firmware", minimum="3.19")))
    record_probe_result("ilo-redfish", {"provider_id": "ilo-redfish", "status": "ok", "managers": [{"FirmwareVersion": "3.19"}]})

    result = fc.get_firmware_compliance()

    assert result["status"] == "passed"
    assert result["components"][0]["status"] == "passed"
    assert result["blockers"] == []


def test_ilo_legacy_identity_firmware_satisfies_baseline_when_redfish_inventory_auth_fails(
    monkeypatch,
    firmware_settings,
) -> None:
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("hpe_ilo_firmware", minimum="3.19")))
    record_probe_result(
        "ilo-redfish",
        {
            "provider_id": "ilo-redfish",
            "status": "failed",
            "endpoint_detection": {
                "classification": "redfish_inventory_auth_failed",
                "inventory_collection_classification": "redfish_collection_unauthorized",
            },
            "legacy_identity": {
                "source": "/xmldata?item=All",
                "current_firmware": "3.19",
                "ilo_generation": "ilo5",
                "serial_present": True,
            },
            "blockers": [
                "Review iLO account permissions or Redfish authentication method. No settings were changed.",
            ],
        },
    )

    result = fc.get_firmware_compliance()

    assert result["status"] == "passed"
    assert result["components"][0]["current_version"] == "3.19"
    assert result["components"][0]["status"] == "passed"


def test_firmware_media_inventory_groups_by_product_hints(monkeypatch, firmware_settings, tmp_path) -> None:
    firmware_settings.media_inventory_dirs = (str(tmp_path),)
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "_media_directories", lambda: [tmp_path])
    (tmp_path / "9131P17_q_image.tgz").write_bytes(b"ontap")
    (tmp_path / "cat9k_iosxe.17.15.05.SPA.bin").write_bytes(b"cisco")
    (tmp_path / "ilo5_319.fwpkg").write_bytes(b"ilo")

    result = fc.get_firmware_media_inventory()

    assert result["candidate_count"] == 3
    assert result["grouped_counts"] == {"cisco": 1, "hpe": 1, "netapp": 1}


def test_below_minimum_blocks(monkeypatch, firmware_settings) -> None:
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("hpe_ilo_firmware", minimum="3.19")))
    record_probe_result("ilo-redfish", {"provider_id": "ilo-redfish", "status": "ok", "managers": [{"FirmwareVersion": "2.80"}]})

    result = fc.get_firmware_compliance()

    assert result["status"] == "blocked"
    assert result["components"][0]["status"] == "blocked"
    assert "below minimum" in result["components"][0]["reason"]


@pytest.mark.parametrize(
    ("unknown_policy", "expected"),
    [("blocked", "blocked"), ("warning", "warning")],
)
def test_unknown_version_uses_baseline_policy(monkeypatch, firmware_settings, unknown_policy, expected) -> None:
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(
        fc,
        "load_firmware_baseline",
        lambda: _baseline(_component("hpe_bios_version", unknown_policy=unknown_policy)),
    )

    result = fc.get_firmware_compliance()

    assert result["components"][0]["status"] == expected


def test_not_configured_netapp_is_not_configured_yet(monkeypatch, firmware_settings) -> None:
    firmware_settings.netapp_configured = False
    firmware_settings.netapp_current_ontap_version = None
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "get_netapp_runtime_state", lambda: {"configured": False})
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("netapp_ontap_version", minimum="9.14")))

    result = fc.get_firmware_compliance()

    assert result["components"][0]["status"] == "not_configured_yet"
    assert result["devices"]["netapp"]["status"] == "not_configured_yet"


def test_netapp_console_version_satisfies_ontap_baseline(monkeypatch, firmware_settings) -> None:
    firmware_settings.netapp_configured = False
    firmware_settings.netapp_current_ontap_version = None
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "get_netapp_runtime_state", lambda: {"configured": False})
    monkeypatch.setattr(
        fc,
        "latest_console_ontap_version",
        lambda: {
            "version": "9.17.1",
            "source": "console_read_only",
            "checked_at": "2026-06-13T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("netapp_ontap_version", minimum="9.14")))

    result = fc.get_firmware_compliance(scope="netapp")

    assert result["components"][0]["status"] == "passed"
    assert result["components"][0]["current_version"] == "9.17.1"
    assert result["inventory"]["live_inventory"]["netapp"]["ontap_version_source"] == "console_read_only"


@pytest.mark.parametrize(
    ("current", "minimum", "expected"),
    [
        ("17.15.05", "17.9", 1),
        ("17.9.1", "17.9", 1),
        ("17.6.5", "17.9", -1),
    ],
)
def test_ios_xe_versions_compare_numerically(current, minimum, expected) -> None:
    assert fc._compare_versions(current, minimum) == expected


def test_cisco_console_inventory_satisfies_ios_xe_baseline(monkeypatch, firmware_settings) -> None:
    firmware_settings.cisco_mgmt_configured = False
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("cisco_ios_xe_version", minimum="17.9")))
    record_probe_result(
        "cisco-console",
        {
            "provider_id": "cisco-console",
            "status": "ok",
            "source": "console-user-exec-show-version",
            "safe_show_commands": [
                {
                    "command": "show version",
                    "version_hint": "17.15.05",
                    "raw_output_redacted": True,
                }
            ],
        },
    )

    result = fc.get_firmware_compliance(scope="cisco")

    assert result["status"] == "passed"
    assert result["components"][0]["current_version"] == "17.15.05"
    assert result["inventory"]["live_inventory"]["cisco"]["source"] == "console-user-exec-show-version"


def test_blocked_console_inventory_marks_ansible_version_historical(monkeypatch, firmware_settings) -> None:
    firmware_settings.cisco_mgmt_configured = False
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("cisco_ios_xe_version", minimum="17.9")))
    record_probe_result(
        "cisco-ansible",
        {
            "provider_id": "cisco-ansible",
            "status": "ok",
            "command_results": {"show version": {"stdout_tail": "Cisco IOS XE Software, Version 17.15.05"}},
        },
    )
    record_probe_result(
        "cisco-console",
        {
            "provider_id": "cisco-console",
            "status": "blocked",
            "source": "console",
            "prompt_state": "unknown",
            "blockers": ["Console port opened but no prompt text was captured."],
        },
    )

    result = fc.get_firmware_compliance(scope="cisco")
    cisco_inventory = result["inventory"]["live_inventory"]["cisco"]

    assert result["status"] == "blocked"
    assert result["components"][0]["current_version"] is None
    assert cisco_inventory["ios_xe_version"] is None
    assert cisco_inventory["historical_evidence"]["ios_xe_version"] == "17.15.05"
    assert cisco_inventory["historical_evidence"]["historical"] is True


def test_cisco_firmware_report_fills_missing_provider_cache(monkeypatch, firmware_settings, tmp_path) -> None:
    report = tmp_path / "cisco-firmware-inventory-report.md"
    report.write_text(
        "\n".join(
            [
                "# Cisco Firmware Inventory Report",
                "",
                "- Status: ok",
                "- Source: console-user-exec-show-version",
                "- IOS XE version: 17.15.05",
                "- Bootloader/ROMMON: 17.12.1",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "CISCO_FIRMWARE_INVENTORY_REPORT", report)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("cisco_ios_xe_version", minimum="17.9")))
    record_probe_result(
        "cisco-console",
        {
            "provider_id": "cisco-console",
            "status": "blocked",
            "source": "console-readiness",
            "blockers": ["Console requires login or password; credentials are not configured for this probe."],
        },
    )

    result = fc.get_firmware_compliance(scope="cisco")
    cisco_inventory = result["inventory"]["live_inventory"]["cisco"]

    assert result["status"] == "passed"
    assert result["components"][0]["current_version"] == "17.15.05"
    assert cisco_inventory["source"] == "console-user-exec-show-version"
    assert cisco_inventory["bootloader_rommon"] == "17.12.1"


def test_firmware_summary_includes_cisco_ios_xe_from_report(monkeypatch, firmware_settings) -> None:
    firmware_settings.cisco_mgmt_configured = False
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(
        fc,
        "_cisco_firmware_report_versions",
        lambda: {
            "status": "ok",
            "source": "console-user-exec-show-version",
            "ios_xe_version": "17.15.05",
            "bootloader_rommon": None,
            "checked_at": "2026-06-11T16:06:26+00:00",
        },
    )
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("cisco_ios_xe_version", minimum="17.9")))

    compliance = fc.get_firmware_compliance(scope="cisco")
    summary = _summary_for(fc.get_firmware_summaries(compliance=compliance), "cisco")

    assert summary["current_versions"][0]["version"] == "17.15.05"
    assert summary["compliance_status"] == "current"
    assert summary["source_type"] == "historical_evidence"


def test_firmware_summary_shows_ilo_current_and_manual_hpe_review(monkeypatch, firmware_settings) -> None:
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(
        fc,
        "load_firmware_baseline",
        lambda: _baseline(
            _component("hpe_ilo_firmware", minimum="3.19"),
            _component("hpe_bios_version", unknown_policy="warning"),
            _component("hpe_smart_array_firmware", unknown_policy="warning"),
        ),
    )
    record_probe_result(
        "ilo-redfish",
        {
            "provider_id": "ilo-redfish",
            "status": "ok",
            "managers": [{"FirmwareVersion": "iLO 5 v3.19"}],
            "systems": [{"BiosVersion": "U46 v1.80 (07/05/2023)"}],
            "storage": {"controllers": [{"FirmwareVersion": "52.26.3-5379"}]},
        },
    )

    compliance = fc.get_firmware_compliance(scope="hpe")
    summaries = fc.get_firmware_summaries(compliance=compliance)
    ilo = _summary_for(summaries, "ilo")
    raid = _summary_for(summaries, "raid")

    assert any(version["label"] == "iLO firmware" and version["version"] == "iLO 5 v3.19" for version in ilo["current_versions"])
    assert ilo["compliance_status"] == "cannot_verify"
    assert "BIOS baseline missing/manual review" in ilo["blocker"]
    assert raid["blocker"] == "Smart Array baseline missing/manual review"


def test_firmware_summary_netapp_not_configured_until_management_exists(monkeypatch, firmware_settings) -> None:
    firmware_settings.netapp_configured = False
    firmware_settings.netapp_current_ontap_version = None
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "get_netapp_runtime_state", lambda: {"configured": False})
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("netapp_ontap_version", minimum="9.14")))

    compliance = fc.get_firmware_compliance(scope="netapp")
    summary = _summary_for(fc.get_firmware_summaries(compliance=compliance), "netapp")

    assert summary["compliance_status"] == "not_configured"
    assert summary["severity"] == "gray"
    assert summary["blocker"] == "not configured yet"


def test_stale_firmware_evidence_is_yellow_not_current_red(monkeypatch, firmware_settings) -> None:
    firmware_settings.cisco_mgmt_configured = False
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(
        fc,
        "_cisco_firmware_report_versions",
        lambda: {
            "status": "ok",
            "source": "console-user-exec-show-version",
            "ios_xe_version": "17.15.05",
            "bootloader_rommon": None,
            "checked_at": "2020-01-01T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("cisco_ios_xe_version", minimum="17.9")))

    compliance = fc.get_firmware_compliance(scope="cisco")
    summary = _summary_for(fc.get_firmware_summaries(compliance=compliance), "cisco")

    assert summary["compliance_status"] == "current"
    assert summary["freshness"] == "stale"
    assert summary["severity"] == "yellow"
    assert summary["blocker"] == "stale evidence only"


def test_cisco_scope_ignores_netapp_not_configured(monkeypatch, firmware_settings) -> None:
    firmware_settings.cisco_mgmt_configured = False
    firmware_settings.netapp_configured = False
    firmware_settings.netapp_current_ontap_version = None
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(
        fc,
        "load_firmware_baseline",
        lambda: _baseline(
            _component("cisco_ios_xe_version", minimum="17.9"),
            _component("netapp_ontap_version", minimum="9.14"),
        ),
    )
    record_probe_result("cisco-console", {"provider_id": "cisco-console", "status": "ok", "ios_xe_version": "17.15.05"})

    result = fc.get_firmware_compliance(scope="cisco")

    assert result["status"] == "passed"
    assert result["devices"]["netapp"]["status"] == "not_configured_yet"
    assert result["blockers"] == []


def test_full_scope_keeps_netapp_not_configured_warning(monkeypatch, firmware_settings) -> None:
    firmware_settings.cisco_mgmt_configured = False
    firmware_settings.netapp_configured = False
    firmware_settings.netapp_current_ontap_version = None
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "get_netapp_runtime_state", lambda: {"configured": False})
    monkeypatch.setattr(
        fc,
        "load_firmware_baseline",
        lambda: _baseline(
            _component("cisco_ios_xe_version", minimum="17.9"),
            _component("netapp_ontap_version", minimum="9.14"),
        ),
    )
    record_probe_result("cisco-console", {"provider_id": "cisco-console", "status": "ok", "ios_xe_version": "17.15.05"})

    result = fc.get_firmware_compliance(scope="full")

    assert result["status"] == "warning"
    assert result["devices"]["netapp"]["status"] == "not_configured_yet"
    assert any("NetApp firmware inventory is waiting for live setup validation" in warning for warning in result["warnings"])


@pytest.mark.parametrize(
    ("component_id", "minimum", "probe_id", "probe_payload", "settings_attr"),
    [
        ("hpe_ilo_firmware", "3.19", "ilo-redfish", {"managers": [{"FirmwareVersion": "2.80"}]}, None),
        ("cisco_ios_xe_version", "17.9", "cisco-ansible", {"command_results": {"show version": {"stdout_tail": "Cisco IOS XE Software, Version 16.12.05"}}}, None),
        ("netapp_ontap_version", "9.14", None, {}, ("netapp_current_ontap_version", "9.12")),
    ],
)
def test_old_provider_versions_block(
    monkeypatch,
    firmware_settings,
    component_id,
    minimum,
    probe_id,
    probe_payload,
    settings_attr,
) -> None:
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "get_netapp_runtime_state", lambda: {"configured": firmware_settings.netapp_configured})
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component(component_id, minimum=minimum)))
    if settings_attr:
        setattr(firmware_settings, settings_attr[0], settings_attr[1])
    if probe_id:
        record_probe_result(probe_id, {"provider_id": probe_id, "status": "ok", **probe_payload})

    result = fc.get_firmware_compliance()

    assert result["status"] == "blocked"
    assert result["components"][0]["status"] == "blocked"


def test_active_waiver_converts_blocked_to_waived(monkeypatch, firmware_settings) -> None:
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("hpe_ilo_firmware", minimum="3.19")))
    monkeypatch.setenv("FIRMWARE_WAIVER_CONFIRM", "WAIVE FIRMWARE COMPLIANCE")
    monkeypatch.setenv("FIRMWARE_WAIVER_REASON", "Temporary lab validation exception")
    monkeypatch.setenv("FIRMWARE_WAIVER_EXPIRES", "2099-01-01")
    monkeypatch.setenv("FIRMWARE_WAIVER_SCOPE", "all")
    record_probe_result("ilo-redfish", {"provider_id": "ilo-redfish", "status": "ok", "managers": [{"FirmwareVersion": "2.80"}]})

    result = fc.get_firmware_compliance()

    assert result["status"] == "waived"
    assert result["components"][0]["status"] == "waived"


@pytest.mark.parametrize(
    ("reason", "expires", "expected_error"),
    [
        ("Temporary exception", "2000-01-01", "expired"),
        ("", "2099-01-01", "FIRMWARE_WAIVER_REASON"),
    ],
)
def test_invalid_waiver_does_not_unblock(monkeypatch, firmware_settings, reason, expires, expected_error) -> None:
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("hpe_ilo_firmware", minimum="3.19")))
    monkeypatch.setenv("FIRMWARE_WAIVER_CONFIRM", "WAIVE FIRMWARE COMPLIANCE")
    monkeypatch.setenv("FIRMWARE_WAIVER_REASON", reason)
    monkeypatch.setenv("FIRMWARE_WAIVER_EXPIRES", expires)
    monkeypatch.setenv("FIRMWARE_WAIVER_SCOPE", "all")
    record_probe_result("ilo-redfish", {"provider_id": "ilo-redfish", "status": "ok", "managers": [{"FirmwareVersion": "2.80"}]})

    result = fc.get_firmware_compliance()

    assert result["status"] == "blocked"
    assert any(expected_error in error for error in result["waiver"]["errors"])


def test_firmware_payload_redacts_secrets(monkeypatch, firmware_settings) -> None:
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("hpe_ilo_firmware", minimum="3.19")))
    record_probe_result(
        "ilo-redfish",
        {
            "provider_id": "ilo-redfish",
            "status": "ok",
            "managers": [{"FirmwareVersion": "3.19"}],
            "warnings": ["password=ilo-secret"],
        },
    )

    result = fc.get_firmware_compliance()

    assert "ilo-secret" not in str(result)
    assert "REDACTED" in str(result)


def test_api_exposes_firmware_gate_schema(client, monkeypatch, firmware_settings) -> None:
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("hpe_ilo_firmware", minimum="3.19")))
    record_probe_result("ilo-redfish", {"provider_id": "ilo-redfish", "status": "ok", "managers": [{"FirmwareVersion": "3.19"}]})

    response = client.get("/api/v1/lab/firmware-compliance")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "firmware-compliance"
    assert payload["status"] == "passed"
    assert payload["components"][0]["current_version"] == "3.19"


def test_api_exposes_compact_firmware_summary(client, monkeypatch, firmware_settings) -> None:
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("hpe_ilo_firmware", minimum="3.19")))
    record_probe_result("ilo-redfish", {"provider_id": "ilo-redfish", "status": "ok", "managers": [{"FirmwareVersion": "iLO 5 v3.19"}]})

    response = client.get("/api/v1/firmware/summary")

    assert response.status_code == 200
    payload = response.json()
    ilo = _summary_for(payload, "ilo")
    assert ilo["scan_action_id"] == "ilo.firmware-inventory"
    assert any(version["version"] == "iLO 5 v3.19" for version in ilo["current_versions"])


def _summary_for(summaries: list[dict], device_id: str) -> dict:
    return next(summary for summary in summaries if summary["device_id"] == device_id)


def _baseline(*components: dict) -> dict:
    return {"baseline_id": "test", "components": list(components)}


def _component(
    component_id: str,
    *,
    minimum: str | None = None,
    unknown_policy: str = "blocked",
) -> dict:
    return {
        "id": component_id,
        "device": component_id.split("_", 1)[0],
        "label": component_id,
        "minimum": minimum,
        "approved": [],
        "unknown_policy": unknown_policy,
        "next_action": "Review firmware.",
    }
