from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.providers.ilo_redfish import IloRedfishConfig, ilo_target_fingerprint
from app.services import esxi_management_recovery
from app.services.ilo_write_target import IloWriteTargetContext


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


def test_recovery_blocks_before_auth_checks_without_exact_target(monkeypatch) -> None:
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
    assert any("explicit current-access ilo_host" in item for item in result["blockers"])


def test_recovery_gates_accept_common_true_like_env_values(monkeypatch) -> None:
    monkeypatch.setenv("LAB_ALLOW_POWER_ACTIONS", " YES ")
    monkeypatch.setenv("ESXI_RECOVERY_APPLY", "TRUE")
    monkeypatch.setenv("ESXI_RECOVERY_CONFIRM", esxi_management_recovery.RECOVERY_CONFIRM_PHRASE)
    monkeypatch.setenv("ESXI_RECOVERY_ASSUME_POWER_OFF", "On")
    monkeypatch.setenv(
        "ESXI_RECOVERY_ASSUME_POWER_OFF_CONFIRM",
        esxi_management_recovery.ASSERT_POWER_OFF_CONFIRM_PHRASE,
    )

    gates = esxi_management_recovery._recovery_gates()

    assert gates["flag_state"]["lab_allow_power_actions"] is True
    assert gates["flag_state"]["esxi_recovery_apply"] is True
    assert gates["flag_state"]["esxi_recovery_assume_power_off"] is True
    assert not any("ESXI_RECOVERY_APPLY=true" in blocker for blocker in gates["blockers"])


def test_recovery_gate_and_blocker_dedupe_preserves_first_seen_order(monkeypatch) -> None:
    class DuplicatePolicy:
        allow_power_actions = False

        def action_blockers(self, action_id: str, category: object) -> list[str]:
            assert action_id == "ilo.power-action"
            return [
                "policy blocker",
                "ESXI_RECOVERY_APPLY=true is required.",
                "policy blocker",
            ]

    monkeypatch.setattr(esxi_management_recovery, "current_lab_action_policy", lambda mode: DuplicatePolicy())
    monkeypatch.setenv("ESXI_RECOVERY_CONFIRM", "wrong")
    monkeypatch.delenv("ESXI_RECOVERY_APPLY", raising=False)

    gates = esxi_management_recovery._recovery_gates()

    assert gates["blockers"] == [
        "policy blocker",
        "ESXI_RECOVERY_APPLY=true is required.",
        f'ESXI_RECOVERY_CONFIRM="{esxi_management_recovery.RECOVERY_CONFIRM_PHRASE}" is required.',
    ]

    blockers = esxi_management_recovery._recovery_blockers(
        _target_state(),
        {"status_code": 401, "power_state": None, "boot": {}},
        {"status": "failed"},
        {
            "flag_state": _gates(asserted=False)["flag_state"],
            "blockers": [
                "iLO Redfish authorization is blocked; the app cannot read power state or issue guarded power recovery.",
                "policy blocker",
                "policy blocker",
            ],
        },
    )

    assert blockers == [
        "iLO Redfish authorization is blocked; the app cannot read power state or issue guarded power recovery.",
        "The app can only auto-recover a verified powered-off host; current power state is not confirmed as Off.",
        "policy blocker",
    ]


def test_recovery_gates_keep_scalar_policy_blocker_whole(monkeypatch) -> None:
    class ScalarPolicy:
        allow_power_actions = True

        def action_blockers(self, action_id: str, category: object) -> str:
            assert action_id == "ilo.power-action"
            return " policy blocker "

    monkeypatch.setattr(esxi_management_recovery, "current_lab_action_policy", lambda mode: ScalarPolicy())
    monkeypatch.setenv("ESXI_RECOVERY_APPLY", "true")
    monkeypatch.setenv("ESXI_RECOVERY_CONFIRM", esxi_management_recovery.RECOVERY_CONFIRM_PHRASE)

    gates = esxi_management_recovery._recovery_gates()

    assert gates["blockers"] == ["policy blocker"]
    assert "p" not in gates["blockers"]


