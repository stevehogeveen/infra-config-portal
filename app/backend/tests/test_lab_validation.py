from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.services import lab_validation
from app.services import vcenter_netapp_readiness
from app.services.lab_validation import (
    build_cisco_validation_item,
    get_lab_validation_summary,
    map_validation_status,
)
from app.services.lab_profiles import create_lab_profile


def test_validation_item_status_mapping() -> None:
    assert map_validation_status(ready=True) == "ready"
    assert map_validation_status(blockers=["blocked"]) == "blocked"
    assert map_validation_status(configured=True, warnings=["warn"]) == "warning"
    assert map_validation_status(checked=False) == "not_checked"
    assert map_validation_status() == "not_configured"


def test_compact_profile_marks_netapp_and_vcenter_validation_not_in_scope(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    create_lab_profile(
        {
            "name": "Compact Edge Lab",
            "subnet_cidr": "10.10.5.0/26",
            "address_plan": {"subnet": "10.10.5.0/26"},
        }
    )

    payload = get_lab_validation_summary(write_report=False)
    items = {item["id"]: item for item in payload["validation_items"]}

    assert items["netapp-console"]["status"] == "not_in_scope"
    assert items["netapp-ontap-cluster"]["status"] == "not_in_scope"
    assert items["vcenter-netapp-datastore"]["status"] == "not_in_scope"
    assert items["netapp-console"]["blockers"] == []
    assert items["netapp-ontap-cluster"]["blockers"] == []
    assert items["vcenter-netapp-datastore"]["blockers"] == []


def test_vcenter_netapp_readiness_is_not_in_scope_for_compact_profile(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    create_lab_profile(
        {
            "name": "Compact Edge Lab",
            "subnet_cidr": "10.10.5.0/26",
            "address_plan": {"subnet": "10.10.5.0/26"},
        }
    )

    result = vcenter_netapp_readiness.get_vcenter_netapp_readiness(write_report=False)

    assert result["status"] == "not_in_scope"
    assert result["blockers"] == []
    assert "active lab profile" in result["message"]


def test_login_hints_do_not_include_secret_values() -> None:
    payload = get_lab_validation_summary(write_report=False)
    serialized = json.dumps(payload).lower()

    assert "password=" not in serialized
    assert "token=" not in serialized
    assert "bearer " not in serialized
    assert "private_key" not in serialized
    assert "credentials not configured" in serialized


def test_ready_cisco_shows_ssh_login_hint() -> None:
    item = build_cisco_validation_item(management_ready=True, target_ip="192.168.1.204")

    assert item["status"] == "ready"
    assert item["login_hint"] == "ssh admin@192.168.1.204"
    assert item["ssh_target"] == "admin@192.168.1.204"


def test_netapp_cluster_setup_wizard_blocks_vcenter_netapp_readiness(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    create_lab_profile(
        {
            "name": "High Storage Lab",
            "subnet_cidr": "192.168.1.0/24",
            "features": {"netapp_enabled": True, "vcenter_enabled": True},
        }
    )
    monkeypatch.setattr(vcenter_netapp_readiness, "settings", _vcenter_netapp_settings())
    monkeypatch.setattr(vcenter_netapp_readiness, "which", lambda _: "/usr/bin/govc")
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "get_netapp_runtime_state",
        lambda: {
            "configured": False,
            "configured_state": "setup_wizard",
            "console": {"prompt_state": "cluster_setup_prompt"},
        },
    )

    result = vcenter_netapp_readiness.get_vcenter_netapp_readiness()

    assert result["status"] == "blocked_by_prior_stage"
    assert result["netapp_stage"] == "cluster_setup_wizard"
    assert any("cluster_setup_wizard" in blocker for blocker in result["blockers"])


def test_vcenter_not_configured_is_not_configured_yet(monkeypatch, tmp_path) -> None:
    _patch_vcenter_netapp_paths(monkeypatch, tmp_path)
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    create_lab_profile(
        {
            "name": "High Storage Lab",
            "subnet_cidr": "192.168.1.0/24",
            "features": {"netapp_enabled": True, "vcenter_enabled": True},
        }
    )
    monkeypatch.setattr(
            vcenter_netapp_readiness,
            "settings",
            _vcenter_netapp_settings(vcenter_host=None, vcenter_configured=False, vcenter_management_ip=None),
        )
    monkeypatch.setattr(vcenter_netapp_readiness, "which", lambda _: "/usr/bin/govc")
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "get_netapp_runtime_state",
        lambda: {"configured": True, "configured_state": "configured", "console": {}},
    )

    result = vcenter_netapp_readiness.get_vcenter_netapp_readiness()

    assert result["status"] == "not_configured_yet"
    assert any("VCENTER_HOST" in blocker or "GOVC_URL" in blocker for blocker in result["blockers"])


def test_vcenter_netapp_readiness_uses_ready_post_attach_state_without_host_env(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _enable_high_storage_profile(monkeypatch, tmp_path)
    _patch_vcenter_netapp_paths(monkeypatch, tmp_path)
    _write_post_attach_validation(tmp_path)
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "settings",
        _vcenter_netapp_settings(
            vcenter_host=None,
            vcenter_configured=False,
            vcenter_management_ip=None,
            vcenter_username=None,
            vcenter_password=None,
        ),
    )
    monkeypatch.setattr(vcenter_netapp_readiness, "which", lambda _: None)
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "get_netapp_runtime_state",
        lambda: {"configured": True, "configured_state": "configured", "console": {}},
    )

    result = vcenter_netapp_readiness.get_vcenter_netapp_readiness(write_report=True)

    assert result["status"] == "ready"
    assert result["blockers"] == []
    assert result["targets"]["vcenter"] == "https://192.168.1.206/sdk"
    assert result["targets"]["datastore_name"] == "netapp_nfs_ds01"
    assert result["current_state"]["vcenter_version"] == "8.0.3 build-24853646"
    assert result["checks"]["vcenter_configured"]["status"] == "ready"
    assert result["checks"]["datastore_mounted"]["status"] == "ready"
    assert result["credential_state"]["vcenter_target_derived"] is True
    assert "No vCenter-NetApp datastore action required" in result["next_safe_action"]
    assert "VCENTER_HOST" not in json.dumps(result["blockers"])
    assert (tmp_path / "artifacts/codex-runs/vcenter-netapp-readiness-report.md").exists()


