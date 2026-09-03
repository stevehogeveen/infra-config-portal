from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import httpx

from app.providers.ilo_redfish import IloRedfishConfig, ilo_target_fingerprint
from app.providers.probe_cache import clear_probe_results, record_probe_result
from app.services import hpe_raid
from app.services.ilo_write_target import IloWriteTargetContext
from app.schemas import HpeRaidVolumeIntent


def test_get_smartstorage_resource_does_not_raise_on_unreachable_device(monkeypatch) -> None:
    # Regression: an unreachable device made _get_redfish_resource raise
    # httpx.ConnectTimeout, which _get_smartstorage_resource passed straight
    # through uncaught. That turned /esxi-install-readiness and
    # /hpe-raid-pending into unhandled 500s instead of a normal
    # failed/blocked read-only status, even though every caller already
    # tolerates a missing/None status_code in the response shape.
    def raise_timeout(path: str):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(hpe_raid, "_get_redfish_resource", raise_timeout)

    result = hpe_raid._get_smartstorage_resource("/redfish/v1/Systems/1/SmartStorage/")

    assert result["status_code"] is None
    assert result["error_class"] == "ConnectTimeout"
    assert result["path"] == "/redfish/v1/Systems/1/SmartStorage/"


def test_write_pending_report_completes_when_device_is_unreachable(monkeypatch, tmp_path: Path) -> None:
    _redirect_artifacts(monkeypatch, tmp_path)

    def raise_timeout(path: str):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(hpe_raid, "_get_redfish_resource", raise_timeout)
    monkeypatch.setattr(hpe_raid, "_last_apply_full_state", lambda: {"status": "never"})
    monkeypatch.setattr(
        hpe_raid,
        "get_hpe_raid_intent",
        lambda _session: type("Intent", (), {"data_guard": "Disabled", "logical_drives": []})(),
    )
    monkeypatch.setattr(
        hpe_raid,
        "_redfish_settings_payload",
        lambda _intent: {"DataGuard": "Disabled", "LogicalDrives": []},
    )

    # Must complete without raising - this is what turned into a 500 at the
    # API layer before the fix. (Whether "unreachable" should itself count
    # as blocked/failed in the pending-report status is a separate business
    # question this test isn't making a claim about.)
    report = hpe_raid.write_hpe_raid_pending_report(object())

    assert report["current_get"]["status_code"] is None
    assert report["settings_get"]["status_code"] is None


def test_last_apply_state_self_heals_corrupt_cache(monkeypatch, tmp_path: Path) -> None:
    _redirect_artifacts(monkeypatch, tmp_path)
    hpe_raid.APPLY_STATE.write_text("{not valid json", encoding="utf-8")

    summary = hpe_raid._last_apply_state()
    full = hpe_raid._last_apply_full_state()

    assert summary == {
        "status": "failed",
        "report": "artifacts/codex-runs/hpe-raid-apply-report.md",
    }
    assert full["status"] == "failed"
    assert "could not be parsed" in full["message"]


def test_last_apply_state_treats_probe_errors_as_missing(monkeypatch, tmp_path: Path) -> None:
    _redirect_artifacts(monkeypatch, tmp_path)
    original_exists = Path.exists

    def flaky_exists(path: Path) -> bool:
        if path == hpe_raid.APPLY_STATE:
            raise OSError("share is temporarily unavailable")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    summary = hpe_raid._last_apply_state()
    full = hpe_raid._last_apply_full_state()

    expected = {
        "status": "never",
        "report": "artifacts/codex-runs/hpe-raid-apply-report.md",
    }
    assert summary == expected
    assert full == expected