def test_recovery_uses_exact_target_power_on_for_verified_off_host(monkeypatch) -> None:
    _allow_exact_write_target(monkeypatch)
    monkeypatch.setattr(
        esxi_management_recovery,
        "_target_state",
        lambda *, ilo_host=None: _target_state(),
    )
    monkeypatch.setattr(
        esxi_management_recovery,
        "_safe_system_state",
        lambda *, config: {"status_code": 200, "power_state": "Off", "boot": {}},
    )
    monkeypatch.setattr(
        esxi_management_recovery,
        "_safe_ilo_probe",
        lambda *, config: _auth_blocked_probe(),
    )
    monkeypatch.setattr(esxi_management_recovery, "_recovery_gates", lambda: _gates(asserted=True))

    calls: list[bool] = []

    def fake_power_on(
        target: dict,
        *,
        config,
        operator_asserted: bool = False,
    ) -> dict:
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
    assert result["recovery_method"]["method"] == "ilo_redfish_power_on"
    assert result["apply"]["attempted"] is True
    assert calls == [False]


def test_report_paths_use_posix_separators(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(esxi_management_recovery, "REPO_ROOT", tmp_path)

    assert esxi_management_recovery._rel(tmp_path / "artifacts" / "codex-runs" / "report.md") == "artifacts/codex-runs/report.md"


def test_recovery_report_writes_json_atomically(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    monkeypatch.setattr(esxi_management_recovery, "_target_state", _target_state)
    monkeypatch.setattr(
        esxi_management_recovery,
        "_safe_system_state",
        lambda: {"status_code": 401, "power_state": None, "boot": {}},
    )
    monkeypatch.setattr(esxi_management_recovery, "_safe_ilo_probe", _auth_blocked_probe)
    monkeypatch.setattr(esxi_management_recovery, "_recovery_gates", lambda: _gates(asserted=False))

    result = esxi_management_recovery.recover_esxi_management(write_report=True)

    saved = json.loads(esxi_management_recovery.RECOVERY_JSON.read_text(encoding="utf-8"))
    assert saved["action"] == result["action"]
    assert saved["status"] == "blocked"
    assert esxi_management_recovery.RECOVERY_REPORT.read_text(encoding="utf-8").strip()
    assert not list(esxi_management_recovery.CODEX_RUN_DIR.glob("*.tmp"))


def test_post_recovery_validation_writes_json_atomically(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    target = {
        **_target_state(),
        "https_check": {"reachable": True},
        "ssh_check": {"reachable": False},
        "https_reachable": True,
        "ssh_reachable": False,
    }
    monkeypatch.setattr(esxi_management_recovery, "_target_state", lambda: target)

    result = esxi_management_recovery.validate_esxi_post_recovery(write_report=True)

    saved = json.loads(esxi_management_recovery.VALIDATION_JSON.read_text(encoding="utf-8"))
    assert saved["action"] == result["action"]
    assert saved["status"] == "ready"
    assert esxi_management_recovery.VALIDATION_REPORT.read_text(encoding="utf-8").strip()
    assert not list(esxi_management_recovery.CODEX_RUN_DIR.glob("*.tmp"))


def _redirect_reports(monkeypatch, tmp_path: Path) -> None:
    codex_runs = tmp_path / "artifacts" / "codex-runs"
    codex_runs.mkdir(parents=True)
    monkeypatch.setattr(esxi_management_recovery, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(esxi_management_recovery, "CODEX_RUN_DIR", codex_runs)
    monkeypatch.setattr(esxi_management_recovery, "RECOVERY_REPORT", codex_runs / "esxi-reachability-remediation-report.md")
    monkeypatch.setattr(esxi_management_recovery, "RECOVERY_JSON", codex_runs / "esxi-reachability-remediation-redacted.json")
    monkeypatch.setattr(esxi_management_recovery, "VALIDATION_REPORT", codex_runs / "esxi-post-recovery-validation-report.md")
    monkeypatch.setattr(esxi_management_recovery, "VALIDATION_JSON", codex_runs / "esxi-post-recovery-validation-redacted.json")


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
        esxi_management_recovery,
        "resolve_ilo_write_target_context",
        lambda requested_host: (
            (context, [])
            if requested_host == host
            else (None, ["write target mismatch"])
        ),
    )
    monkeypatch.setattr(
        esxi_management_recovery,
        "exact_ilo_write_config",
        lambda resolved: config if resolved == context else None,
    )
    monkeypatch.setattr(
        esxi_management_recovery,
        "refresh_ilo_write_target_context",
        lambda resolved: (
            (context, config, [])
            if resolved == context
            else (None, None, ["write target mismatch"])
        ),
    )
    return context
