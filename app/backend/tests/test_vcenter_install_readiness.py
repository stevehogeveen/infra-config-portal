from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from app.services import vcenter_netapp_readiness


def test_vcenter_install_readiness_reports_incomplete_values(monkeypatch, tmp_path: Path) -> None:
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(vcenter_netapp_readiness, "settings", _settings())
    monkeypatch.setattr(vcenter_netapp_readiness, "active_lab_profile_context", lambda: _profile_context())
    monkeypatch.setattr(vcenter_netapp_readiness, "_tool_available", lambda _name: False)

    result = vcenter_netapp_readiness.get_vcenter_install_readiness(check_ports=False, write_report=True)

    assert result["status"] == "blocked"
    assert result["deployment_values"]["complete"] is False
    assert "VCENTER_APPLIANCE_NAME" in result["deployment_values"]["missing_fields"]
    assert result["credential_state"]["deployment_credentials_configured"] is False
    assert result["apply_enabled"] is False
    assert (tmp_path / "artifacts/codex-runs/vcenter-install-readiness-redacted.json").exists()


def test_vcenter_install_preview_uses_redacted_value_and_credential_status(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _patch_paths(monkeypatch, tmp_path)
    media = tmp_path / "artifacts" / "Media" / "VMware-VCSA-all-8.0.3.iso"
    vcsa_deploy = tmp_path / "vcsa-cli-installer" / "lin64" / "vcsa-deploy"
    media.parent.mkdir(parents=True)
    vcsa_deploy.parent.mkdir(parents=True)
    media.write_bytes(b"vcsa")
    vcsa_deploy.write_text("#!/bin/sh\n", encoding="utf-8")
    vcsa_deploy.chmod(0o755)
    _write_datastore_validation(tmp_path)
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "settings",
        _settings(
            media_inventory_dirs=(str(media.parent),),
            vcenter_appliance_name="vcsa01",
            vcenter_management_ip="192.168.1.206",
            vcenter_subnet_cidr="192.168.1.0/24",
            vcenter_gateway="192.168.1.1",
            vcenter_dns_servers=("192.168.1.1",),
            vcenter_ntp_servers=("192.168.1.1",),
            vcenter_sso_domain="vsphere.local",
            vcenter_sso_admin_username="administrator@vsphere.local",
            vcenter_sso_admin_password="super-secret-sso",
            vcenter_appliance_root_password="super-secret-root",
            vcenter_esxi_target="192.168.1.203",
            vcenter_datastore_target="netapp_nfs_ds01",
            vcenter_deployment_size="tiny",
            vcenter_network="VM Network",
            vcenter_vcsa_deploy_path=str(vcsa_deploy),
            esxi_test_username="root",
            esxi_test_password="super-secret-esxi",
        ),
    )
    monkeypatch.setattr(vcenter_netapp_readiness, "active_lab_profile_context", lambda: _profile_context())
    monkeypatch.setattr(vcenter_netapp_readiness, "_tool_available", lambda _name: True)
    monkeypatch.setattr(vcenter_netapp_readiness, "_tcp_check", _tcp_ready)
    monkeypatch.setattr(vcenter_netapp_readiness, "_ip_available_check", _ip_available)

    result = vcenter_netapp_readiness.get_vcenter_install_preview(write_report=True)
    serialized = json.dumps(result)

    assert result["status"] == "ready"
    assert result["action"] == "vcenter-install-preview"
    assert result["deployment_values"]["complete"] is True
    assert result["credential_state"]["deployment_credentials_configured"] is True
    assert result["install_plan"]["deploy_apply_enabled"] is False
    assert "super-secret" not in serialized
    assert (tmp_path / "artifacts/codex-runs/vcenter-install-preview-redacted.json").exists()
    assert (tmp_path / "artifacts/codex-runs/vcenter-install-preview-report.md").exists()