def test_write_apply_artifacts_writes_json_atomically(monkeypatch, tmp_path: Path) -> None:
    _redirect_artifacts(monkeypatch, tmp_path)

    hpe_raid._write_apply_artifacts(
        {
            "status": "succeeded",
            "message": "Applied.",
            "started_at": "2026-06-25T00:00:00+00:00",
            "finished_at": "2026-06-25T00:00:01+00:00",
            "redfish_payload": {"DataGuard": "Disabled", "LogicalDrives": [{"Raid": "1"}]},
            "redfish_result": {"status_code": 200},
            "blockers": [],
            "warnings": [],
        }
    )

    saved_state = json.loads(hpe_raid.APPLY_STATE.read_text(encoding="utf-8"))
    saved_payload = json.loads(hpe_raid.APPLY_PAYLOAD_REDACTED.read_text(encoding="utf-8"))
    assert saved_state["status"] == "succeeded"
    assert saved_payload["DataGuard"] == "Disabled"
    assert hpe_raid.APPLY_REPORT.exists()
    assert hpe_raid.APPLY_REPORT.read_text(encoding="utf-8").strip()
    assert not list(hpe_raid.CODEX_RUN_DIR.glob("*.tmp"))


def test_write_pending_report_writes_json_artifacts_atomically(monkeypatch, tmp_path: Path) -> None:
    _redirect_artifacts(monkeypatch, tmp_path)
    monkeypatch.setattr(
        hpe_raid,
        "_get_smartstorage_resource",
        lambda path: {"status_code": 200, "body": {"path": path, "Current": True}},
    )
    monkeypatch.setattr(hpe_raid, "_last_apply_full_state", lambda: {"status": "never"})
    monkeypatch.setattr(
        hpe_raid,
        "get_hpe_raid_intent",
        lambda _session: type("Intent", (), {"data_guard": "Disabled", "logical_drives": []})(),
    )
    monkeypatch.setattr(
        hpe_raid,
        "_redfish_settings_payload",
        lambda _intent: {"DataGuard": "Disabled", "LogicalDrives": []},
    )

    report = hpe_raid.write_hpe_raid_pending_report(object())

    current = json.loads(hpe_raid.SMARTSTORAGE_CURRENT.read_text(encoding="utf-8"))
    expected = json.loads(hpe_raid.APPLY_PAYLOAD_REDACTED.read_text(encoding="utf-8"))
    assert report["provider_id"] == hpe_raid.PROVIDER_ID
    assert current["path"] == hpe_raid.SMART_STORAGE_CONFIG_PATH
    assert expected["DataGuard"] == "Disabled"
    assert hpe_raid.PENDING_REPORT.exists()
    assert hpe_raid.PENDING_REPORT.read_text(encoding="utf-8").strip()
    assert not list(hpe_raid.CODEX_RUN_DIR.glob("*.tmp"))


def test_hpe_storage_discovery_dedupes_duplicate_probe_inventory() -> None:
    clear_probe_results()
    record_probe_result(
        hpe_raid.PROVIDER_ID,
        {
            "provider_id": hpe_raid.PROVIDER_ID,
            "status": "ok",
            "systems": [{"Model": "ProLiant DL360 Gen10", "PowerState": "On"}],
            "storage": {
                "controllers": [
                    {"Id": "0", "Name": "P408i", "Model": "Smart Array"},
                    {"Id": "0", "Name": "P408i", "Model": "Smart Array"},
                ],
                "physical_drives": [
                    {"Bay": "1I:1:1", "CapacityBytes": 1200},
                    {"Bay": "1I:1:1", "CapacityBytes": 1200},
                    {"Bay": "1I:1:2", "CapacityBytes": 1200},
                ],
                "logical_drives": [
                    {
                        "LogicalDriveName": "ESXi-OS",
                        "RAIDType": "RAID1",
                        "CapacityBytes": 500,
                        "DataDrives": ["1I:1:1", "1I:1:2"],
                    },
                    {
                        "LogicalDriveName": "ESXi-OS",
                        "RAIDType": "RAID1",
                        "CapacityBytes": 500,
                        "DataDrives": ["1I:1:1", "1I:1:2"],
                    },
                ],
            },
        },
    )

    discovery = hpe_raid.get_hpe_storage_discovery()

    assert discovery.storage_inventory_available is True
    assert len(discovery.controllers) == 1
    assert len(discovery.physical_drives) == 2
    assert len(discovery.logical_drives) == 1
    assert {drive["selection_id"] for drive in discovery.physical_drives} == {
        "1I:1:1",
        "1I:1:2",
    }
    assert all(drive["raid_payload_compatible"] is True for drive in discovery.physical_drives)
    clear_probe_results()