def test_lab_validation_marks_vcenter_netapp_ready_from_post_attach_state(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _enable_high_storage_profile(monkeypatch, tmp_path)
    _patch_lab_validation_paths(monkeypatch, tmp_path)
    _patch_vcenter_netapp_paths(monkeypatch, tmp_path)
    _write_post_attach_validation(tmp_path)
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "settings",
        _vcenter_netapp_settings(
            vcenter_host=None,
            vcenter_configured=False,
            vcenter_management_ip=None,
            vcenter_username=None,
            vcenter_password=None,
        ),
    )
    monkeypatch.setattr(vcenter_netapp_readiness, "which", lambda _: None)
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "get_netapp_runtime_state",
        lambda: {"configured": True, "configured_state": "configured", "console": {}},
    )
    monkeypatch.setattr(
        lab_validation,
        "get_netapp_runtime_state",
        lambda: {"configured": True, "configured_state": "configured", "console": {}},
    )
    monkeypatch.setattr(
        lab_validation,
        "get_lab_build_verification",
        lambda: {
            "status": "completed",
            "message": "Build Verification completed.",
            "source_type": "live_probe",
            "freshness": "current",
            "checked_at": "2026-06-14T20:00:00+00:00",
            "blockers": [],
            "warnings": [],
            "next_safe_action": "Review warnings, then continue product certification.",
        },
    )

    payload = lab_validation.get_lab_validation_summary(write_report=True)
    items = {item["id"]: item for item in payload["validation_items"]}

    assert items["vcenter-netapp-datastore"]["status"] == "ready"
    assert items["vcenter-netapp-datastore"]["management_url"] == "https://192.168.1.206/sdk"
    assert "No vCenter-NetApp datastore action required" in items["vcenter-netapp-datastore"]["next_action"]
    assert "VCENTER_HOST / GOVC_URL not configured" not in items["vcenter-netapp-datastore"]["login_hint"]
    report = (tmp_path / "artifacts/codex-runs/lab-validation-handoff-report.md").read_text(encoding="utf-8")
    assert "| vCenter-NetApp Datastore | `ready` |" in report
    assert "No vCenter-NetApp datastore action required" in report


