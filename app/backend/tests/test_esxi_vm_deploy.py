from __future__ import annotations

from dataclasses import replace

from app.core.config import settings
from app.services import esxi_vm_deploy


def test_esxi_vm_deploy_preview_blocks_when_netapp_datastore_is_not_visible(monkeypatch, tmp_path) -> None:
    ovf = tmp_path / "template.ovf"
    ovf.write_text("<Envelope />", encoding="utf-8")
    _patch_settings(monkeypatch)
    monkeypatch.setenv("VM_DEPLOY_OVF_PATH", str(ovf))
    monkeypatch.setattr(esxi_vm_deploy, "_govc_binary", lambda: "/usr/bin/govc")
    monkeypatch.setattr(esxi_vm_deploy, "_run_govc", _govc_datastore_missing)

    payload = esxi_vm_deploy.build_esxi_vm_deploy_preview(write_report=False)

    assert payload["status"] == "blocked"
    assert payload["apply_enabled"] is False
    assert payload["deployment_plan"]["datastore"] == "netapp_nfs_ds01"
    assert payload["deployment_plan"]["target_is_netapp_nfs"] is True
    assert payload["datastore_check"]["exists"] is False
    assert any("not mounted on ESXi" in blocker for blocker in payload["blockers"])
    assert any("govc import.ovf" in command for command in payload["command_preview"])


def test_esxi_vm_deploy_apply_refuses_without_flags_and_datastore(monkeypatch, tmp_path) -> None:
    ovf = tmp_path / "template.ovf"
    ovf.write_text("<Envelope />", encoding="utf-8")
    _patch_settings(monkeypatch)
    monkeypatch.setenv("VM_DEPLOY_OVF_PATH", str(ovf))
    monkeypatch.delenv("VM_DEPLOY_APPLY", raising=False)
    monkeypatch.delenv("VM_DEPLOY_CONFIRM", raising=False)
    monkeypatch.delenv("VM_DEPLOY_ALLOW_CREATE", raising=False)
    monkeypatch.setattr(esxi_vm_deploy, "_govc_binary", lambda: "/usr/bin/govc")
    monkeypatch.setattr(esxi_vm_deploy, "_run_govc", _govc_datastore_missing)

    payload = esxi_vm_deploy.apply_esxi_vm_deploy(write_report=False)

    assert payload["status"] == "blocked"
    assert payload["apply_enabled"] is False
    assert payload["apply"]["govc_import_ovf_attempted"] is False
    assert any("VM_DEPLOY_APPLY=true" in blocker for blocker in payload["blockers"])
    assert any("VM_DEPLOY_ALLOW_CREATE=true" in blocker for blocker in payload["blockers"])
    assert any("Target datastore `netapp_nfs_ds01`" in blocker for blocker in payload["blockers"])


def _patch_settings(monkeypatch) -> None:
    settings_override = replace(
        settings,
        provider_mode="local-lab-readwrite",
        lab_environment="isolated-real-lab",
        lab_acknowledge_real_hardware=True,
        lab_acknowledge_device_reconfiguration=True,
        lab_acknowledge_data_loss_risk=True,
        lab_acknowledge_lab_only=True,
        esxi_configured=True,
        esxi_test_host="192.168.1.203",
        esxi_test_username="root",
        esxi_test_password="configured-value",
        esxi_test_verify_tls=False,
        netapp_nfs_datastore_name="netapp_nfs_ds01",
        netapp_nfs_lifs=("192.168.1.230", "192.168.1.231"),
        netapp_nfs_mount_path="/esxi_datastore_01",
    )
    monkeypatch.setattr(esxi_vm_deploy, "settings", settings_override)


def _govc_datastore_missing(args, *, env, timeout):
    if args[:2] == ["datastore.info", "-json"]:
        return {"return_code": 1, "stdout": "", "stderr": "datastore not found"}
    raise AssertionError(f"unexpected govc call: {args}")