def test_hpe_storage_discovery_preserves_distinct_opaque_redfish_drive_resources() -> None:
    probe = {
        "provider_id": hpe_raid.PROVIDER_ID,
        "status": "ok",
        "storage": {
            "physical_drives": [
                {
                    "@odata.id": f"/redfish/v1/Chassis/DE009000/Drives/{index}",
                    "Id": str(index),
                    "Name": "Physical Drive",
                    "CapacityBytes": 1_200_000_000_000,
                    "Status": {"Health": "OK", "State": "Enabled"},
                }
                for index in range(8)
            ],
        },
    }

    discovery = hpe_raid.get_hpe_storage_discovery(
        probe=probe,
        probe_time="2026-07-23T12:00:00+00:00",
    )

    assert discovery.storage_inventory_available is True
    assert len(discovery.physical_drives) == 8
    assert {drive["bay_id"] for drive in discovery.physical_drives} == {""}
    assert len({drive["selection_id"] for drive in discovery.physical_drives}) == 8
    assert len({drive["inventory_id"] for drive in discovery.physical_drives}) == 8
    assert len({drive["display_label"] for drive in discovery.physical_drives}) == 8
    assert {drive["identity_kind"] for drive in discovery.physical_drives} == {
        "redfish_resource"
    }
    assert {drive["raid_payload_id"] for drive in discovery.physical_drives} == {None}
    assert all(
        drive["raid_payload_compatible"] is False
        for drive in discovery.physical_drives
    )
    assert any(
        "opaque resource IDs cannot be used" in warning
        for warning in discovery.warnings
    )
    assert "resolve SmartStorage physical bay locations" in discovery.next_safe_action


def test_hpe_storage_discovery_dedupes_same_opaque_redfish_resource() -> None:
    drive = {
        "@odata.id": "/redfish/v1/Chassis/DE009000/Drives/0",
        "Id": "0",
        "Name": "Physical Drive",
    }

    discovery = hpe_raid.get_hpe_storage_discovery(
        probe={
            "provider_id": hpe_raid.PROVIDER_ID,
            "status": "ok",
            "storage": {"physical_drives": [drive, dict(drive)]},
        },
    )

    assert len(discovery.physical_drives) == 1
    assert discovery.physical_drives[0]["selection_id"] == (
        "redfish:/redfish/v1/Chassis/DE009000/Drives/0"
    )


def test_opaque_redfish_drive_ids_cannot_make_raid_plan_apply_ready(monkeypatch) -> None:
    discovery = hpe_raid.get_hpe_storage_discovery(
        probe={
            "provider_id": hpe_raid.PROVIDER_ID,
            "status": "ok",
            "storage": {
                "controllers": [{"Id": "0", "Name": "Smart Array"}],
                "physical_drives": [
                    {
                        "@odata.id": f"/redfish/v1/Chassis/DE009000/Drives/{index}",
                        "Id": str(index),
                        "CapacityBytes": 1_200_000_000_000,
                        "Status": {"Health": "OK", "State": "Enabled"},
                    }
                    for index in range(2)
                ],
            },
        },
    )
    intent = SimpleNamespace(
        controller_ref="0",
        wipe_existing_logical_drives=True,
        volumes=[
            SimpleNamespace(
                name="ESXi-OS",
                raid_level="RAID1",
                drive_bays=["0", "1"],
                spare_bays=[],
                bootable=True,
            )
        ],
    )

    validation = hpe_raid._validate_intent(intent, discovery)
    recommendation = hpe_raid._recommended_local_storage_layout(discovery)
    monkeypatch.setattr(hpe_raid, "current_lab_action_policy", lambda _mode=None: _AllowPolicy())
    monkeypatch.setattr(hpe_raid, "firmware_gate_blockers", lambda _label: [])
    monkeypatch.setenv("HPE_RAID_ALLOW_DESTRUCTIVE", "true")
    apply_blockers = hpe_raid._apply_blockers(
        SimpleNamespace(
            blockers=validation["blockers"],
            desired_intent=intent,
            current_layout=discovery,
        ),
        confirmation_phrase=hpe_raid.CONFIRMATION_PHRASE,
    )

    assert any(
        "only opaque Redfish resource IDs" in blocker
        for blocker in validation["blockers"]
    )
    assert any(
        "only opaque Redfish resource IDs" in blocker
        for blocker in apply_blockers
    )
    assert recommendation["status"] == "blocked"
    assert recommendation["usable_drive_count"] == 0
    assert any(
        "ControllerPort:Box:Bay" in blocker
        for blocker in recommendation["blockers"]
    )


