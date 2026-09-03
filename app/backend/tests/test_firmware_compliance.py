from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.providers.probe_cache import clear_probe_results, record_probe_result
from app.services import firmware_compliance as fc
from app.services import media_inventory as mi


@pytest.fixture(autouse=True)
def clear_probe_cache(monkeypatch, tmp_path) -> None:
    clear_probe_results()
    monkeypatch.setattr(fc, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(fc, "BASELINE_PATH", tmp_path / "config" / "firmware-baselines" / "real-lab.yml")
    monkeypatch.setattr(fc, "CODEX_RUN_DIR", tmp_path / "artifacts" / "codex-runs")
    monkeypatch.setattr(fc, "_media_directories", lambda: [tmp_path])
    monkeypatch.setattr(fc, "COMPLIANCE_REPORT", tmp_path / "artifacts" / "codex-runs" / "firmware-compliance-report.md")
    monkeypatch.setattr(fc, "COMPLIANCE_SUMMARY", tmp_path / "artifacts" / "codex-runs" / "firmware-compliance-summary-redacted.json")
    monkeypatch.setattr(fc, "WAIVER_REPORT", tmp_path / "artifacts" / "codex-runs" / "firmware-waiver-report.md")
    monkeypatch.setattr(fc, "LOCAL_WAIVER_PATH", tmp_path / "artifacts" / "codex-runs" / "firmware-waiver.json")
    monkeypatch.setattr(fc, "CISCO_FIRMWARE_INVENTORY_REPORT", tmp_path / "cisco-firmware-inventory-report.md")
    monkeypatch.setattr(fc, "INVENTORY_REPORT", tmp_path / "firmware-inventory-report.md")
    monkeypatch.setattr(fc, "NETAPP_ONTAP_UPGRADE_VALIDATION_JSON", tmp_path / "netapp-ontap-upgrade-validation-redacted.json")
    monkeypatch.setattr(fc, "NETAPP_ONTAP_UPGRADE_PLAN_JSON", tmp_path / "netapp-ontap-upgrade-plan-redacted.json")
    monkeypatch.setattr(fc, "ESXI_MANAGEMENT_VALIDATION_REPORT", tmp_path / "esxi-post-recovery-validation-report.md")
    monkeypatch.setattr(fc, "VCENTER_POST_INSTALL_VALIDATION_JSON", tmp_path / "vcenter-post-install-validation-redacted.json")
    monkeypatch.setattr(fc, "VCENTER_POST_ATTACH_VALIDATION_JSON", tmp_path / "vcenter-post-attach-validation-redacted.json")
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
    assert result["baseline"]["path"] == "config/firmware-baselines/real-lab.yml"
    assert result["reports"]["compliance"] == "artifacts/codex-runs/firmware-compliance-report.md"
    assert "\\" not in result["reports"]["summary"]


def test_live_firmware_refresh_never_falls_back_to_legacy_console_scan(
    monkeypatch,
    firmware_settings,
) -> None:
    from app.providers.cisco_console import CiscoConsoleAdapter
    from app.providers.ilo_redfish import IloRedfishAdapter

    firmware_settings.cisco_mgmt_configured = False
    monkeypatch.setattr(fc, "settings", firmware_settings)
    calls: list[str] = []
    monkeypatch.setattr(
        IloRedfishAdapter,
        "probe",
        lambda _self: calls.append("ilo") or {"provider_id": "ilo-redfish", "status": "ok"},
    )
    monkeypatch.setattr(
        CiscoConsoleAdapter,
        "firmware_inventory",
        lambda _self: pytest.fail("firmware refresh must not invoke legacy serial scanning"),
    )

    fc._refresh_live_inventory()

    assert calls == ["ilo"]


def test_firmware_report_paths_use_posix_separators(tmp_path) -> None:
    assert fc._rel(tmp_path / "artifacts" / "codex-runs" / "report.md") == "artifacts/codex-runs/report.md"


def test_write_firmware_reports_writes_artifacts_atomically(monkeypatch, firmware_settings) -> None:
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("hpe_ilo_firmware", minimum="3.19")))
    record_probe_result("ilo-redfish", {"provider_id": "ilo-redfish", "status": "ok", "managers": [{"FirmwareVersion": "3.19"}]})

    result = fc.write_firmware_reports()

    assert result["status"] == "passed"
    saved = json.loads(fc.COMPLIANCE_SUMMARY.read_text(encoding="utf-8"))
    assert saved["status"] == "passed"
    assert fc.INVENTORY_REPORT.read_text(encoding="utf-8").strip()
    assert fc.COMPLIANCE_REPORT.read_text(encoding="utf-8").strip()
    assert not list(fc.CODEX_RUN_DIR.glob("*.tmp"))


