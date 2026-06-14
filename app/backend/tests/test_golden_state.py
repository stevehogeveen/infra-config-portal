from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.services import golden_state


def test_golden_state_aggregates_known_good_rows(monkeypatch, tmp_path: Path) -> None:
    _patch_paths(monkeypatch, tmp_path)
    _write_golden_artifacts(tmp_path)
    monkeypatch.setattr(golden_state, "get_lab_build_verification", lambda: _build_verification())
    monkeypatch.setattr(
        golden_state,
        "get_media_inventory",
        lambda: SimpleNamespace(items=[SimpleNamespace(category="iso", product_hints=["vmware-vcenter"])]),
    )

    result = golden_state.get_provider_lab_golden_state(write_report=True)
    rows = {row["id"]: row for row in result["rows"]}

    assert result["status"] == "partial"
    assert result["blockers"] == []
    assert rows["cisco"]["status"] == "ready"
    assert rows["ilo"]["status"] == "ready"
    assert rows["raid"]["status"] == "ready"
    assert rows["esxi"]["status"] == "ready"
    assert rows["netapp"]["current_state"] == "ONTAP 9.17.1"
    assert rows["netapp-nfs-datastore"]["current_state"] == "netapp_nfs_ds01 readWrite"
    assert rows["vm-deployment"]["status"] == "ready"
    assert rows["vcenter"]["status"] == "not_configured"
    assert rows["firmware"]["status"] == "warning"
    assert result["vcenter_readiness"]["vcsa_iso"] == "found"
    assert result["vcenter_readiness"]["esxi"] == "ready"
    assert result["vcenter_readiness"]["netapp_datastore"] == "ready"
    assert result["artifacts"]["report"] == "artifacts/codex-runs/golden-state-productization-report.md"
    assert (tmp_path / result["artifacts"]["report"]).exists()


def test_golden_state_credentials_are_presence_only(monkeypatch, tmp_path: Path) -> None:
    _patch_paths(monkeypatch, tmp_path)
    _write_golden_artifacts(tmp_path)
    monkeypatch.setattr(golden_state, "get_lab_build_verification", lambda: _build_verification())

    result = golden_state.get_provider_lab_golden_state(write_report=False)
    serialized = json.dumps(result).lower()

    assert "length" not in serialized
    assert "quoted_length" not in serialized
    assert "super-secret" not in serialized
    assert all({"configured", "tested", "status"}.issubset(row) for row in result["credentials"]["rows"])


def test_golden_state_api_shape(client: TestClient) -> None:
    response = client.get("/api/v1/lab/golden-state")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_id"] == "provider-lab-golden-state"
    assert "rows" in payload
    assert "credentials" in payload
    assert "vcenter_readiness" in payload
    assert any(row["id"] == "netapp-nfs-datastore" for row in payload["rows"])


def _patch_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(golden_state, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(golden_state, "CODEX_RUN_DIR", tmp_path / "artifacts" / "codex-runs")
    monkeypatch.setattr(golden_state, "GOLDEN_REPORT", tmp_path / "artifacts" / "codex-runs" / "golden-state-productization-report.md")
    monkeypatch.setattr(golden_state, "GOLDEN_JSON", tmp_path / "artifacts" / "codex-runs" / "golden-state-summary-redacted.json")


def _write_golden_artifacts(root: Path) -> None:
    run_dir = root / "artifacts" / "codex-runs"
    run_dir.mkdir(parents=True)
    _write_json(
        run_dir / "provider-lab-live-status-redacted.json",
        {
            "stages": [
                {"stage": "ilo-reachability", "status": "completed", "warnings": []},
                {"stage": "cisco-console-ethernet", "status": "ready", "warnings": []},
                {"stage": "netapp-live-state", "status": "ready", "warnings": []},
                {"stage": "firmware-compliance", "status": "warning", "warnings": ["Manual firmware review remains."]},
            ]
        },
    )
    _write_json(run_dir / "esxi-post-recovery-validation-redacted.json", {"status": "ready"})
    _write_json(
        run_dir / "esxi-netapp-nfs-datastore-validation-redacted.json",
        {
            "status": "ready",
            "current_state": {
                "exists": True,
                "accessible": True,
                "summary": {"name": "netapp_nfs_ds01", "access_mode": "readWrite"},
            },
        },
    )
    _write_json(
        run_dir / "esxi-vm-deploy-validation-redacted.json",
        {"status": "ready", "deployment_plan": {"datastore": "netapp_nfs_ds01"}},
    )
    _write_json(
        run_dir / "netapp-ontap-upgrade-validation-redacted.json",
        {"status": "current", "current_version": "9.17.1", "target_version": "9.17.1"},
    )
    _write_json(run_dir / "vcenter-install-readiness-redacted.json", {"current_state": {"vcsa_iso": "configured-directory-1"}})
    (run_dir / "hpe-raid-after-reset-validation-report.md").write_text(
        "Status: succeeded\nMatches saved intent: True\n",
        encoding="utf-8",
    )
    for name in [
        "cisco-console-ethernet-readiness-report.md",
        "ilo-real-run-report.md",
        "esxi-post-recovery-validation-report.md",
        "netapp-live-state-report.md",
        "netapp-ontap-upgrade-validation-report.md",
        "esxi-netapp-nfs-datastore-validation-report.md",
        "esxi-vm-deploy-validation-report.md",
        "vcenter-install-readiness-report.md",
        "firmware-compliance-report.md",
    ]:
        (run_dir / name).write_text("redacted report\n", encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _build_verification() -> dict:
    return {
        "credentials": {
            "checks": [
                {"name": "ilo", "configured": True, "classification": "passed", "field": "ILO_TEST_PASSWORD"},
                {"name": "cisco", "configured": True, "classification": "passed", "field": "CISCO_TEST_PASSWORD"},
                {
                    "name": "cisco_enable",
                    "configured": True,
                    "classification": "passed",
                    "field": "CISCO_ENABLE_PASSWORD",
                },
                {"name": "esxi", "configured": True, "classification": "passed", "field": "ESXI_TEST_PASSWORD"},
                {"name": "netapp", "configured": True, "classification": "passed", "field": "NETAPP_API_PASSWORD"},
            ]
        }
    }