def test_reset_reports_write_atomically(monkeypatch, tmp_path: Path) -> None:
    _redirect_artifacts(monkeypatch, tmp_path)

    hpe_raid._write_reset_report({"status": "blocked", "blockers": ["gate"], "warnings": []})
    hpe_raid._write_after_reset_validation_report(
        {"status": "ready", "blockers": [], "warnings": [], "validation": {"status": "ready"}}
    )

    assert hpe_raid.RESET_REPORT.read_text(encoding="utf-8").strip()
    assert hpe_raid.AFTER_RESET_VALIDATION_REPORT.read_text(encoding="utf-8").strip()
    assert not list(hpe_raid.CODEX_RUN_DIR.glob("*.tmp"))


def test_apply_blockers_accept_common_true_like_env_values(monkeypatch) -> None:
    monkeypatch.setattr(hpe_raid, "current_lab_action_policy", lambda _mode=None: _AllowPolicy())
    monkeypatch.setattr(hpe_raid, "firmware_gate_blockers", lambda _label: [])
    monkeypatch.setenv("HPE_RAID_ALLOW_DESTRUCTIVE", " YES ")
    preview = SimpleNamespace(
        blockers=[],
        desired_intent=SimpleNamespace(volumes=[{"name": "os"}], wipe_existing_logical_drives=True),
        current_layout=SimpleNamespace(logical_drives=[]),
    )

    blockers = hpe_raid._apply_blockers(
        preview,
        confirmation_phrase=hpe_raid.CONFIRMATION_PHRASE,
    )

    assert blockers == []


def test_apply_blockers_keep_scalar_policy_firmware_and_preview_blockers_whole(monkeypatch) -> None:
    monkeypatch.setattr(hpe_raid, "current_lab_action_policy", lambda _mode=None: _ScalarBlockerPolicy())
    monkeypatch.setattr(hpe_raid, "firmware_gate_blockers", lambda _label: " firmware blocker ")
    monkeypatch.setenv("HPE_RAID_ALLOW_DESTRUCTIVE", "true")
    preview = SimpleNamespace(
        blockers=" preview blocker ",
        desired_intent=SimpleNamespace(volumes=[{"name": "os"}], wipe_existing_logical_drives=True),
        current_layout=SimpleNamespace(logical_drives=[]),
    )

    blockers = hpe_raid._apply_blockers(
        preview,
        confirmation_phrase=hpe_raid.CONFIRMATION_PHRASE,
    )

    assert "policy blocker" in blockers
    assert "firmware blocker" in blockers
    assert "preview blocker" in blockers
    assert not any(blocker == "p" for blocker in blockers)


def test_reset_blockers_accept_common_true_like_env_values(monkeypatch) -> None:
    monkeypatch.setattr(hpe_raid, "current_lab_action_policy", lambda _mode=None: _AllowPolicy())
    monkeypatch.setattr(hpe_raid, "firmware_gate_blockers", lambda _label: [])
    monkeypatch.setenv("HPE_RAID_ALLOW_RESET", "ON")
    monkeypatch.setenv("HPE_RAID_RESET_CONFIRM", hpe_raid.RESET_CONFIRMATION_PHRASE)

    blockers = hpe_raid._reset_blockers()

    assert blockers == []


def test_reset_blockers_keep_scalar_policy_and_firmware_blockers_whole(monkeypatch) -> None:
    monkeypatch.setattr(hpe_raid, "current_lab_action_policy", lambda _mode=None: _ScalarBlockerPolicy())
    monkeypatch.setattr(hpe_raid, "firmware_gate_blockers", lambda _label: " firmware blocker ")
    monkeypatch.setenv("HPE_RAID_ALLOW_RESET", "true")
    monkeypatch.setenv("HPE_RAID_RESET_CONFIRM", hpe_raid.RESET_CONFIRMATION_PHRASE)

    blockers = hpe_raid._reset_blockers()

    assert "policy blocker" in blockers
    assert "firmware blocker" in blockers
    assert not any(blocker == "p" for blocker in blockers)