def test_write_firmware_reports_ignores_unavailable_stale_waiver_report(monkeypatch, firmware_settings) -> None:
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("hpe_ilo_firmware", minimum="3.19")))
    record_probe_result("ilo-redfish", {"provider_id": "ilo-redfish", "status": "ok", "managers": [{"FirmwareVersion": "3.19"}]})
    original_exists = type(fc.WAIVER_REPORT).exists

    def unavailable_exists(path) -> bool:  # noqa: ANN001
        if path == fc.WAIVER_REPORT:
            raise OSError("waiver report unavailable")
        return original_exists(path)

    monkeypatch.setattr(type(fc.WAIVER_REPORT), "exists", unavailable_exists)

    result = fc.write_firmware_reports()

    assert result["status"] == "passed"
    assert fc.COMPLIANCE_REPORT.read_text(encoding="utf-8").strip()


def test_load_firmware_baseline_self_heals_missing_empty_and_invalid_files() -> None:
    assert fc.load_firmware_baseline() == {"baseline_id": "missing", "components": []}

    fc.BASELINE_PATH.parent.mkdir(parents=True)
    fc.BASELINE_PATH.write_text("\n# no data\n", encoding="utf-8")
    assert fc.load_firmware_baseline() == {"baseline_id": "missing", "components": []}

    fc.BASELINE_PATH.write_text("this is not useful baseline yaml\n", encoding="utf-8")
    assert fc.load_firmware_baseline() == {"baseline_id": "missing", "components": []}


def test_load_firmware_baseline_filters_bad_component_shapes() -> None:
    fc.BASELINE_PATH.parent.mkdir(parents=True)
    fc.BASELINE_PATH.write_text(
        "\n".join(
            [
                "baseline_id: real-lab",
                "components:",
                "  - hpe_ilo_firmware",
                "  - id: hpe_bios_version",
                "    minimum: 2.0",
            ]
        ),
        encoding="utf-8",
    )

    baseline = fc.load_firmware_baseline()

    assert baseline["baseline_id"] == "real-lab"
    assert baseline["components"] == [{"id": "hpe_bios_version", "minimum": "2.0"}]


def test_read_json_artifact_self_heals_corrupt_cache(tmp_path) -> None:
    artifact = tmp_path / "artifact.json"
    artifact.write_text("{not valid json", encoding="utf-8")

    assert fc._read_json_artifact(artifact) == {}


def test_firmware_read_text_self_heals_locked_report(monkeypatch, tmp_path) -> None:
    report = tmp_path / "firmware-report.md"
    report.write_text("Status: ready\n", encoding="utf-8")
    original_read_text = type(report).read_text

    def locked_read_text(path, *args, **kwargs) -> str:
        if path == report:
            raise OSError("locked")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(type(report), "read_text", locked_read_text)

    assert fc._read_text(report) == ""


def test_firmware_read_text_self_heals_bad_encoding(tmp_path) -> None:
    report = tmp_path / "firmware-report.md"
    report.write_bytes(b"\xff\xfe\xfa")

    assert fc._read_text(report) == ""


def test_firmware_path_mtime_self_heals_disappearing_report(monkeypatch, tmp_path) -> None:
    report = tmp_path / "firmware-report.md"
    report.write_text("Status: ready\n", encoding="utf-8")
    original_stat = type(report).stat

    def disappearing_stat(path, *args, **kwargs) -> SimpleNamespace:
        if path == report:
            raise FileNotFoundError("gone")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(type(report), "stat", disappearing_stat)

    assert fc._path_mtime(report) is None


