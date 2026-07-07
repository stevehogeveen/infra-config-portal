from __future__ import annotations

import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from app.core.config import settings
from app.providers.action_policy import ActionCategory
from app.services import esxi_boot_workflow, esxi_install_readiness, hpe_raid


def test_prepare_esxi_media_url_keeps_scalar_firmware_blocker_whole(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    monkeypatch.setattr(esxi_boot_workflow, "firmware_gate_blockers", lambda *_args: " firmware blocker ")

    result = esxi_boot_workflow.prepare_esxi_media_url()

    assert result["status"] == "blocked"
    assert result["blockers"] == ["firmware blocker"]
    assert not any(blocker == "f" for blocker in result["blockers"])
    assert esxi_boot_workflow.MEDIA_URL_REPORT.exists()


def test_insert_virtual_media_keeps_scalar_policy_and_firmware_blockers_whole(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    monkeypatch.setattr(esxi_boot_workflow, "_action_blockers", lambda *_args: [" policy blocker "])
    monkeypatch.setattr(esxi_boot_workflow, "firmware_gate_blockers", lambda *_args: " firmware blocker ")

    result = esxi_boot_workflow.insert_esxi_virtual_media()

    assert result["status"] == "blocked"
    assert " policy blocker " in result["blockers"]
    assert "firmware blocker" in result["blockers"]
    assert not any(blocker == "f" for blocker in result["blockers"])


def test_action_blockers_keeps_scalar_policy_blocker_whole(monkeypatch) -> None:
    monkeypatch.setattr(
        esxi_boot_workflow,
        "current_lab_action_policy",
        lambda _mode: SimpleNamespace(action_blockers=lambda _action_id, _category: " policy blocker "),
    )

    blockers = esxi_boot_workflow._action_blockers("ilo.virtual-media", ActionCategory.VIRTUAL_MEDIA)

    assert blockers == ["policy blocker"]


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
    assert not list(esxi_boot_workflow.CODEX_RUN_DIR.glob("*.tmp"))
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
    assert not list(esxi_boot_workflow.CODEX_RUN_DIR.glob("*.tmp"))


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


def test_report_summary_self_heals_unreadable_report(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    report = esxi_boot_workflow.VIRTUAL_MEDIA_REPORT
    report.write_text(
        "# ESXi Virtual Media Report\n\n## Summary\n\n- status: inserted\n- message: inserted\n",
        encoding="utf-8",
    )
    original_read_text = Path.read_text

    def flaky_read_text(path: Path, *args, **kwargs) -> str:
        if path == report:
            raise OSError("locked")
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky_read_text)

    assert esxi_boot_workflow._report_summary(report) == {
        "status": "not_run",
        "report": "artifacts/codex-runs/esxi-virtual-media-report.md",
    }


def test_report_summary_replaces_bad_encoding(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    report = esxi_boot_workflow.VIRTUAL_MEDIA_REPORT
    report.write_bytes(
        b"# ESXi Virtual Media Report\n\n## Summary\n\n- status: inserted\n- message: inserted\xff\n"
    )

    summary = esxi_boot_workflow._report_summary(report)

    assert summary == {
        "status": "inserted",
        "message": "inserted\ufffd",
        "report": "artifacts/codex-runs/esxi-virtual-media-report.md",
    }


def test_report_summary_self_heals_report_probe_error(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    report = esxi_boot_workflow.VIRTUAL_MEDIA_REPORT
    report.write_text(
        "# ESXi Virtual Media Report\n\n## Summary\n\n- status: inserted\n- message: inserted\n",
        encoding="utf-8",
    )
    original_exists = Path.exists

    def flaky_exists(path: Path) -> bool:
        if path == report:
            raise OSError("probe failed")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    assert esxi_boot_workflow._report_summary(report) == {
        "status": "not_run",
        "report": "artifacts/codex-runs/esxi-virtual-media-report.md",
    }


def test_latest_report_summary_skips_reports_that_disappear(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    older = esxi_boot_workflow.VIRTUAL_MEDIA_REPORT
    disappearing = esxi_boot_workflow.VIRTUAL_MEDIA_EJECT_REPORT
    older.write_text(
        "# ESXi Virtual Media Report\n\n## Summary\n\n- status: inserted\n- message: inserted\n",
        encoding="utf-8",
    )
    disappearing.write_text(
        "# ESXi Virtual Media Eject Report\n\n## Summary\n\n- status: ejected\n- message: ejected\n",
        encoding="utf-8",
    )
    os.utime(older, (1, 1))
    os.utime(disappearing, (2, 2))
    original_stat = Path.stat

    def flaky_stat(path: Path, *args, **kwargs) -> os.stat_result:
        if path == disappearing:
            raise FileNotFoundError("gone")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky_stat)

    summary = esxi_boot_workflow._latest_report_summary(older, disappearing)

    assert summary["status"] == "inserted"
    assert summary["report"] == "artifacts/codex-runs/esxi-virtual-media-report.md"


def test_latest_virtual_media_path_ignores_corrupt_state(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    esxi_boot_workflow.VIRTUAL_MEDIA_STATE.write_text("{not valid json", encoding="utf-8")

    assert esxi_boot_workflow._latest_virtual_media_path() is None


def test_insert_virtual_media_writes_state_atomically(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    monkeypatch.setattr(esxi_boot_workflow, "_action_blockers", lambda *_args: [])
    monkeypatch.setattr(esxi_boot_workflow, "firmware_gate_blockers", lambda *_args: [])
    monkeypatch.setattr(
        esxi_boot_workflow,
        "prepare_esxi_media_url",
        lambda: {
            "status": "ready",
            "selected_iso": {"name": "esxi.iso"},
            "media_url": "http://127.0.0.1:8088/esxi.iso",
            "blockers": [],
            "warnings": [],
        },
    )
    monkeypatch.setattr(
        esxi_boot_workflow,
        "_select_virtual_media_device",
        lambda: {"path": "/redfish/v1/Managers/1/VirtualMedia/2/"},
    )
    monkeypatch.setattr(
        esxi_boot_workflow,
        "_get_redfish_resource",
        lambda _path: {
            "status_code": 200,
            "body": {
                "Inserted": True,
                "Image": "http://127.0.0.1:8088/esxi.iso",
                "ConnectedVia": "URI",
            },
        },
    )
    monkeypatch.setattr(
        esxi_boot_workflow,
        "_post_virtual_media_action",
        lambda device, media_url: {"status_code": 200, "device": device, "media_url": media_url},
    )

    result = esxi_boot_workflow.insert_esxi_virtual_media()

    assert result["status"] == "inserted"
    saved_state = json.loads(esxi_boot_workflow.VIRTUAL_MEDIA_STATE.read_text(encoding="utf-8"))
    assert saved_state["status"] == "inserted"
    assert saved_state["device"]["path"] == "/redfish/v1/Managers/1/VirtualMedia/2/"
    assert not list(esxi_boot_workflow.CODEX_RUN_DIR.glob("*.tmp"))


def test_one_time_boot_writes_boot_snapshots_atomically(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    monkeypatch.setattr(esxi_boot_workflow, "_action_blockers", lambda *_args: [])
    monkeypatch.setattr(esxi_boot_workflow, "firmware_gate_blockers", lambda *_args: [])
    monkeypatch.setattr(
        esxi_boot_workflow,
        "_get_redfish_resource",
        lambda _path: {
            "status_code": 200,
            "body": {
                "Boot": {
                    "BootSourceOverrideEnabled": "Disabled",
                    "BootSourceOverrideTarget": "None",
                    "BootSourceOverrideTarget@Redfish.AllowableValues": ["Cd", "Usb", "Hdd"],
                }
            },
        },
    )
    monkeypatch.setattr(
        esxi_boot_workflow,
        "_patch_system_boot",
        lambda payload: {"status_code": 200, "request": payload},
    )

    result = esxi_boot_workflow.set_esxi_one_time_boot()

    assert result["status"] == "blocked"
    before = json.loads(esxi_boot_workflow.BOOT_SETTINGS_BEFORE.read_text(encoding="utf-8"))
    after = json.loads(esxi_boot_workflow.BOOT_SETTINGS_AFTER.read_text(encoding="utf-8"))
    assert before["boot_source_override_enabled"] == "Disabled"
    assert after["boot_source_override_target"] == "None"
    assert not list(esxi_boot_workflow.CODEX_RUN_DIR.glob("*.tmp"))


def test_prepare_esxi_media_url_writes_report_atomically(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    iso = tmp_path / "VMware-ESXi-8.0.3.iso"
    iso.write_bytes(b"iso")
    monkeypatch.setattr(esxi_boot_workflow, "firmware_gate_blockers", lambda *_args: [])
    monkeypatch.setattr(
        esxi_boot_workflow,
        "settings",
        SimpleNamespace(media_inventory_dirs=(str(tmp_path),)),
    )
    monkeypatch.setenv("ESXI_MEDIA_BASE_URL", "http://example.invalid/media")
    monkeypatch.setattr(
        esxi_boot_workflow,
        "_validate_media_url",
        lambda url, expected_size: {
            "reachable": True,
            "status_code": 200,
            "content_length": expected_size,
            "url": url,
        },
    )

    result = esxi_boot_workflow.prepare_esxi_media_url()

    assert result["status"] == "ready"
    assert result["media_url"] == "http://example.invalid/media/VMware-ESXi-8.0.3.iso"
    assert esxi_boot_workflow.MEDIA_URL_REPORT.read_text(encoding="utf-8").strip()
    assert not list(esxi_boot_workflow.CODEX_RUN_DIR.glob("*.tmp"))


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


def test_install_readiness_raid_snapshot_does_not_wait_for_reset(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(hpe_raid, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(hpe_raid, "PENDING_REPORT", tmp_path / "artifacts" / "codex-runs" / "hpe-raid-pending-report.md")
    monkeypatch.setattr(esxi_install_readiness, "PENDING_REPORT", hpe_raid.PENDING_REPORT)
    calls = 0

    def fake_pending_report(_session) -> dict:
        nonlocal calls
        calls += 1
        return {
            "message": "HPE SmartStorage current/settings state cannot be read.",
            "pending": {
                "live_matches_expected": False,
                "pending_config_exists": False,
                "reset_required": False,
                "smartstorage_reads_available": False,
            },
        }

    monkeypatch.setattr(esxi_install_readiness, "write_hpe_raid_pending_report", fake_pending_report)

    snapshot = esxi_install_readiness._raid_validation_snapshot(object())

    assert calls == 1
    assert snapshot["status"] == "blocked"
    assert snapshot["report"] == "artifacts/codex-runs/hpe-raid-pending-report.md"
    assert snapshot["validation"]["reset_required"] is False
    assert snapshot["validation"]["smartstorage_reads_available"] is False


def test_hpe_raid_report_paths_use_posix_separators(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(hpe_raid, "REPO_ROOT", tmp_path)

    assert hpe_raid._rel(tmp_path / "artifacts" / "codex-runs" / "hpe-raid-apply-report.md") == "artifacts/codex-runs/hpe-raid-apply-report.md"


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


def test_media_server_uses_current_python_and_platform_process_group(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    monkeypatch.delenv("PYTHON", raising=False)

    port_checks = iter([False, True])
    popen_calls: list[dict] = []

    class FakeProcess:
        pid = 4242

    def fake_popen(command: list[str], **kwargs) -> FakeProcess:
        popen_calls.append({"command": command, "kwargs": kwargs})
        return FakeProcess()

    monkeypatch.setattr(esxi_boot_workflow, "_port_open", lambda *_args: next(port_checks))
    monkeypatch.setattr(esxi_boot_workflow.subprocess, "Popen", fake_popen)

    result = esxi_boot_workflow._ensure_media_server(tmp_path, "127.0.0.1", 8765)

    assert result["status"] == "started"
    assert result["pid"] == 4242
    assert result["log"] == "artifacts/codex-runs/esxi-media-http-server.log"
    assert esxi_boot_workflow.MEDIA_SERVER_PID.read_text(encoding="utf-8") == "4242"
    assert not list(esxi_boot_workflow.CODEX_RUN_DIR.glob("*.tmp"))
    assert popen_calls[0]["command"][0] == sys.executable
    if os.name == "nt":
        assert popen_calls[0]["kwargs"]["creationflags"] == esxi_boot_workflow.subprocess.CREATE_NEW_PROCESS_GROUP
        assert "start_new_session" not in popen_calls[0]["kwargs"]
    else:
        assert popen_calls[0]["kwargs"]["start_new_session"] is True
        assert "creationflags" not in popen_calls[0]["kwargs"]


def test_install_readiness_writes_report_atomically(monkeypatch, tmp_path: Path) -> None:
    codex_runs = tmp_path / "artifacts" / "codex-runs"
    codex_runs.mkdir(parents=True)
    report_path = codex_runs / "esxi-install-readiness-report.md"
    pending_report = codex_runs / "hpe-raid-pending-report.md"
    monkeypatch.setattr(hpe_raid, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(hpe_raid, "PENDING_REPORT", pending_report)
    monkeypatch.setattr(esxi_install_readiness, "CODEX_RUN_DIR", codex_runs)
    monkeypatch.setattr(esxi_install_readiness, "ESXI_INSTALL_READINESS_REPORT", report_path)
    monkeypatch.setattr(esxi_install_readiness, "PENDING_REPORT", pending_report)
    monkeypatch.setattr(
        esxi_install_readiness,
        "write_hpe_raid_pending_report",
        lambda _session: {
            "message": "RAID live layout matches saved intent.",
            "pending": {
                "live_matches_expected": True,
                "pending_config_exists": True,
                "reset_required": False,
                "smartstorage_reads_available": True,
            },
        },
    )
    monkeypatch.setattr(
        esxi_install_readiness,
        "esxi_boot_workflow_summary",
        lambda: {"status": "not_started", "installer_boot": {"status": "not_started"}},
    )
    monkeypatch.setattr(
        esxi_install_readiness,
        "get_media_inventory",
        lambda: SimpleNamespace(
            model_dump=lambda: {
                "mode": "local",
                "items": [
                    {
                        "placeholder_name": "VMware-ESXi-8.0.iso",
                        "category": "iso",
                        "product_hints": ["esxi"],
                        "version_hint": "8.0",
                    }
                ],
                "warnings": [],
            }
        ),
    )

    def fake_safe_get(path: str, requests: list[dict]) -> dict:
        responses = {
            "/redfish/v1/": {
                "status_code": 200,
                "body": {"Managers": {"@odata.id": "/redfish/v1/Managers/"}},
            },
            esxi_install_readiness.SYSTEM_PATH: {
                "status_code": 200,
                "body": {
                    "Model": "ProLiant",
                    "PowerState": "On",
                    "Status": {"Health": "OK"},
                    "BiosVersion": "U32",
                    "Boot": {
                        "BootSourceOverrideEnabled": "Disabled",
                        "BootSourceOverrideTarget": "Cd",
                        "BootSourceOverrideEnabled@Redfish.AllowableValues": ["Disabled", "Once"],
                        "BootSourceOverrideTarget@Redfish.AllowableValues": ["Cd", "Usb"],
                    },
                    "Bios": {"@odata.id": "/redfish/v1/Systems/1/Bios/"},
                },
            },
            "/redfish/v1/Managers/": {
                "status_code": 200,
                "body": {"Members": [{"@odata.id": "/redfish/v1/Managers/1/"}]},
            },
            "/redfish/v1/Managers/1/": {
                "status_code": 200,
                "body": {"VirtualMedia": {"@odata.id": "/redfish/v1/Managers/1/VirtualMedia/"}},
            },
            "/redfish/v1/Managers/1/VirtualMedia/": {
                "status_code": 200,
                "body": {"Members": [{"@odata.id": "/redfish/v1/Managers/1/VirtualMedia/2/"}]},
            },
            "/redfish/v1/Managers/1/VirtualMedia/2/": {
                "status_code": 200,
                "body": {"Id": "2", "Name": "VirtualMedia", "MediaTypes": ["CD", "DVD"], "Actions": {}},
            },
            "/redfish/v1/Systems/1/Bios/": {
                "status_code": 200,
                "body": {
                    "Attributes": {"BootMode": "Uefi"},
                    "@Redfish.Settings": {"@odata.id": "/redfish/v1/Systems/1/Bios/Settings/"},
                },
            },
            "/redfish/v1/Systems/1/Bios/Settings/": {
                "status_code": 200,
                "body": {"Attributes": {"BootMode": "Uefi"}},
            },
        }
        response = responses[path]
        requests.append({"path": path, "status_code": response["status_code"]})
        return response

    monkeypatch.setattr(esxi_install_readiness, "_safe_get", fake_safe_get)

    result = esxi_install_readiness.get_esxi_install_readiness(object())

    assert result["status"] == "ready"
    assert report_path.read_text(encoding="utf-8").strip()
    assert not list(codex_runs.glob("*.tmp"))


def test_select_esxi_iso_skips_unreadable_media_directory(monkeypatch, tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    monkeypatch.delenv("ESXI_INSTALL_ISO", raising=False)
    monkeypatch.delenv("ESXI_ISO_PATH", raising=False)
    monkeypatch.setattr(esxi_boot_workflow, "settings", replace(settings, media_inventory_dirs=(str(media_root),)))
    original_is_dir = Path.is_dir

    def flaky_is_dir(path: Path) -> bool:
        if path == media_root.resolve():
            raise OSError("locked")
        return original_is_dir(path)

    monkeypatch.setattr(Path, "is_dir", flaky_is_dir)

    try:
        esxi_boot_workflow._select_esxi_iso()
    except RuntimeError as exc:
        assert "No ESXi ISO was found" in str(exc)
    else:
        raise AssertionError("expected missing ISO error")


def test_select_esxi_iso_skips_unresolvable_media_directory(monkeypatch, tmp_path: Path) -> None:
    bad_media_root = tmp_path / "bad-media"
    media_root = tmp_path / "media"
    media_root.mkdir()
    iso = media_root / "VMware-ESXi-8.0.3.iso"
    iso.write_bytes(b"iso")
    monkeypatch.delenv("ESXI_INSTALL_ISO", raising=False)
    monkeypatch.delenv("ESXI_ISO_PATH", raising=False)
    monkeypatch.setattr(
        esxi_boot_workflow,
        "settings",
        replace(settings, media_inventory_dirs=(str(bad_media_root), str(media_root))),
    )
    original_resolve = Path.resolve

    def flaky_resolve(path: Path, *args, **kwargs) -> Path:
        if path == bad_media_root:
            raise OSError("media path unavailable")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", flaky_resolve)

    selected = esxi_boot_workflow._select_esxi_iso()

    assert selected["path"] == media_root.resolve() / "VMware-ESXi-8.0.3.iso"
    assert selected["selection"] == "preferred-esxi-8"


def test_select_esxi_iso_skips_candidates_that_disappear(monkeypatch, tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    broken = media_root / "VMware-ESXi-8.0.3-broken.iso"
    stable = media_root / "VMware-ESXi-8.0.2-stable.iso"
    broken.write_bytes(b"broken")
    stable.write_bytes(b"stable")
    monkeypatch.delenv("ESXI_INSTALL_ISO", raising=False)
    monkeypatch.delenv("ESXI_ISO_PATH", raising=False)
    monkeypatch.setattr(esxi_boot_workflow, "settings", replace(settings, media_inventory_dirs=(str(media_root),)))
    original_stat = Path.stat

    def flaky_stat(path: Path, *args, **kwargs) -> os.stat_result:
        if path == broken:
            raise FileNotFoundError("gone")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky_stat)

    selected = esxi_boot_workflow._select_esxi_iso()

    assert selected["path"] == stable
    assert selected["size_bytes"] == len(b"stable")


def test_select_esxi_iso_explicit_path_self_heals_stat_error(monkeypatch, tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    iso = media_root / "VMware-ESXi-8.0.3.iso"
    iso.write_bytes(b"iso")
    monkeypatch.setenv("ESXI_INSTALL_ISO", str(iso))
    monkeypatch.delenv("ESXI_ISO_PATH", raising=False)
    monkeypatch.setattr(esxi_boot_workflow, "settings", replace(settings, media_inventory_dirs=(str(media_root),)))
    original_stat = Path.stat

    def flaky_stat(path: Path, *args, **kwargs) -> os.stat_result:
        if path == iso:
            raise FileNotFoundError("gone")
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky_stat)

    try:
        esxi_boot_workflow._select_esxi_iso()
    except RuntimeError as exc:
        assert "not an ISO file" in str(exc)
    else:
        raise AssertionError("expected unreadable explicit ISO error")


def test_select_esxi_iso_explicit_path_reports_unresolvable_path(monkeypatch, tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    iso = media_root / "VMware-ESXi-8.0.3.iso"
    iso.write_bytes(b"iso")
    monkeypatch.setenv("ESXI_INSTALL_ISO", str(iso))
    monkeypatch.delenv("ESXI_ISO_PATH", raising=False)
    monkeypatch.setattr(esxi_boot_workflow, "settings", replace(settings, media_inventory_dirs=(str(media_root),)))
    original_resolve = Path.resolve

    def flaky_resolve(path: Path, *args, **kwargs) -> Path:
        if path == iso:
            raise OSError("iso path unavailable")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", flaky_resolve)

    try:
        esxi_boot_workflow._select_esxi_iso()
    except RuntimeError as exc:
        assert "could not be resolved" in str(exc)
    else:
        raise AssertionError("expected unresolvable explicit ISO error")


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
    monkeypatch.setattr(esxi_boot_workflow, "MEDIA_SERVER_LOG", codex_runs / "esxi-media-http-server.log")
    monkeypatch.setattr(esxi_boot_workflow, "MEDIA_SERVER_PID", codex_runs / "esxi-media-http-server.pid")