def test_vcsa_deploy_is_found_under_mounted_iso(monkeypatch, tmp_path: Path) -> None:
    mounted = tmp_path / "vcsa-iso"
    deploy = mounted / "vcsa-cli-installer" / "lin64" / "vcsa-deploy"
    deploy.parent.mkdir(parents=True)
    deploy.write_text("#!/bin/sh\n", encoding="utf-8")
    deploy.chmod(0o755)
    monkeypatch.setattr(vcenter_netapp_readiness, "settings", _settings())
    monkeypatch.setattr(vcenter_netapp_readiness, "VCSA_MOUNT_ROOTS", (mounted,))

    result = vcenter_netapp_readiness._vcsa_deploy_status()

    assert result["status"] == "ready"
    assert result["executable"] is True
    assert result["path"] == str(deploy.resolve())


def _patch_paths(monkeypatch, tmp_path: Path) -> None:
    run_dir = tmp_path / "artifacts" / "codex-runs"
    monkeypatch.setattr(vcenter_netapp_readiness, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(vcenter_netapp_readiness, "CODEX_RUN_DIR", run_dir)
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_INSTALL_READINESS_REPORT", run_dir / "vcenter-install-readiness-report.md")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_INSTALL_PLAN_REPORT", run_dir / "vcenter-install-plan-report.md")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_INSTALL_PREVIEW_REPORT", run_dir / "vcenter-install-preview-report.md")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_INSTALL_READINESS_JSON", run_dir / "vcenter-install-readiness-redacted.json")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_INSTALL_PLAN_JSON", run_dir / "vcenter-install-plan-redacted.json")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_INSTALL_PREVIEW_JSON", run_dir / "vcenter-install-preview-redacted.json")


def _settings(**overrides) -> SimpleNamespace:
    values = {
        "provider_mode": "local-readonly",
        "media_inventory_dirs": (),
        "lab_subnet_cidr": "192.168.1.0/24",
        "esxi_test_host": "192.168.1.203",
        "esxi_test_username": None,
        "esxi_test_password": None,
        "netapp_nfs_lifs": ("192.168.1.230",),
        "netapp_nfs_datastore_name": "netapp_nfs_ds01",
        "vcenter_configured": False,
        "vcenter_host": None,
        "vcenter_username": None,
        "vcenter_password": None,
        "vcenter_appliance_name": None,
        "vcenter_management_ip": None,
        "vcenter_subnet_cidr": None,
        "vcenter_gateway": None,
        "vcenter_dns_servers": (),
        "vcenter_ntp_servers": (),
        "vcenter_sso_domain": None,
        "vcenter_sso_admin_username": None,
        "vcenter_sso_admin_password": None,
        "vcenter_appliance_root_password": None,
        "vcenter_esxi_target": None,
        "vcenter_datastore_target": None,
        "vcenter_vcsa_iso_path": None,
        "vcenter_vcsa_deploy_path": None,
        "vcenter_deployment_size": "tiny",
        "vcenter_network": None,
        "vcenter_portgroup": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _profile_context() -> dict:
    return {
        "enabled_features": {"netapp_enabled": True, "vcenter_enabled": False},
        "resolved_address_plan": {"subnet": "192.168.1.0/24", "esxi_management": "192.168.1.203"},
        "active_profile": {
            "global_settings": {
                "gateway": "192.168.1.1",
                "dns_servers": ["192.168.1.1"],
                "ntp_servers": ["192.168.1.1"],
            }
        },
    }


def _tcp_ready(label: str, host: str | None, port: int, *, check_ports: bool) -> dict:
    return {
        "label": label,
        "host": host,
        "port": port,
        "status": "ready",
        "detail": f"TCP {port} reachable.",
        "source_type": "live_provider",
        "freshness": "live",
    }


def _ip_available(label: str, host: str | None, *, check_ports: bool) -> dict:
    return {
        "label": label,
        "host": host,
        "status": "ready",
        "detail": "Management IP appears available for VCSA deployment.",
        "available": True,
        "source_type": "live_provider",
        "freshness": "live",
    }


def _write_datastore_validation(root: Path) -> None:
    run_dir = root / "artifacts" / "codex-runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "esxi-netapp-nfs-datastore-validation-redacted.json").write_text(
        json.dumps(
            {
                "status": "ready",
                "current_state": {
                    "exists": True,
                    "accessible": True,
                    "summary": {"name": "netapp_nfs_ds01", "access_mode": "readWrite"},
                },
            }
        ),
        encoding="utf-8",
    )