def test_firmware_path_mtime_self_heals_exists_probe_errors(monkeypatch, tmp_path) -> None:
    report = tmp_path / "firmware-report.md"
    original_exists = type(report).exists

    def locked_exists(path) -> bool:  # noqa: ANN001
        if path == report:
            raise OSError("path unavailable")
        return original_exists(path)

    monkeypatch.setattr(type(report), "exists", locked_exists)

    assert fc._path_mtime(report) is None


def test_firmware_string_list_self_heals_scalar_and_bad_shapes() -> None:
    assert fc._string_list(" required intermediate ") == ["required intermediate"]
    assert fc._string_list([" warning ", "warning", "", None, 42]) == ["warning", "42"]
    assert fc._string_list({"warning": "ignored"}) == []


def test_firmware_ontap_target_source_self_heals_exists_probe_errors(monkeypatch) -> None:
    original_exists = type(fc.NETAPP_ONTAP_UPGRADE_VALIDATION_JSON).exists

    def locked_exists(path) -> bool:  # noqa: ANN001
        if path == fc.NETAPP_ONTAP_UPGRADE_VALIDATION_JSON:
            raise OSError("validation artifact unavailable")
        return original_exists(path)

    monkeypatch.setattr(type(fc.NETAPP_ONTAP_UPGRADE_VALIDATION_JSON), "exists", locked_exists)
    monkeypatch.setattr(fc, "_netapp_upgrade_versions", lambda: {"target_version": "9.17.1"})

    result = fc._path_target("netapp_ontap_version", None, [])

    assert result["target_version"] == "9.17.1"
    assert result["baseline_source"] == "netapp-ontap-upgrade-plan-redacted.json"


def test_firmware_path_evidence_artifacts_self_heals_exists_probe_errors(monkeypatch, tmp_path) -> None:
    locked = tmp_path / "artifacts" / "codex-runs" / "netapp-ontap-upgrade-validation-report.md"
    available = tmp_path / "artifacts" / "codex-runs" / "netapp-ontap-upgrade-plan-report.md"
    available.parent.mkdir(parents=True)
    available.write_text("planned\n", encoding="utf-8")
    original_exists = type(available).exists

    def locked_exists(path) -> bool:  # noqa: ANN001
        if path == locked:
            raise OSError("artifact unavailable")
        return original_exists(path)

    monkeypatch.setattr(type(available), "exists", locked_exists)

    result = fc._path_evidence_artifacts("netapp_ontap_version")

    assert "artifacts/codex-runs/netapp-ontap-upgrade-validation-report.md" not in result
    assert "artifacts/codex-runs/netapp-ontap-upgrade-plan-report.md" in result


def test_existing_summary_artifacts_skips_paths_that_error(monkeypatch) -> None:
    class ArtifactPath:
        def __init__(self, *, exists: bool = True, exists_error: Exception | None = None) -> None:
            self._exists = exists
            self._exists_error = exists_error

        def exists(self) -> bool:
            if self._exists_error:
                raise self._exists_error
            return self._exists

    class RepoRoot:
        def __truediv__(self, path: str) -> ArtifactPath:
            return artifacts[path]

    artifacts = {
        "artifacts/ready.md": ArtifactPath(),
        "artifacts/locked.md": ArtifactPath(exists_error=OSError("locked")),
        "artifacts/missing.md": ArtifactPath(exists=False),
    }
    monkeypatch.setattr(fc, "REPO_ROOT", RepoRoot())
    monkeypatch.setattr(fc, "SUMMARY_EVIDENCE_ARTIFACTS", {"custom": tuple(artifacts)})

    assert fc._existing_summary_artifacts("custom") == ["artifacts/ready.md"]