def test_handoff_remaining_items_collapses_supporting_partials_to_firmware() -> None:
    items = [
        {"id": "firmware-compliance", "label": "Firmware Compliance", "status": "partial", "next_action": "Refresh firmware compliance."},
        {"id": "hpe-ilo", "label": "HPE / iLO", "status": "partial", "next_action": "Refresh iLO evidence.", "blockers": []},
        {"id": "raid-storage", "label": "RAID / Storage", "status": "partial", "next_action": "Refresh RAID evidence.", "blockers": []},
        {"id": "esxi-host", "label": "ESXi Host", "status": "partial", "next_action": "Refresh ESXi evidence.", "blockers": []},
        {"id": "vcenter-netapp-datastore", "label": "vCenter-NetApp Datastore", "status": "ready", "next_action": "No action required."},
    ]

    remaining = lab_validation._remaining_items(items)

    assert [item["id"] for item in remaining] == ["firmware-compliance"]
    next_action = lab_validation._summary_next_action(None, remaining)
    assert "Refresh firmware compliance" in next_action
    assert "No vCenter-NetApp datastore action required" in next_action


def test_firmware_handoff_includes_upgrade_path_summary(monkeypatch) -> None:
    monkeypatch.setattr(
        lab_validation,
        "get_firmware_compliance",
        lambda **_: {
            "checked_at": "2026-06-14T20:00:00+00:00",
            "source_type": "historical_evidence",
            "upgrade_paths": [
                {
                    "device_label": "Cisco",
                    "component_label": "Cisco IOS XE",
                    "current_version": "17.15.05",
                    "target_version": "17.15.05",
                    "path_status": "current",
                    "package_name": "firmware-1.bin",
                    "evidence_artifacts": [],
                },
                {
                    "device_label": "HPE Server",
                    "component_label": "HPE BIOS",
                    "current_version": "U32 v3.30",
                    "target_version": None,
                    "path_status": "manual_review",
                    "package_name": None,
                    "disabled_reason": "Manual review required: missing target baseline.",
                    "evidence_artifacts": [],
                },
            ],
        },
    )

    item = lab_validation._firmware_item({})
    markdown = lab_validation._handoff_markdown(
        {
            "generated_at": "2026-06-14T20:00:00+00:00",
            "overall_status": "partial",
            "validation_items": [item],
            "proof_links": [],
            "top_blocker": None,
        }
    )

    assert item["status"] == "partial"
    assert "1/2 firmware/software components current" in item["current_state"]
    assert "Cisco Cisco IOS XE: current 17.15.05, target 17.15.05, path current, package firmware-1.bin." in item["proof_points"]
    assert "HPE Server HPE BIOS: current U32 v3.30, target manual review, path manual_review, package not available." in item["proof_points"]
    assert "Open Firmware Upgrades" in item["next_action"]
    assert "## What Remains" in markdown
    assert "HPE Server HPE BIOS: current U32 v3.30" in markdown
    assert "raw" not in markdown.lower()


def test_vcenter_netapp_readiness_finds_repo_local_govc(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    create_lab_profile(
        {
            "name": "High Storage Lab",
            "subnet_cidr": "192.168.1.0/24",
            "features": {"netapp_enabled": True, "vcenter_enabled": True},
        }
    )
    local_bin = tmp_path / ".local" / "bin"
    local_bin.mkdir(parents=True)
    govc = local_bin / "govc"
    govc.write_text("#!/bin/sh\n", encoding="utf-8")
    govc.chmod(0o755)
    _patch_vcenter_netapp_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(vcenter_netapp_readiness, "which", lambda _: None)
    monkeypatch.setattr(vcenter_netapp_readiness, "settings", _vcenter_netapp_settings())
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "get_netapp_runtime_state",
        lambda: {"configured": True, "configured_state": "configured", "console": {}},
    )

    result = vcenter_netapp_readiness.get_vcenter_netapp_readiness()

    assert result["status"] == "ready"
    assert result["tooling"]["govc_available"] is True


def test_evidence_artifacts_are_collapsed_supporting_metadata() -> None:
    payload = get_lab_validation_summary(write_report=False)

    assert payload["validation_items"]
    assert all(item["evidence_collapsed_by_default"] is True for item in payload["validation_items"])
    assert "proof_links" in payload


