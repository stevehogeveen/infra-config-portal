from __future__ import annotations

from app.services import esxi_iscsi_datastore


def test_esxi_iscsi_preview_reports_readonly_evidence(monkeypatch) -> None:
    _patch_common(monkeypatch)

    payload = esxi_iscsi_datastore.build_esxi_iscsi_datastore_preview(write_report=False)

    assert payload["status"] == "preview_ready"
    assert payload["source_type"] == "live_probe"
    assert payload["current_state"]["adapter_count"] == 1
    assert payload["current_state"]["iscsi_path_count"] == 1
    assert payload["current_state"]["target_iqn_seen"] is True
    assert payload["current_state"]["datastore_visible"] is True
    assert payload["remediation_plan"]["status"] == "ready"
    assert payload["remediation_plan"]["read_only"] is True
    assert "VMFS format" in payload["not_attempted"]


def test_esxi_iscsi_validation_blocks_when_datastore_is_not_visible(monkeypatch) -> None:
    _patch_common(monkeypatch, filesystem_stdout="")

    payload = esxi_iscsi_datastore.validate_esxi_iscsi_datastore(write_report=False)

    assert payload["status"] == "blocked"
    assert "ESXi VMFS datastore `netapp_iscsi_ds01` is not visible." in payload["blockers"]
    assert payload["current_state"]["target_iqn_seen"] is True
    remediation = payload["remediation_plan"]
    assert remediation["status"] == "blocked"
    assert "iSCSI remediation step" in remediation["summary"]
    vmfs_step = _step_by_label(remediation, "Confirm VMFS datastore visibility")
    assert vmfs_step["status"] == "blocked"
    assert "guarded datastore create or mount lane" in vmfs_step["next_action"]


def test_esxi_iscsi_validation_blocks_when_target_session_is_missing(monkeypatch) -> None:
    _patch_common(monkeypatch, session_stdout="")

    payload = esxi_iscsi_datastore.validate_esxi_iscsi_datastore(write_report=False)

    assert payload["status"] == "blocked"
    assert "ESXi does not show an active iSCSI session to the NetApp target IQN." in payload["blockers"]
    remediation = payload["remediation_plan"]
    assert remediation["status"] == "blocked"
    session_step = _step_by_label(remediation, "Establish active iSCSI session")
    assert session_step["status"] == "blocked"
    assert "Add the NetApp target portal" in session_step["next_action"]
    assert "adapter rescan" in remediation["apply_not_attempted"]


def test_esxi_iscsi_preview_keeps_netapp_blockers(monkeypatch) -> None:
    _patch_common(monkeypatch, netapp_blockers=["NetApp iSCSI LUN is missing."])

    payload = esxi_iscsi_datastore.build_esxi_iscsi_datastore_preview(write_report=False)

    assert payload["status"] == "blocked"
    assert "NetApp iSCSI LUN is missing." in payload["blockers"]


def _patch_common(
    monkeypatch,
    *,
    filesystem_stdout: str | None = None,
    session_stdout: str | None = None,
    netapp_blockers: list[str] | None = None,
) -> None:
    monkeypatch.setattr(
        esxi_iscsi_datastore,
        "_ssh_target_state",
        lambda: {
            "host": "192.168.1.203",
            "can_query": True,
            "missing_fields": [],
        },
    )
    monkeypatch.setattr(esxi_iscsi_datastore, "build_netapp_iscsi_setup_preview", lambda write_report=False: _netapp_preview())
    monkeypatch.setattr(
        esxi_iscsi_datastore,
        "validate_netapp_iscsi_setup",
        lambda write_report=False: _netapp_validation(netapp_blockers or []),
    )

    def fake_ssh(command: str, *, timeout: int = 60) -> dict[str, object]:
        if command == "esxcli iscsi adapter list":
            return {"return_code": 0, "stdout": "vmhba64  iqn.1998-01.com.vmware:host-a  online\n", "stderr": ""}
        if command == "esxcli iscsi session list":
            stdout = session_stdout
            if stdout is None:
                stdout = "Adapter: vmhba64\nTarget: iqn.1992-08.com.netapp:sn.test\nISID: 00023d000001\n\n"
            return {
                "return_code": 0,
                "stdout": stdout,
                "stderr": "",
            }
        if command == "esxcli storage core device list":
            return {
                "return_code": 0,
                "stdout": "naa.600a098038314f6c2f5d50774d315268\n   Display Name: NETAPP iSCSI Disk esxi_lun_01\n",
                "stderr": "",
            }
        if command == "esxcli storage filesystem list":
            stdout = filesystem_stdout
            if stdout is None:
                stdout = "/vmfs/volumes/abc  netapp_iscsi_ds01  abc true VMFS-6 1048576 524288\n"
            return {"return_code": 0, "stdout": stdout, "stderr": ""}
        raise AssertionError(f"unexpected SSH command: {command}")

    monkeypatch.setattr(esxi_iscsi_datastore, "_run_esxi_ssh", fake_ssh)


def _netapp_preview() -> dict[str, object]:
    return {
        "iscsi_plan": {
            "datastore_name": "netapp_iscsi_ds01",
            "vmfs_version": "VMFS6",
            "preferred_iscsi_lif": "192.168.1.240",
            "iscsi_lifs": ["192.168.1.240"],
            "lun_path": "/vol/esxi_datastore_01/esxi_lun_01",
            "lun_name": "esxi_lun_01",
            "igroup_name": "esxi_hosts",
            "initiator_iqns": ["iqn.1998-01.com.vmware:host-a"],
        },
        "current_state": {
            "iscsi_service": {
                "target_iqn": "iqn.1992-08.com.netapp:sn.test",
            },
        },
    }


def _netapp_validation(blockers: list[str]) -> dict[str, object]:
    return {
        "status": "blocked" if blockers else "ready",
        "blockers": blockers,
        "protocol_readiness": {"ready": not blockers},
        "current_state": {},
    }


def _step_by_label(payload: dict[str, object], label: str) -> dict[str, object]:
    for step in payload["steps"]:
        if step["label"] == label:
            return step
    raise AssertionError(f"missing remediation step {label!r}")