def test_cisco_firmware_report_versions_self_heals_missing_timestamp(monkeypatch, tmp_path) -> None:
    report = tmp_path / "cisco-firmware-inventory-report.md"
    report.write_text(
        "\n".join(
            [
                "- Status: ready",
                "- IOS XE version: 17.9.5",
                "- Bootloader/ROMMON: 17.9",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(fc, "CISCO_FIRMWARE_INVENTORY_REPORT", report)
    monkeypatch.setattr(fc, "_path_mtime", lambda path: None)

    payload = fc._cisco_firmware_report_versions()

    assert payload["status"] == "ready"
    assert payload["ios_xe_version"] == "17.9.5"
    assert payload["checked_at"] is None


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


def test_cisco_management_command_results_satisfy_ios_xe_baseline(monkeypatch, firmware_settings) -> None:
    firmware_settings.cisco_mgmt_configured = True
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("cisco_ios_xe_version", minimum="17.9")))
    record_probe_result(
        "cisco-ansible",
        {
            "provider_id": "cisco-ansible",
            "status": "ok",
            "safe_show_commands": ["show version", "show inventory"],
            "command_results": {
                "show version": {
                    "command": "show version",
                    "version_hint": "17.15.05",
                    "bootloader_rommon_hint": "17.12.1",
                }
            },
        },
    )

    result = fc.get_firmware_compliance(scope="cisco")

    assert result["status"] == "passed"
    assert result["components"][0]["current_version"] == "17.15.05"
    assert result["inventory"]["live_inventory"]["cisco"]["bootloader_rommon"] == "17.12.1"


def test_cisco_management_version_survives_empty_console_cache(monkeypatch, firmware_settings) -> None:
    firmware_settings.cisco_mgmt_configured = True
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("cisco_ios_xe_version", minimum="17.9")))
    record_probe_result(
        "cisco-ansible",
        {
            "provider_id": "cisco-ansible",
            "status": "ok",
            "safe_show_commands": ["show version"],
            "command_results": {"show version": {"version_hint": "17.15.05"}},
        },
    )
    record_probe_result(
        "cisco-console",
        {
            "provider_id": "cisco-console",
            "status": "ok",
            "source": "console-ethernet-readiness",
        },
    )

    result = fc.get_firmware_compliance(scope="full")

    assert result["inventory"]["live_inventory"]["cisco"]["ios_xe_version"] == "17.15.05"
    assert result["components"][0]["current_version"] == "17.15.05"


def test_cisco_management_version_survives_blocked_console_cache(monkeypatch, firmware_settings) -> None:
    firmware_settings.cisco_mgmt_configured = True
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("cisco_ios_xe_version", minimum="17.9")))
    record_probe_result(
        "cisco-ansible",
        {
            "provider_id": "cisco-ansible",
            "status": "ok",
            "command_results": {"show version": {"version_hint": "17.15.05"}},
        },
    )
    record_probe_result(
        "cisco-console",
        {
            "provider_id": "cisco-console",
            "status": "blocked",
            "source": "console",
            "blockers": ["Console port opened but no prompt text was captured."],
        },
    )

    result = fc.get_firmware_compliance(scope="full")

    assert result["inventory"]["live_inventory"]["cisco"]["ios_xe_version"] == "17.15.05"
    assert result["components"][0]["current_version"] == "17.15.05"


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


def test_ontap_target_9171_is_current(monkeypatch, firmware_settings) -> None:
    firmware_settings.netapp_current_ontap_version = "9.17.1"
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "get_netapp_runtime_state", lambda: {"configured": True})
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("netapp_ontap_version", approved=["9.17.1"])))

    result = fc.get_firmware_compliance(scope="netapp")
    path = _path_for(result, "netapp_ontap_version")

    assert path["current_version"] == "9.17.1"
    assert path["target_version"] == "9.17.1"
    assert path["path_status"] == "current"
    assert path["apply_enabled"] is False


def test_cisco_ios_xe_current_equals_target_is_current(monkeypatch, firmware_settings) -> None:
    firmware_settings.cisco_mgmt_configured = False
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("cisco_ios_xe_version", approved=["17.15.05"])))
    record_probe_result("cisco-console", {"provider_id": "cisco-console", "status": "ok", "ios_xe_version": "17.15.05"})

    result = fc.get_firmware_compliance(scope="cisco")
    path = _path_for(result, "cisco_ios_xe_version")

    assert path["current_version"] == "17.15.05"
    assert path["target_version"] == "17.15.05"
    assert path["path_status"] == "current"


def test_ilo_current_equals_target_is_current(monkeypatch, firmware_settings) -> None:
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("hpe_ilo_firmware", approved=["3.19"])))
    record_probe_result("ilo-redfish", {"provider_id": "ilo-redfish", "status": "ok", "managers": [{"FirmwareVersion": "iLO 5 v3.19"}]})

    result = fc.get_firmware_compliance(scope="hpe")
    path = _path_for(result, "hpe_ilo_firmware")

    assert path["current_version"] == "iLO 5 v3.19"
    assert path["target_version"] == "3.19"
    assert path["path_status"] == "current"