def test_lab_validation_api_payload_shape(client: TestClient) -> None:
    response = client.get("/api/v1/lab/validation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["overall_status"]
    assert "progress_counts" in payload
    assert "validation_items" in payload
    assert "proof_links" in payload
    assert "generated_at" in payload
    assert "next_action" in payload
    assert any(item["id"] == "vcenter-netapp-datastore" for item in payload["validation_items"])


def _vcenter_netapp_settings(**overrides):
    values = {
        "provider_mode": "mock",
        "vcenter_host": "https://vcenter.example/sdk",
        "vcenter_configured": True,
        "vcenter_management_ip": None,
        "vcenter_username": "configured-user",
        "vcenter_password": "configured-password",
        "vcenter_sso_admin_username": "administrator@vsphere.local",
        "vcenter_sso_admin_password": "configured-password",
        "netapp_api_username": "configured-user",
        "netapp_api_password": "configured-password",
        "netapp_cluster_mgmt_ip": "192.168.1.220",
        "netapp_svm_mgmt_ip": "192.168.1.223",
        "netapp_nfs_lifs": ("192.168.1.230", "192.168.1.231"),
        "netapp_nfs_volume": "esxi_datastore_01",
        "netapp_nfs_export_policy": "esxi_nfs_policy",
        "netapp_nfs_mount_path": "/esxi_datastore_01",
        "netapp_nfs_datastore_name": "netapp_nfs_ds01",
        "netapp_nfs_client_match": "192.168.1.0/24",
        "esxi_test_host": "192.168.1.203",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _enable_high_storage_profile(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    create_lab_profile(
        {
            "name": "High Storage Lab",
            "subnet_cidr": "192.168.1.0/24",
            "features": {"netapp_enabled": True, "vcenter_enabled": True},
        }
    )


def _patch_vcenter_netapp_paths(monkeypatch, tmp_path: Path) -> None:
    run_dir = tmp_path / "artifacts" / "codex-runs"
    monkeypatch.setattr(vcenter_netapp_readiness, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(vcenter_netapp_readiness, "CODEX_RUN_DIR", run_dir)
    monkeypatch.setattr(vcenter_netapp_readiness, "READINESS_REPORT", run_dir / "vcenter-netapp-readiness-report.md")
    monkeypatch.setattr(vcenter_netapp_readiness, "PLAN_REPORT", run_dir / "vcenter-netapp-datastore-plan-report.md")
    monkeypatch.setattr(vcenter_netapp_readiness, "READINESS_JSON", run_dir / "vcenter-netapp-readiness-redacted.json")
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "VCENTER_POST_ATTACH_VALIDATION_JSON",
        run_dir / "vcenter-post-attach-validation-redacted.json",
    )


def _patch_lab_validation_paths(monkeypatch, tmp_path: Path) -> None:
    run_dir = tmp_path / "artifacts" / "codex-runs"
    monkeypatch.setattr(lab_validation, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(lab_validation, "CODEX_RUN_DIR", run_dir)
    monkeypatch.setattr(lab_validation, "HANDOFF_REPORT", run_dir / "lab-validation-handoff-report.md")
    monkeypatch.setattr(lab_validation, "SUMMARY_JSON", run_dir / "lab-validation-summary-redacted.json")


def _write_post_attach_validation(root: Path) -> None:
    run_dir = root / "artifacts" / "codex-runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "vcenter-post-attach-validation-redacted.json").write_text(
        json.dumps(
            {
                "status": "ready",
                "checked_at": "2026-06-14T20:00:00+00:00",
                "source_type": "live_provider",
                "freshness": "live",
                "target": {
                    "host": "192.168.1.206",
                    "url": "https://192.168.1.206/sdk",
                    "username_configured": True,
                    "credential_configured": True,
                    "govc_available": True,
                    "govc_configured": True,
                    "esxi_target": "192.168.1.203",
                    "datastore": "netapp_nfs_ds01",
                    "datacenter": "Lab-DC",
                    "cluster": "Lab-Cluster",
                },
                "checks": {
                    "govc_authentication": {
                        "status": "ready",
                        "return_code": 0,
                        "stdout": "Version:      8.0.3\nBuild:        24853646\n",
                    },
                    "datacenter_visible": {"visible": True, "status": "ready", "name": "Lab-DC"},
                    "cluster_visible": {"visible": True, "status": "ready", "name": "Lab-Cluster"},
                    "esxi_visible": {"visible": True, "status": "ready", "name": "192.168.1.203"},
                    "netapp_datastore_visible": {
                        "visible": True,
                        "status": "ready",
                        "name": "netapp_nfs_ds01",
                        "paths": ["/Lab-DC/datastore/netapp_nfs_ds01"],
                    },
                    "vm_inventory_visible": {"visible": True, "status": "ready", "count": 4},
                },
                "blockers": [],
                "warnings": [],
                "recheck_command": "make provider-lab-vcenter-post-attach-validation",
            }
        ),
        encoding="utf-8",
    )
