from __future__ import annotations

from types import SimpleNamespace

from app.services import hpe_firmware_upgrade as hpe


def test_hpe_firmware_plan_filters_selected_component(monkeypatch) -> None:
    monkeypatch.setattr(hpe, "get_firmware_compliance", lambda **_: _hpe_compliance())

    result = hpe.build_hpe_firmware_upgrade_plan(
        component_id="hpe_smart_array_firmware",
        write_report=False,
    )

    assert result["status"] == "ready"
    assert result["selected_component_id"] == "hpe_smart_array_firmware"
    assert result["selected_component_label"] == "Smart Array firmware"
    assert [step["component_id"] for step in result["ordered_steps"]] == ["hpe_smart_array_firmware"]
    assert [step["component_id"] for step in result["upgrade_steps"]] == ["hpe_smart_array_firmware"]
    assert "HPE_FIRMWARE_COMPONENT_ID=hpe_smart_array_firmware" in result["apply_command"]


def test_hpe_firmware_plan_blocks_unknown_selected_component(monkeypatch) -> None:
    monkeypatch.setattr(hpe, "get_firmware_compliance", lambda **_: _hpe_compliance())

    result = hpe.build_hpe_firmware_upgrade_plan(component_id="hpe_unknown_firmware", write_report=False)

    assert result["status"] == "blocked"
    assert result["ordered_steps"] == []
    assert result["blockers"] == ["Unsupported HPE firmware component selected: hpe_unknown_firmware."]


def test_hpe_firmware_apply_reports_current_without_executor_blocker(monkeypatch) -> None:
    monkeypatch.setattr(hpe, "settings", SimpleNamespace(provider_mode="local-lab-readwrite"))
    monkeypatch.setenv("HPE_FIRMWARE_APPLY", "true")
    monkeypatch.setenv("HPE_FIRMWARE_CONFIRM", "run")
    monkeypatch.setattr(hpe, "current_lab_action_policy", lambda: SimpleNamespace(action_blockers=lambda *_: []))
    monkeypatch.setattr(hpe, "build_hpe_firmware_upgrade_plan", lambda **_: _current_hpe_plan())

    result = hpe.apply_hpe_firmware_upgrade(write_report=False, component_id="hpe_smart_array_firmware")

    assert result["status"] == "current"
    assert result["blockers"] == []
    assert result["upgrade_writes_attempted"] is False


def test_hpe_bios_expected_package_name_uses_bios_family_target() -> None:
    assert hpe._bios_package_name("U32 v3.66 (04/01/2026)") == "U32_3.66_04_01_2026.fwpkg"


def _hpe_compliance() -> dict:
    return {
        "status": "needs_upgrade",
        "blockers": [],
        "source_type": "cached_live",
        "freshness": "current",
        "components": [
            {"id": "hpe_ilo_firmware", "status": "passed", "current_version": "3.19", "approved_versions": ["3.19"]},
            {
                "id": "hpe_bios_version",
                "status": "passed",
                "current_version": "U32 v3.30 (07/31/2024)",
                "approved_versions": ["U32 v3.30 (07/31/2024)"],
            },
            {
                "id": "hpe_smart_array_firmware",
                "status": "failed",
                "current_version": "1.98",
                "approved_versions": ["8.00"],
            },
        ],
        "upgrade_paths": [
            {
                "component_id": "hpe_smart_array_firmware",
                "path_status": "staged",
                "current_version": "1.98",
                "target_version": "8.00",
                "package_available": True,
                "package_name": "HPE_SR_Gen10_8.00_A.fwpkg",
                "reboot_required": True,
            }
        ],
    }


def _current_hpe_plan() -> dict:
    return {
        "status": "current",
        "selected_component_id": "hpe_smart_array_firmware",
        "selected_component_label": "Smart Array firmware",
        "ordered_steps": [
            {
                "component_id": "hpe_smart_array_firmware",
                "label": "Smart Array firmware",
                "action": "skip",
                "current_version": "8.00",
                "target_version": "8.00",
            }
        ],
        "upgrade_steps": [],
        "blockers": [],
        "artifacts": {},
    }
