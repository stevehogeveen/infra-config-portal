from __future__ import annotations

from app.services import esxi_management_recovery


def _target_state() -> dict:
    return {
        "esxi_host": "192.168.1.203",
        "ilo_host": "192.168.1.201",
        "https_check": {"reachable": False},
        "ssh_check": {"reachable": False},
        "ilo_https_check": {"reachable": True},
        "https_reachable": False,
        "ssh_reachable": False,
        "ilo_https_reachable": True,
    }


def _auth_blocked_probe() -> dict:
    return {
        "status": "failed",
        "message": "Inventory collections returned HTTP 401.",
        "endpoint_detection": {
            "redfish_status": "available",
            "classification": "redfish_inventory_auth_failed",
        },
        "legacy_identity": {
            "ilo_generation": "ilo5",
            "model": "ProLiant DL360 Gen10",
        },
    }


def _gates(*, asserted: bool) -> dict:
    return {
        "flag_state": {
            "provider_mode": "local-lab-readwrite",
            "local_lab_readwrite": True,
            "lab_allow_power_actions": True,
            "esxi_recovery_apply": True,
            "esxi_recovery_confirm": True,
            "esxi_recovery_assume_power_off": asserted,
            "esxi_recovery_assume_power_off_confirm": asserted,
        },
        "blockers": [],
    }


def test_recovery_still_blocks_on_redfish_auth_without_power_off_assertion(monkeypatch) -> None:
    monkeypatch.setattr(esxi_management_recovery, "_target_state", _target_state)
    monkeypatch.setattr(
        esxi_management_recovery,
        "_safe_system_state",
        lambda: {"status_code": 401, "power_state": None, "boot": {}},
    )
    monkeypatch.setattr(esxi_management_recovery, "_safe_ilo_probe", _auth_blocked_probe)
    monkeypatch.setattr(esxi_management_recovery, "_recovery_gates", lambda: _gates(asserted=False))

    result = esxi_management_recovery.recover_esxi_management(write_report=False)

    assert result["status"] == "blocked"
    assert result["apply"]["attempted"] is False
    assert any("Redfish authorization is blocked" in item for item in result["blockers"])


def test_recovery_uses_operator_asserted_power_on_for_auth_blocked_off_host(monkeypatch) -> None:
    monkeypatch.setattr(esxi_management_recovery, "_target_state", _target_state)
    monkeypatch.setattr(
        esxi_management_recovery,
        "_safe_system_state",
        lambda: {"status_code": 401, "power_state": None, "boot": {}},
    )
    monkeypatch.setattr(esxi_management_recovery, "_safe_ilo_probe", _auth_blocked_probe)
    monkeypatch.setattr(esxi_management_recovery, "_recovery_gates", lambda: _gates(asserted=True))

    calls: list[bool] = []

    def fake_power_on(target: dict, *, operator_asserted: bool = False) -> dict:
        calls.append(operator_asserted)
        return {
            "power_on_attempted": True,
            "force_restart_attempted": False,
            "operator_asserted_power_off": operator_asserted,
            "result": "power_on_requested",
            "reset": {"status_code": 200, "request": {"ResetType": "On"}},
            "poll_checks": [{"reachable": True}],
            "esxi_https_reachable_after": True,
        }

    monkeypatch.setattr(esxi_management_recovery, "_power_on_and_wait", fake_power_on)

    result = esxi_management_recovery.recover_esxi_management(write_report=False)

    assert result["status"] == "recovered"
    assert result["recovery_method"]["method"] == "operator_asserted_redfish_power_on"
    assert result["apply"]["attempted"] is True
    assert calls == [True]