def test_reset_plan_uses_power_on_when_server_is_off(monkeypatch) -> None:
    monkeypatch.setattr(hpe_raid, "current_lab_action_policy", lambda _mode=None: _AllowPolicy())
    monkeypatch.setattr(hpe_raid, "firmware_gate_blockers", lambda _label: [])
    monkeypatch.setenv("HPE_RAID_ALLOW_RESET", "true")
    monkeypatch.setenv("HPE_RAID_RESET_CONFIRM", hpe_raid.RESET_CONFIRMATION_PHRASE)
    monkeypatch.setattr(
        hpe_raid,
        "_server_reset_observation",
        lambda *, allow_errors=False: {"reachable": True, "power_state": "Off"},
    )

    plan = hpe_raid.build_hpe_raid_reset_plan()

    assert plan["status"] == "ready"
    assert plan["reset_type"] == "On"
    assert plan["power_state"] == "Off"
    assert "Power on" in plan["next_safe_action"]


def test_reset_server_for_raid_powers_on_when_server_is_off(monkeypatch, tmp_path: Path) -> None:
    _redirect_artifacts(monkeypatch, tmp_path)
    _allow_exact_write_target(monkeypatch)
    monkeypatch.setattr(hpe_raid, "current_lab_action_policy", lambda _mode=None: _AllowPolicy())
    monkeypatch.setattr(hpe_raid, "firmware_gate_blockers", lambda _label: [])
    monkeypatch.setenv("HPE_RAID_ALLOW_RESET", "true")
    monkeypatch.setenv("HPE_RAID_RESET_CONFIRM", hpe_raid.RESET_CONFIRMATION_PHRASE)
    monkeypatch.setattr(hpe_raid.time, "sleep", lambda _seconds: None)

    observations = iter(
        [
            {"reachable": True, "power_state": "Off"},
            {"reachable": True, "power_state": "On"},
        ]
    )
    reset_types: list[str] = []

    def fake_observation(*, config=None, allow_errors: bool = False) -> dict:
        return next(observations)

    def fake_reset(reset_type: str, *, config) -> dict:
        reset_types.append(reset_type)
        return {
            "method": "POST",
            "path": "/redfish/v1/Systems/1/Actions/ComputerSystem.Reset/",
            "status_code": 200,
            "request": {"ResetType": reset_type},
            "response": {},
        }

    monkeypatch.setattr(hpe_raid, "_server_reset_observation", fake_observation)
    monkeypatch.setattr(hpe_raid, "_post_system_reset", fake_reset)
    monkeypatch.setattr(
        hpe_raid,
        "_target_bound_reset_preconditions",
        lambda *_args: ({"reset_required": True}, []),
    )

    result = hpe_raid.reset_server_for_raid()

    assert result["status"] == "reset-requested"
    assert result["reset_type"] == "On"
    assert reset_types == ["On"]
    assert result["reset"]["request"] == {"ResetType": "On"}