def test_missing_baseline_becomes_manual_review(monkeypatch, firmware_settings) -> None:
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("hpe_bios_version", unknown_policy="warning")))
    record_probe_result("ilo-redfish", {"provider_id": "ilo-redfish", "status": "ok", "systems": [{"BiosVersion": "U32 v3.30"}]})

    result = fc.get_firmware_compliance(scope="hpe")
    path = _path_for(result, "hpe_bios_version")

    assert path["current_version"] == "U32 v3.30"
    assert path["target_version"] is None
    assert path["path_status"] == "manual_review"
    assert "approved HPE baseline" in path["missing_evidence"]


def test_missing_package_blocks_upgrade_apply(monkeypatch, firmware_settings) -> None:
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("hpe_ilo_firmware", approved=["3.19"])))
    record_probe_result("ilo-redfish", {"provider_id": "ilo-redfish", "status": "ok", "managers": [{"FirmwareVersion": "2.80"}]})

    result = fc.get_firmware_compliance(scope="hpe")
    path = _path_for(result, "hpe_ilo_firmware")

    assert path["path_status"] == "blocked"
    assert path["package_available"] is False
    assert path["apply_enabled"] is False
    assert "matching local package" in path["disabled_reason"]


def test_unknown_current_version_requires_scan(monkeypatch, firmware_settings) -> None:
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("hpe_ilo_firmware", approved=["3.19"])))

    result = fc.get_firmware_compliance(scope="hpe")
    path = _path_for(result, "hpe_ilo_firmware")

    assert path["path_status"] == "unknown"
    assert path["apply_enabled"] is False
    assert "ilo.firmware-inventory" in path["next_action"]


def test_staged_path_renders_intermediate_versions(monkeypatch, firmware_settings, tmp_path) -> None:
    firmware_settings.media_inventory_dirs = (str(tmp_path),)
    (tmp_path / "ilo5_319.fwpkg").write_bytes(b"firmware")
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "_media_directories", lambda: [tmp_path])
    monkeypatch.setattr(
        fc,
        "load_firmware_baseline",
        lambda: _baseline(
            _component(
                "hpe_ilo_firmware",
                approved=["3.19"],
                required_intermediate_versions=["3.00"],
            )
        ),
    )
    record_probe_result("ilo-redfish", {"provider_id": "ilo-redfish", "status": "ok", "managers": [{"FirmwareVersion": "2.80"}]})

    result = fc.get_firmware_compliance(scope="hpe")
    path = _path_for(result, "hpe_ilo_firmware")

    assert path["path_status"] == "staged"
    assert path["required_intermediate_versions"] == ["3.00"]
    assert path["package_available"] is True
    assert path["apply_enabled"] is False


