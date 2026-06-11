from __future__ import annotations

import json
import os
from pathlib import Path

from app.services import esxi_boot_workflow, esxi_install_readiness


def test_eject_virtual_media_posts_eject_action_and_writes_report(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    monkeypatch.setattr(esxi_boot_workflow, "_action_blockers", lambda *_args: [])
    monkeypatch.setattr(esxi_boot_workflow, "firmware_gate_blockers", lambda *_args: [])
    monkeypatch.setattr(
        esxi_boot_workflow,
        "_latest_virtual_media_path",
        lambda: "/redfish/v1/Managers/1/VirtualMedia/2/",
    )

    get_calls: list[str] = []
    post_calls: list[tuple[str, dict]] = []

    def fake_get(path: str) -> dict:
        get_calls.append(path)
        if len(get_calls) == 1:
            return {
                "status_code": 200,
                "body": {
                    "Id": "2",
                    "Name": "VirtualMedia",
                    "Inserted": True,
                    "Image": "http://example.invalid/esxi.iso",
                    "MediaTypes": ["CD", "DVD"],
                    "ConnectedVia": "URI",
                    "Actions": {
                        "#VirtualMedia.EjectMedia": {
                            "target": "/redfish/v1/Managers/1/VirtualMedia/2/Actions/VirtualMedia.EjectMedia/"
                        }
                    },
                },
            }
        return {
            "status_code": 200,
            "body": {
                "Id": "2",
                "Name": "VirtualMedia",
                "Inserted": False,
                "Image": None,
                "MediaTypes": ["CD", "DVD"],
                "ConnectedVia": "NotConnected",
                "Actions": {},
            },
        }

    def fake_post(path: str, payload: dict) -> dict:
        post_calls.append((path, payload))
        return {"method": "POST", "path": path, "status_code": 200, "request": payload, "response": {}}

    monkeypatch.setattr(esxi_boot_workflow, "_get_redfish_resource", fake_get)
    monkeypatch.setattr(esxi_boot_workflow, "_post_redfish", fake_post)

    result = esxi_boot_workflow.eject_esxi_virtual_media()

    assert result["status"] == "ejected"
    assert result["ejected"] is True
    assert post_calls == [
        ("/redfish/v1/Managers/1/VirtualMedia/2/Actions/VirtualMedia.EjectMedia/", {})
    ]
    assert esxi_boot_workflow.VIRTUAL_MEDIA_EJECT_REPORT.exists()
    saved_state = json.loads(esxi_boot_workflow.VIRTUAL_MEDIA_STATE.read_text(encoding="utf-8"))
    assert saved_state["status"] == "ejected"


def test_installer_detection_reports_installed_esxi_when_media_ejected_and_boot_disabled() -> None:
    detection = esxi_boot_workflow._installer_detection(
        {
            "status_code": 200,
            "body": {
                "PowerState": "On",
                "Boot": {
                    "BootSourceOverrideEnabled": "Disabled",
                    "BootSourceOverrideTarget": "None",
                    "BootSourceOverrideMode": "UEFI",
                },
                "Oem": {
                    "Hpe": {
                        "HostOS": {
                            "OsName": "VMware ESXi",
                            "OsVersion": "8.0.3 Build-24859861",
                            "OsType": 25,
                        }
                    }
                },
            },
        },
        {
            "status_code": 200,
            "body": {
                "Inserted": False,
                "Image": None,
                "ConnectedVia": "NotConnected",
            },
        },
    )

    assert detection["status"] == "installed_esxi"


def test_eject_virtual_media_writes_report_when_before_state_unreachable(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    monkeypatch.setattr(esxi_boot_workflow, "_action_blockers", lambda *_args: [])
    monkeypatch.setattr(esxi_boot_workflow, "firmware_gate_blockers", lambda *_args: [])
    monkeypatch.setattr(
        esxi_boot_workflow,
        "_latest_virtual_media_path",
        lambda: "/redfish/v1/Managers/1/VirtualMedia/2/",
    )
    monkeypatch.setattr(
        esxi_boot_workflow,
        "_safe_get",
        lambda _path: {"status_code": None, "error_class": "ConnectTimeout", "error": "timed out"},
    )

    result = esxi_boot_workflow.eject_esxi_virtual_media()

    assert result["status"] == "blocked"
    assert "not reachable before eject" in result["blockers"][0]
    assert esxi_boot_workflow.VIRTUAL_MEDIA_EJECT_REPORT.exists()


def test_boot_workflow_summary_prefers_newer_virtual_media_eject_report(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    esxi_boot_workflow.VIRTUAL_MEDIA_REPORT.write_text(
        "# ESXi Virtual Media Report\n\n## Summary\n\n- status: inserted\n- message: inserted\n",
        encoding="utf-8",
    )
    esxi_boot_workflow.VIRTUAL_MEDIA_EJECT_REPORT.write_text(
        "# ESXi Virtual Media Eject Report\n\n## Summary\n\n- status: ejected\n- message: ejected\n",
        encoding="utf-8",
    )
    os.utime(esxi_boot_workflow.VIRTUAL_MEDIA_REPORT, (1, 1))
    os.utime(esxi_boot_workflow.VIRTUAL_MEDIA_EJECT_REPORT, (2, 2))

    summary = esxi_boot_workflow.esxi_boot_workflow_summary()

    assert summary["virtual_media"]["status"] == "ejected"
    assert summary["virtual_media"]["report"] == "artifacts/codex-runs/esxi-virtual-media-eject-report.md"


def test_install_readiness_uses_installed_esxi_state_after_cleanup() -> None:
    boot_workflow = {
        "one_time_boot": {"status": "set"},
        "reset_boot": {"status": "installed_esxi"},
    }

    milestones = esxi_install_readiness._milestones(
        "ready",
        {"supported": True},
        {"one_time_boot_supported": True, "boot_source_override_enabled": "Disabled"},
        {"ready": True},
        {"status": "succeeded"},
        boot_workflow,
    )

    statuses = {item["id"]: item["status"] for item in milestones}
    assert statuses["one-time-boot"] == "ready_to_run"
    assert statuses["esxi-iso-boots"] == "installed_esxi"
    assert esxi_install_readiness._next_safe_action(
        "ready",
        boot_workflow,
    ) == "Installed ESXi is running; no installer boot override is queued."


def test_reset_for_installer_boot_powers_on_when_server_is_off(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    monkeypatch.setattr(esxi_boot_workflow, "_action_blockers", lambda *_args: [])
    monkeypatch.setattr(esxi_boot_workflow, "firmware_gate_blockers", lambda *_args: [])
    monkeypatch.setattr(
        esxi_boot_workflow,
        "insert_esxi_virtual_media",
        lambda: {"status": "inserted", "device": {"path": "/redfish/v1/Managers/1/VirtualMedia/2/"}},
    )
    monkeypatch.setattr(esxi_boot_workflow, "set_esxi_one_time_boot", lambda: {"status": "set"})

    reset_types: list[str] = []

    def fake_reset(reset_type: str) -> dict:
        reset_types.append(reset_type)
        return {
            "method": "POST",
            "path": "/redfish/v1/Systems/1/Actions/ComputerSystem.Reset/",
            "status_code": 200,
            "request": {"ResetType": reset_type},
            "response": {},
        }

    def fake_safe_get(path: str) -> dict:
        if path == esxi_boot_workflow.SYSTEM_PATH:
            return {
                "status_code": 200,
                "body": {
                    "PowerState": "Off",
                    "Boot": {
                        "BootSourceOverrideEnabled": "Once",
                        "BootSourceOverrideTarget": "Cd",
                    },
                },
            }
        return {"status_code": 200, "body": {"Inserted": True, "Image": "http://example.invalid/esxi.iso"}}

    monkeypatch.setattr(esxi_boot_workflow, "_post_system_reset", fake_reset)
    monkeypatch.setattr(esxi_boot_workflow, "_safe_get", fake_safe_get)
    monkeypatch.setattr(
        esxi_boot_workflow,
        "_wait_for_ilo",
        lambda *, require_powered=False: {"reachable": True, "power_state": "On", "require_powered": require_powered},
    )
    monkeypatch.setattr(esxi_boot_workflow, "_installer_detection", lambda *_args: {"status": "detected", "warnings": []})

    result = esxi_boot_workflow.reset_for_esxi_installer_boot()

    assert result["status"] == "boot_requested"
    assert reset_types == ["On"]
    assert result["wait"]["require_powered"] is True
    assert not result["blockers"]


def _redirect_reports(monkeypatch, tmp_path: Path) -> None:
    repo_root = tmp_path
    codex_runs = repo_root / "artifacts" / "codex-runs"
    codex_runs.mkdir(parents=True)
    monkeypatch.setattr(esxi_boot_workflow, "REPO_ROOT", repo_root)
    monkeypatch.setattr(esxi_boot_workflow, "CODEX_RUN_DIR", codex_runs)
    monkeypatch.setattr(esxi_boot_workflow, "MEDIA_URL_REPORT", codex_runs / "esxi-media-url-report.md")
    monkeypatch.setattr(esxi_boot_workflow, "VIRTUAL_MEDIA_REPORT", codex_runs / "esxi-virtual-media-report.md")
    monkeypatch.setattr(esxi_boot_workflow, "VIRTUAL_MEDIA_EJECT_REPORT", codex_runs / "esxi-virtual-media-eject-report.md")
    monkeypatch.setattr(esxi_boot_workflow, "ONE_TIME_BOOT_REPORT", codex_runs / "esxi-one-time-boot-report.md")
    monkeypatch.setattr(esxi_boot_workflow, "INSTALLER_BOOT_REPORT", codex_runs / "esxi-installer-boot-report.md")
    monkeypatch.setattr(esxi_boot_workflow, "VIRTUAL_MEDIA_STATE", codex_runs / "esxi-virtual-media-state.json")