def test_reset_server_for_raid_gracefully_restarts_when_server_is_on(monkeypatch, tmp_path: Path) -> None:
    _redirect_artifacts(monkeypatch, tmp_path)
    _allow_exact_write_target(monkeypatch)
    monkeypatch.setattr(hpe_raid, "current_lab_action_policy", lambda _mode=None: _AllowPolicy())
    monkeypatch.setattr(hpe_raid, "firmware_gate_blockers", lambda _label: [])
    monkeypatch.setenv("HPE_RAID_ALLOW_RESET", "true")
    monkeypatch.setenv("HPE_RAID_RESET_CONFIRM", hpe_raid.RESET_CONFIRMATION_PHRASE)
    monkeypatch.setattr(hpe_raid.time, "sleep", lambda _seconds: None)

    observations = iter(
        [
            {"reachable": True, "power_state": "On"},
            {"reachable": True, "power_state": "On"},
        ]
    )
    reset_types: list[str] = []

    monkeypatch.setattr(
        hpe_raid,
        "_server_reset_observation",
        lambda *, config=None, allow_errors=False: next(observations),
    )
    monkeypatch.setattr(
        hpe_raid,
        "_post_system_reset",
        lambda reset_type, *, config: reset_types.append(reset_type)
        or {
            "method": "POST",
            "path": "/redfish/v1/Systems/1/Actions/ComputerSystem.Reset/",
            "status_code": 200,
            "request": {"ResetType": reset_type},
            "response": {},
        },
    )
    monkeypatch.setattr(
        hpe_raid,
        "_target_bound_reset_preconditions",
        lambda *_args: ({"reset_required": True}, []),
    )

    result = hpe_raid.reset_server_for_raid()

    assert result["status"] == "reset-requested"
    assert result["reset_type"] == "GracefulRestart"
    assert reset_types == ["GracefulRestart"]


def test_factory_reset_preview_lists_delete_and_recreate_plan(monkeypatch, tmp_path: Path) -> None:
    _redirect_artifacts(monkeypatch, tmp_path)
    preview = SimpleNamespace(
        blockers=[],
        warnings=[],
        desired_intent=SimpleNamespace(
            wipe_existing_logical_drives=True,
            volumes=[
                HpeRaidVolumeIntent(
                    name="ESXi-OS",
                    purpose="os",
                    raid_level="RAID1",
                    drive_bays=["1I:1:1", "1I:1:2"],
                    bootable=True,
                    size_policy="500",
                ),
                HpeRaidVolumeIntent(
                    name="VM-Datastore",
                    purpose="datastore",
                    raid_level="RAID6",
                    drive_bays=["1I:1:3", "1I:1:4", "1I:1:5", "1I:1:6", "1I:1:7", "1I:1:8"],
                ),
            ],
            data_guard="Disabled",
        ),
        current_layout=SimpleNamespace(
            logical_drives=[
                {
                    "name": "ESXi-OS",
                    "raid_level": "RAID1",
                    "capacity_label": "500 GiB",
                    "resource": "/redfish/v1/Systems/1/SmartStorage/ArrayControllers/0/LogicalDrives/1",
                },
                {
                    "name": "VM-Datastore",
                    "raid_level": "RAID6",
                    "capacity_label": "3.27 TiB",
                    "resource": "/redfish/v1/Systems/1/SmartStorage/ArrayControllers/0/LogicalDrives/2",
                },
            ]
        ),
    )
    monkeypatch.setattr(hpe_raid, "get_hpe_raid_plan_preview", lambda _session: preview)

    result = hpe_raid.build_hpe_raid_factory_reset_preview(object())

    assert result["status"] == "ready"
    assert result["apply_enabled"] is False
    assert result["executor_available"] is False
    assert result["delete_count"] == 2
    assert result["recreate_count"] == 2
    assert result["recreate_payload"]["LogicalDrives"][0]["LogicalDriveName"] == "ESXi-OS"
    assert "logical drive delete" in result["not_attempted"]
    assert hpe_raid.FACTORY_RESET_PLAN_REPORT.read_text(encoding="utf-8").strip()


def test_factory_reset_apply_refuses_even_when_gated(monkeypatch, tmp_path: Path) -> None:
    _redirect_artifacts(monkeypatch, tmp_path)
    monkeypatch.setattr(hpe_raid, "current_lab_action_policy", lambda _mode=None: _AllowPolicy())
    monkeypatch.setenv("LAB_ALLOW_FACTORY_RESET", "true")
    monkeypatch.setenv("HPE_RAID_ALLOW_FACTORY_RESET", "true")
    preview = {
        "provider_id": hpe_raid.PROVIDER_ID,
        "status": "ready",
        "executor_available": False,
        "blockers": [],
        "warnings": [],
        "delete_existing_logical_drives": [{"name": "ESXi-OS"}],
        "recreate_payload": {"LogicalDrives": [{"LogicalDriveName": "ESXi-OS"}]},
    }
    monkeypatch.setattr(hpe_raid, "build_hpe_raid_factory_reset_preview", lambda _session: preview)

    result = hpe_raid.apply_hpe_raid_factory_reset(
        object(),
        hpe_raid.HpeRaidFactoryResetCreate(confirmation_phrase=hpe_raid.FACTORY_RESET_CONFIRMATION_PHRASE),
    )

    assert result["status"] == "blocked"
    assert result["apply_enabled"] is False
    assert "No implemented HPE SmartStorage logical-drive delete/factory-reset executor exists yet." in result["blockers"]
    assert "logical drive delete" in result["not_attempted"]
    assert hpe_raid.FACTORY_RESET_APPLY_REPORT.read_text(encoding="utf-8").strip()