def test_stale_evidence_does_not_enable_upgrade_apply(monkeypatch, firmware_settings, tmp_path) -> None:
    firmware_settings.cisco_mgmt_configured = False
    firmware_settings.media_inventory_dirs = (str(tmp_path),)
    (tmp_path / "cat9k_iosxe.17.15.05.SPA.bin").write_bytes(b"firmware")
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "_media_directories", lambda: [tmp_path])
    monkeypatch.setattr(
        fc,
        "_cisco_firmware_report_versions",
        lambda: {
            "status": "ok",
            "source": "console-user-exec-show-version",
            "ios_xe_version": "16.12.05",
            "bootloader_rommon": None,
            "checked_at": "2020-01-01T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("cisco_ios_xe_version", approved=["17.15.05"])))

    result = fc.get_firmware_compliance(scope="cisco")
    path = _path_for(result, "cisco_ios_xe_version")

    assert path["path_status"] == "manual_review"
    assert path["package_available"] is True
    assert path["freshness"] == "stale"
    assert path["apply_enabled"] is False
    assert "not fresh live inventory" in path["disabled_reason"]


def test_upgrade_path_exposes_selected_repo_media_file_and_candidates(
    monkeypatch,
    firmware_settings,
    tmp_path,
) -> None:
    media_root = tmp_path / "artifacts" / "Media"
    media_root.mkdir(parents=True)
    selected = media_root / "cat9k_iosxe.17.15.05.SPA.bin"
    alternate = media_root / "cat9k_iosxe.17.12.01.SPA.bin"
    selected.write_bytes(b"firmware")
    alternate.write_bytes(b"firmware")
    firmware_settings.cisco_mgmt_configured = False
    firmware_settings.media_inventory_dirs = (str(media_root),)
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "_media_directories", lambda: [media_root])
    monkeypatch.setattr(mi, "DEFAULT_MEDIA_ROOT", media_root)
    monkeypatch.setattr(fc, "load_firmware_baseline", lambda: _baseline(_component("cisco_ios_xe_version", approved=["17.15.05"])))
    record_probe_result("cisco-console", {"provider_id": "cisco-console", "status": "ok", "ios_xe_version": "16.12.05"})

    result = fc.get_firmware_compliance(scope="cisco")
    path = _path_for(result, "cisco_ios_xe_version")

    assert path["equipment_label"] == "Cisco"
    assert path["selected_file_name"] == "cat9k_iosxe.17.15.05.SPA.bin"
    assert path["selected_file_path"] == str(selected.resolve())
    assert path["selection_source"] == "auto"
    assert [candidate["file_name"] for candidate in path["candidate_files"]] == [
        "cat9k_iosxe.17.15.05.SPA.bin",
        "cat9k_iosxe.17.12.01.SPA.bin",
    ]
    assert path["candidate_files"][0]["detected_vendor"] == "Cisco"
    assert path["candidate_files"][0]["detected_product"] == "cisco-ios-xe"


def test_hpe_service_pack_media_is_candidate_for_smart_array(
    monkeypatch,
    firmware_settings,
    tmp_path,
) -> None:
    media_root = tmp_path / "artifacts" / "Media"
    media_root.mkdir(parents=True)
    spp = media_root / "Service Pack for ProLiant 2024.03.iso"
    spp.write_bytes(b"spp")
    firmware_settings.media_inventory_dirs = (str(media_root),)
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "_media_directories", lambda: [media_root])
    monkeypatch.setattr(mi, "DEFAULT_MEDIA_ROOT", media_root)
    monkeypatch.setattr(
        fc,
        "load_firmware_baseline",
        lambda: _baseline(_component("hpe_smart_array_firmware", unknown_policy="warning")),
    )
    record_probe_result(
        "ilo-redfish",
        {
            "provider_id": "ilo-redfish",
            "status": "ok",
            "storage": {
                "controllers": [
                    {
                        "FirmwareVersion": "52.26.3-5379",
                        "Model": "HPE Smart Array P408i-a SR Gen10",
                    }
                ]
            },
        },
    )

    result = fc.get_firmware_compliance(scope="hpe")
    path = _path_for(result, "hpe_smart_array_firmware")

    assert path["current_version"] == "52.26.3-5379"
    assert path["selected_file_name"] == "Service Pack for ProLiant 2024.03.iso"
    assert path["selected_file_path"] == str(spp.resolve())
    assert path["candidate_files"][0]["detected_product"] == "hpe-spp"
    assert path["selection_source"] == "auto"


def test_current_gen10_spp_media_is_candidate_for_all_hpe_paths(
    monkeypatch,
    firmware_settings,
    tmp_path,
) -> None:
    media_root = tmp_path / "artifacts" / "Media"
    media_root.mkdir(parents=True)
    gen11_spp = media_root / "P92600_001_gen11spp-2026.03.00.00-Gen11SPP2026030000.2026_0324.8.iso"
    gen11_spp.write_bytes(b"gen11 spp")
    spp = media_root / "P95170_001_gen10spp-2026.05.00.00-SPP2026050000.2026_0527.9.iso"
    spp.write_bytes(b"spp")
    firmware_settings.media_inventory_dirs = (str(media_root),)
    monkeypatch.setattr(fc, "settings", firmware_settings)
    monkeypatch.setattr(fc, "_media_directories", lambda: [media_root])
    monkeypatch.setattr(mi, "DEFAULT_MEDIA_ROOT", media_root)
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
            "managers": [{"FirmwareVersion": "iLO 5 v3.10"}],
            "systems": [{"BiosVersion": "U32 v3.30 (07/31/2024)"}],
            "storage": {"controllers": [{"FirmwareVersion": "1.98"}]},
        },
    )

    result = fc.get_firmware_compliance(scope="hpe")

    for component_id in ("hpe_ilo_firmware", "hpe_bios_version", "hpe_smart_array_firmware"):
        path = _path_for(result, component_id)
        assert "P95170_001_gen10spp-2026.05.00.00-SPP2026050000.2026_0527.9.iso" in [
            candidate["file_name"] for candidate in path["candidate_files"]
        ]
        assert path["candidate_files"][0]["file_name"] == "P95170_001_gen10spp-2026.05.00.00-SPP2026050000.2026_0527.9.iso"
        assert path["selected_file_path"] == str(spp.resolve())
        assert path["candidate_files"][0]["detected_product"] == "hpe-spp"


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


