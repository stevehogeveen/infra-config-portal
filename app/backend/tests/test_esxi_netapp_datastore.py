from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

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


def test_apply_gate_accepts_common_true_like_env_values(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    monkeypatch.setenv("ESXI_NETAPP_DATASTORE_APPLY", " YES ")
    monkeypatch.setenv("ESXI_NETAPP_DATASTORE_CONFIRM", "MOUNT NETAPP NFS DATASTORE")
    plan = {
        "datastore_name": "netapp_nfs_ds01",
        "remote_host": "192.168.1.230",
        "remote_path": "/esxi_datastore_01",
        "nfs_version": "nfs",
    }
    target = {"can_query": True}
    current = {"exists": False, "accessible": False}

    result = esxi_netapp_datastore._apply_gates(plan, target, current)

    assert result["blockers"] == []
    assert result["flag_state"]["datastore_apply"] is True


def test_apply_gate_dedupes_blockers_preserving_order(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    monkeypatch.setenv("ESXI_NETAPP_DATASTORE_APPLY", "false")
    monkeypatch.delenv("ESXI_NETAPP_DATASTORE_CONFIRM", raising=False)
    monkeypatch.setattr(
        esxi_netapp_datastore,
        "current_lab_action_policy",
        lambda mode: _PolicyWithDuplicateBlockers(),
    )
    plan = {
        "datastore_name": "",
        "remote_host": "",
        "remote_path": "",
        "nfs_version": "nfs",
    }
    target = {
        "can_query": False,
        "missing_fields": ["govc", "govc"],
    }
    current = {"exists": False, "accessible": False}

    result = esxi_netapp_datastore._apply_gates(plan, target, current)

    assert result["blockers"] == [
        "policy blocker",
        "NETAPP_NFS_DATASTORE_NAME or ESXI_NETAPP_DATASTORE_NAME is required.",
        "NETAPP_NFS_LIFS or ESXI_NETAPP_DATASTORE_REMOTE_HOST is required.",
        "NETAPP_NFS_MOUNT_PATH or ESXI_NETAPP_DATASTORE_REMOTE_PATH is required.",
        "ESXi govc target is not ready: govc.",
        "ESXI_NETAPP_DATASTORE_APPLY=true is required.",
        'ESXI_NETAPP_DATASTORE_CONFIRM="MOUNT NETAPP NFS DATASTORE" is required.',
    ]


def test_apply_gate_keeps_scalar_policy_and_missing_field_blockers_whole(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    monkeypatch.setenv("ESXI_NETAPP_DATASTORE_APPLY", "false")
    monkeypatch.delenv("ESXI_NETAPP_DATASTORE_CONFIRM", raising=False)
    monkeypatch.setattr(
        esxi_netapp_datastore,
        "current_lab_action_policy",
        lambda mode: _PolicyWithScalarBlockers(),
    )
    plan = {
        "datastore_name": "netapp_nfs_ds01",
        "remote_host": "192.168.1.230",
        "remote_path": "/esxi_datastore_01",
        "nfs_version": "nfs",
    }
    target = {
        "can_query": False,
        "missing_fields": " GOVC_URL ",
    }
    current = {"exists": False, "accessible": False}

    result = esxi_netapp_datastore._apply_gates(plan, target, current)

    assert "policy blocker" in result["blockers"]
    assert "ESXi govc target is not ready: GOVC_URL." in result["blockers"]
    assert not any(blocker == "p" for blocker in result["blockers"])
    assert not any("G, O, V, C" in blocker for blocker in result["blockers"])


def test_preview_uses_esxi_ssh_fallback_when_govc_is_missing(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    monkeypatch.setattr(esxi_netapp_datastore, "_govc_binary", lambda: None)
    monkeypatch.setattr(esxi_netapp_datastore, "_tcp_reachable", lambda host, port: True)
    monkeypatch.setattr(esxi_netapp_datastore, "_run_esxi_ssh", _ssh_datastore_calls)

    payload = esxi_netapp_datastore.build_esxi_netapp_datastore_preview(write_report=False)

    assert payload["status"] == "preview_ready"
    assert payload["target_state"]["access_method"] == "ssh"
    assert payload["current_state"]["summary"]["accessible"] is True
    assert any("esxcli storage nfs add" in command for command in payload["command_preview"])


def test_apply_uses_esxi_ssh_fallback_when_govc_is_missing(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    monkeypatch.setenv("ESXI_NETAPP_DATASTORE_APPLY", "true")
    monkeypatch.setenv("ESXI_NETAPP_DATASTORE_CONFIRM", "MOUNT NETAPP NFS DATASTORE")
    monkeypatch.setattr(esxi_netapp_datastore, "_govc_binary", lambda: None)
    monkeypatch.setattr(esxi_netapp_datastore, "_tcp_reachable", lambda host, port: True)
    calls = []

    def fake_ssh(command, *, timeout=60):
        calls.append(command)
        if "storage nfs add" in command:
            return {"return_code": 0, "stdout": "", "stderr": ""}
        if "storage nfs list" in command and any("storage nfs add" in call for call in calls):
            return _ssh_nfs_list(accessible=True)
        if "storage filesystem list" in command and any("storage nfs add" in call for call in calls):
            return _ssh_filesystem_list()
        return {"return_code": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(esxi_netapp_datastore, "_run_esxi_ssh", fake_ssh)

    payload = esxi_netapp_datastore.apply_esxi_netapp_datastore(write_report=False)

    assert payload["status"] == "mounted"
    assert any("esxcli storage nfs add" in call for call in calls)
    assert payload["apply"]["apply_mechanism"] == "ssh-esxcli"


def test_report_paths_use_posix_separators(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(esxi_netapp_datastore, "REPO_ROOT", tmp_path)

    assert esxi_netapp_datastore._rel(tmp_path / "artifacts" / "codex-runs" / "report.md") == "artifacts/codex-runs/report.md"


def test_govc_stdout_json_object_parser_ignores_bad_shapes() -> None:
    assert esxi_netapp_datastore._json_stdout_object(None) == {}
    assert esxi_netapp_datastore._json_stdout_object("") == {}
    assert esxi_netapp_datastore._json_stdout_object("govc warning\n{not-json") == {}
    assert esxi_netapp_datastore._json_stdout_object('["not", "object"]') == {}
    assert esxi_netapp_datastore._json_stdout_object('{"hostSystems": []}') == {"hostSystems": []}


def test_discover_host_target_ignores_unexpected_govc_shapes(monkeypatch) -> None:
    monkeypatch.setattr(esxi_netapp_datastore, "_govc_env", lambda: {})
    outputs = iter(
        [
            "not-json",
            '["host"]',
            '{"hostSystems": ["not-object"]}',
            '{"HostSystems": [{"Name": "HomeEsxi."}]}',
        ]
    )
    monkeypatch.setattr(
        esxi_netapp_datastore,
        "_run_govc",
        lambda *_args, **_kwargs: {"return_code": 0, "stdout": next(outputs), "stderr": ""},
    )

    assert esxi_netapp_datastore._discover_host_target() is None
    assert esxi_netapp_datastore._discover_host_target() is None
    assert esxi_netapp_datastore._discover_host_target() is None
    assert esxi_netapp_datastore._discover_host_target() == "HomeEsxi."


def test_datastore_summary_ignores_unexpected_govc_shapes() -> None:
    assert esxi_netapp_datastore._datastore_summary(None) is None
    assert esxi_netapp_datastore._datastore_summary("not-json") is None
    assert esxi_netapp_datastore._datastore_summary('{"Datastores": []}') is None
    assert esxi_netapp_datastore._datastore_summary('{"Datastores": [{"Summary": "bad"}]}') is None

    summary = esxi_netapp_datastore._datastore_summary(
        json.dumps(
            {
                "datastores": [
                    {
                        "summary": {
                            "name": "netapp_nfs_ds01",
                            "type": "NFS",
                            "accessible": True,
                        },
                        "host": [{"mountInfo": {"accessMode": "readWrite"}}],
                    }
                ]
            }
        )
    )

    assert summary == {
        "name": "netapp_nfs_ds01",
        "type": "NFS",
        "accessible": True,
        "capacity": None,
        "free_space": None,
        "access_mode": "readWrite",
    }


def test_preview_report_writes_json_atomically(monkeypatch, tmp_path: Path) -> None:
    paths = _redirect_reports(monkeypatch, tmp_path)
    _patch_settings(monkeypatch)
    monkeypatch.setattr(esxi_netapp_datastore, "_govc_binary", lambda: "/usr/bin/govc")
    monkeypatch.setattr(esxi_netapp_datastore, "_run_govc", _govc_preview_calls)

    payload = esxi_netapp_datastore.build_esxi_netapp_datastore_preview()

    stored = json.loads(paths["preview_json"].read_text(encoding="utf-8"))
    assert stored["action"] == "esxi-netapp-datastore-preview"
    assert stored["status"] == payload["status"]
    assert paths["preview_report"].read_text(encoding="utf-8").startswith("# ESXi NetApp NFS Datastore Report")
    assert not list(tmp_path.rglob("*.tmp"))


def test_apply_report_writes_json_atomically(monkeypatch, tmp_path: Path) -> None:
    paths = _redirect_reports(monkeypatch, tmp_path)
    _patch_settings(monkeypatch)
    monkeypatch.setenv("ESXI_NETAPP_DATASTORE_APPLY", "true")
    monkeypatch.setenv("ESXI_NETAPP_DATASTORE_CONFIRM", "MOUNT NETAPP NFS DATASTORE")
    monkeypatch.setattr(esxi_netapp_datastore, "_govc_binary", lambda: "/usr/bin/govc")
    monkeypatch.setattr(esxi_netapp_datastore, "_run_govc", _govc_apply_calls)

    payload = esxi_netapp_datastore.apply_esxi_netapp_datastore()

    stored = json.loads(paths["apply_json"].read_text(encoding="utf-8"))
    assert stored["action"] == "esxi-netapp-datastore-apply"
    assert stored["status"] == payload["status"]
    assert paths["apply_report"].read_text(encoding="utf-8").strip()
    assert not list(tmp_path.rglob("*.tmp"))


def test_validation_report_writes_json_atomically(monkeypatch, tmp_path: Path) -> None:
    paths = _redirect_reports(monkeypatch, tmp_path)
    _patch_settings(monkeypatch)
    monkeypatch.setattr(esxi_netapp_datastore, "_govc_binary", lambda: "/usr/bin/govc")
    monkeypatch.setattr(esxi_netapp_datastore, "_run_govc", _govc_preview_calls)

    payload = esxi_netapp_datastore.validate_esxi_netapp_datastore()

    stored = json.loads(paths["validation_json"].read_text(encoding="utf-8"))
    assert stored["action"] == "esxi-netapp-datastore-validation"
    assert stored["status"] == payload["status"]
    assert paths["validation_report"].read_text(encoding="utf-8").strip()
    assert not list(tmp_path.rglob("*.tmp"))


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


class _PolicyWithDuplicateBlockers:
    def action_blockers(self, action_id, category):
        return ["policy blocker", "policy blocker"]


class _PolicyWithScalarBlockers:
    def action_blockers(self, action_id, category):
        return " policy blocker "


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


def _ssh_datastore_calls(command, *, timeout=60):
    if "storage nfs list" in command:
        return _ssh_nfs_list(accessible=True)
    if "storage filesystem list" in command:
        return _ssh_filesystem_list()
    raise AssertionError(f"unexpected ssh call: {command}")


def _ssh_nfs_list(*, accessible: bool) -> dict[str, str | int]:
    value = "true" if accessible else "false"
    return {
        "return_code": 0,
        "stdout": (
            "Volume Name      Host           Share               Vmknic  Accessible  Mounted  Connections  Read-Only   isPE  Hardware Acceleration\n"
            "---------------  -------------  ------------------  ------  ----------  -------  -----------  ---------  -----  ---------------------\n"
            f"netapp_nfs_ds01  192.168.1.230  /esxi_datastore_01  vmk0          {value}     true            1      false  false  Not Supported\n"
        ),
        "stderr": "",
    }


def _ssh_filesystem_list() -> dict[str, str | int]:
    return {
        "return_code": 0,
        "stdout": (
            "Mount Point                      Volume Name      UUID                 Mounted  Type            Size          Free\n"
            "/vmfs/volumes/6924a5f4-e017ec92  netapp_nfs_ds01  6924a5f4-e017ec92 true     NFS  1044536049664  1044535697408\n"
        ),
        "stderr": "",
    }


def _redirect_reports(monkeypatch, tmp_path: Path) -> dict[str, Path]:
    codex_run_dir = tmp_path / "artifacts" / "codex-runs"
    paths = {
        "preview_report": codex_run_dir / "preview-report.md",
        "preview_json": codex_run_dir / "preview.json",
        "apply_report": codex_run_dir / "apply-report.md",
        "apply_json": codex_run_dir / "apply.json",
        "validation_report": codex_run_dir / "validation-report.md",
        "validation_json": codex_run_dir / "validation.json",
    }
    monkeypatch.setattr(esxi_netapp_datastore, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(esxi_netapp_datastore, "CODEX_RUN_DIR", codex_run_dir)
    monkeypatch.setattr(esxi_netapp_datastore, "PREVIEW_REPORT", paths["preview_report"])
    monkeypatch.setattr(esxi_netapp_datastore, "PREVIEW_JSON", paths["preview_json"])
    monkeypatch.setattr(esxi_netapp_datastore, "APPLY_REPORT", paths["apply_report"])
    monkeypatch.setattr(esxi_netapp_datastore, "APPLY_JSON", paths["apply_json"])
    monkeypatch.setattr(esxi_netapp_datastore, "VALIDATION_REPORT", paths["validation_report"])
    monkeypatch.setattr(esxi_netapp_datastore, "VALIDATION_JSON", paths["validation_json"])
    return paths


def _govc_apply_calls(args, *, env, timeout):
    if args == ["about"]:
        return {"return_code": 0, "stdout": "", "stderr": ""}
    if args == ["host.info", "-json"]:
        return _host_info()
    if args[:2] == ["datastore.info", "-json"]:
        return _datastore_info()
    if args and args[0] == "datastore.create":
        return {"return_code": 0, "stdout": "", "stderr": ""}
    raise AssertionError(f"unexpected govc call: {args}")