def _redirect_artifacts(monkeypatch, tmp_path: Path) -> None:
    codex_runs = tmp_path / "artifacts" / "codex-runs"
    codex_runs.mkdir(parents=True)
    monkeypatch.setattr(hpe_raid, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(hpe_raid, "CODEX_RUN_DIR", codex_runs)
    monkeypatch.setattr(hpe_raid, "APPLY_REPORT", codex_runs / "hpe-raid-apply-report.md")
    monkeypatch.setattr(hpe_raid, "APPLY_STATE", codex_runs / "hpe-raid-apply-state.json")
    monkeypatch.setattr(hpe_raid, "REDFISH_DEBUG_REPORT", codex_runs / "hpe-raid-redfish-debug-report.md")
    monkeypatch.setattr(hpe_raid, "APPLY_PAYLOAD_REDACTED", codex_runs / "hpe-raid-apply-payload-redacted.json")
    monkeypatch.setattr(hpe_raid, "SMARTSTORAGE_CURRENT", codex_runs / "hpe-smartstorage-current.json")
    monkeypatch.setattr(hpe_raid, "SMARTSTORAGE_SETTINGS", codex_runs / "hpe-smartstorage-settings.json")
    monkeypatch.setattr(hpe_raid, "PENDING_REPORT", codex_runs / "hpe-raid-pending-report.md")
    monkeypatch.setattr(hpe_raid, "RESET_REPORT", codex_runs / "hpe-raid-reset-report.md")
    monkeypatch.setattr(hpe_raid, "AFTER_RESET_VALIDATION_REPORT", codex_runs / "hpe-raid-after-reset-validation-report.md")
    monkeypatch.setattr(hpe_raid, "FACTORY_RESET_PLAN_REPORT", codex_runs / "hpe-raid-factory-reset-plan-report.md")
    monkeypatch.setattr(hpe_raid, "FACTORY_RESET_APPLY_REPORT", codex_runs / "hpe-raid-factory-reset-apply-report.md")


def _allow_exact_write_target(monkeypatch) -> IloWriteTargetContext:
    host = "192.168.1.11"
    context = IloWriteTargetContext(
        current_access_host=host,
        target_fingerprint=ilo_target_fingerprint(host) or "",
        identity_fingerprint_sha256="a" * 64,
        evidence_digest_sha256="b" * 64,
        evidence_checked_at=datetime.now(UTC),
        target_source="operator_first_contact",
    )
    config = IloRedfishConfig(
        host=host,
        username="operator",
        password="secret",
        verify_tls=False,
        timeout_seconds=3.0,
        host_source="exact_write_target_context",
    )
    monkeypatch.setenv("ILO_WRITE_TARGET_HOST", host)
    monkeypatch.setattr(
        hpe_raid,
        "resolve_ilo_write_target_context",
        lambda requested_host: (
            (context, [])
            if requested_host == host
            else (None, ["write target mismatch"])
        ),
    )
    monkeypatch.setattr(
        hpe_raid,
        "exact_ilo_write_config",
        lambda resolved: config if resolved == context else None,
    )
    monkeypatch.setattr(
        hpe_raid,
        "refresh_ilo_write_target_context",
        lambda resolved: (
            (context, config, [])
            if resolved == context
            else (None, None, ["write target mismatch"])
        ),
    )
    return context


class _AllowPolicy:
    def action_blockers(self, _action_id, _category):
        return []


class _ScalarBlockerPolicy:
    def action_blockers(self, _action_id, _category):
        return " policy blocker "
