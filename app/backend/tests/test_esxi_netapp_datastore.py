from __future__ import annotations

import json
from dataclasses import replace

from app.core.config import settings
from app.services import esxi_netapp_datastore


def test_preview_discovers_govc_host_target(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    monkeypatch.setattr(esxi_netapp_datastore, "_govc_binary", lambda: "/usr/bin/govc")
    monkeypatch.setattr(esxi_netapp_datastore, "_run_govc", _govc_preview_calls)

    payload = esxi_netapp_datastore.build_esxi_netapp_datastore_preview(write_report=False)

    assert payload["status"] == "preview_ready"
    assert payload["target_state"]["esxi_host_target"] == "HomeEsxi."
    assert any(command.endswith(" HomeEsxi.") for command in payload["command_preview"])


def test_apply_passes_govc_host_target(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    monkeypatch.setenv("ESXI_NETAPP_DATASTORE_APPLY", "true")
    monkeypatch.setenv("ESXI_NETAPP_DATASTORE_CONFIRM", "MOUNT NETAPP NFS DATASTORE")
    monkeypatch.setattr(esxi_netapp_datastore, "_govc_binary", lambda: "/usr/bin/govc")
    calls = []

    def fake_govc(args, *, env, timeout):
        calls.append(args)
        if args == ["about"]:
            return {"return_code": 0, "stdout": "", "stderr": ""}
        if args == ["host.info", "-json"]:
            return _host_info()
        if args[:2] == ["datastore.info", "-json"]:
            if any(call and call[0] == "datastore.create" for call in calls):
                return _datastore_info()
            return {"return_code": 1, "stdout": "", "stderr": "datastore not found"}
        if args and args[0] == "datastore.create":
            return {"return_code": 0, "stdout": "", "stderr": ""}
        raise AssertionError(f"unexpected govc call: {args}")

    monkeypatch.setattr(esxi_netapp_datastore, "_run_govc", fake_govc)

    payload = esxi_netapp_datastore.apply_esxi_netapp_datastore(write_report=False)

    assert payload["status"] == "mounted"
    create_calls = [call for call in calls if call and call[0] == "datastore.create"]
    assert create_calls
    assert create_calls[0][-1] == "HomeEsxi."


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
    monkeypatch.setattr(esxi_netapp_datastore, "settings", settings_override)
    monkeypatch.setenv("GOVC_URL", "https://192.168.1.203/sdk")
    monkeypatch.setenv("GOVC_USERNAME", "root")
    monkeypatch.setenv("GOVC_PASSWORD", "configured-value")
    monkeypatch.setenv("GOVC_INSECURE", "true")
    monkeypatch.setattr(esxi_netapp_datastore, "current_lab_action_policy", lambda mode: _AllowPolicy())


class _AllowPolicy:
    def action_blockers(self, action_id, category):
        return []


def _govc_preview_calls(args, *, env, timeout):
    if args == ["about"]:
        return {"return_code": 0, "stdout": "", "stderr": ""}
    if args == ["host.info", "-json"]:
        return _host_info()
    if args[:2] == ["datastore.info", "-json"]:
        return {"return_code": 1, "stdout": "", "stderr": "datastore not found"}
    raise AssertionError(f"unexpected govc call: {args}")


def _host_info() -> dict[str, str | int]:
    return {
        "return_code": 0,
        "stdout": json.dumps({"hostSystems": [{"name": "HomeEsxi."}]}),
        "stderr": "",
    }


def _datastore_info() -> dict[str, str | int]:
    return {
        "return_code": 0,
        "stdout": json.dumps(
            {
                "Datastores": [
                    {
                        "Summary": {
                            "Name": "netapp_nfs_ds01",
                            "Type": "NFS",
                            "Accessible": True,
                        },
                        "host": [{"mountInfo": {"accessMode": "readWrite"}}],
                    }
                ]
            }
        ),
        "stderr": "",
    }