def test_corrupt_local_waiver_is_invalid_artifact(monkeypatch, firmware_settings) -> None:
    monkeypatch.setattr(fc, "settings", firmware_settings)
    fc.LOCAL_WAIVER_PATH.parent.mkdir(parents=True, exist_ok=True)
    fc.LOCAL_WAIVER_PATH.write_text("{not valid json", encoding="utf-8")

    result = fc.load_firmware_waiver()

    assert result["source"] == "artifact"
    assert result["configured"] is False
    assert result["active"] is False


def test_unavailable_local_waiver_path_falls_back_to_empty_env(monkeypatch, firmware_settings) -> None:
    monkeypatch.setattr(fc, "settings", firmware_settings)
    original_exists = type(fc.LOCAL_WAIVER_PATH).exists

    def unavailable_exists(path) -> bool:  # noqa: ANN001
        if path == fc.LOCAL_WAIVER_PATH:
            raise OSError("waiver path unavailable")
        return original_exists(path)

    monkeypatch.setattr(type(fc.LOCAL_WAIVER_PATH), "exists", unavailable_exists)

    result = fc.load_firmware_waiver()

    assert result["source"] == "env"
    assert result["configured"] is False
    assert result["active"] is False


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
    assert firmware_settings.ilo_test_password not in str(result["upgrade_paths"])


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


def test_missing_path_evidence_dedupes_preserving_order() -> None:
    missing = fc._missing_path_evidence(
        current_version=None,
        target_version=None,
        baseline_component=None,
        component_id="netapp_disk_firmware",
    )

    assert missing == [
        "current version",
        "target baseline",
        "component firmware inventory",
        "component firmware baseline",
    ]


def test_summary_path_rollup_dedupes_versions_and_prechecks() -> None:
    rollup = fc._summary_path_rollup(
        [
            {
                "path_status": "staged",
                "package_available": False,
                "required_intermediate_versions": ["3.00", "3.10"],
                "prechecks_required": ["backup", "maintenance window"],
                "estimated_impact": "Reboot required.",
            },
            {
                "path_status": "direct",
                "package_available": True,
                "package_name": "ilo5_319.fwpkg",
                "required_intermediate_versions": ["3.00", "3.20"],
                "prechecks_required": ["backup", "console access"],
                "estimated_impact": "Short outage.",
            },
        ]
    )

    assert rollup["required_intermediate_versions"] == ["3.00", "3.10", "3.20"]
    assert rollup["prechecks_required"] == ["backup", "maintenance window", "console access"]
    assert rollup["path_status"] == "staged"


def _summary_for(summaries: list[dict], device_id: str) -> dict:
    return next(summary for summary in summaries if summary["device_id"] == device_id)


def _path_for(payload: dict, component_id: str) -> dict:
    return next(path for path in payload["upgrade_paths"] if path["component_id"] == component_id)


def _baseline(*components: dict) -> dict:
    return {"baseline_id": "test", "components": list(components)}


def _component(
    component_id: str,
    *,
    minimum: str | None = None,
    approved: list[str] | None = None,
    required_intermediate_versions: list[str] | None = None,
    unknown_policy: str = "blocked",
) -> dict:
    return {
        "id": component_id,
        "device": component_id.split("_", 1)[0],
        "label": component_id,
        "minimum": minimum,
        "approved": approved or [],
        "required_intermediate_versions": required_intermediate_versions or [],
        "unknown_policy": unknown_policy,
        "next_action": "Review firmware.",
    }
