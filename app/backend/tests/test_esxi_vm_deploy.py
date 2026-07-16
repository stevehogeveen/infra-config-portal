from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from dataclasses import replace
from pathlib import Path

from app.core.config import settings
from app.providers import action_policy
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


def test_esxi_vm_deploy_apply_refuses_same_target_when_import_in_flight(monkeypatch, tmp_path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    ovf = tmp_path / "template.ovf"
    ovf.write_text("<Envelope />", encoding="utf-8")
    _patch_settings(monkeypatch)
    monkeypatch.setenv("VM_DEPLOY_OVF_PATH", str(ovf))
    monkeypatch.setenv("VM_DEPLOY_APPLY", "true")
    monkeypatch.setenv("VM_DEPLOY_CONFIRM", esxi_vm_deploy.VM_DEPLOY_CONFIRM_PHRASE)
    monkeypatch.setenv("VM_DEPLOY_ALLOW_CREATE", "true")
    monkeypatch.setattr(action_policy, "settings", esxi_vm_deploy.settings)
    monkeypatch.setattr(esxi_vm_deploy, "_govc_binary", lambda: "/usr/bin/govc")
    govc_calls: list[list[str]] = []

    def fake_govc(args, *, env, timeout):
        govc_calls.append(args)
        if args[:2] == ["datastore.info", "-json"]:
            return _govc_datastore_present(args, env=env, timeout=timeout)
        raise AssertionError(f"unexpected govc call while lock is held: {args}")

    monkeypatch.setattr(esxi_vm_deploy, "_run_govc", fake_govc)
    plan = {
        "vm_name": "netapp-nfs-ovf-preview-vm",
        "datastore": "netapp_nfs_ds01",
        "ovf_path": str(ovf),
    }
    lock_path = esxi_vm_deploy._inflight_lock_path(plan)
    lock_path.write_text("in flight", encoding="utf-8")

    payload = esxi_vm_deploy.apply_esxi_vm_deploy(write_report=False)

    assert payload["status"] == "blocked"
    assert payload["apply_enabled"] is False
    assert payload["apply"]["in_flight_refused"] is True
    assert any("already in flight" in blocker for blocker in payload["blockers"])
    assert payload["apply"]["govc_import_spec_attempted"] is False
    assert govc_calls == [["datastore.info", "-json", "netapp_nfs_ds01"]]


def test_esxi_vm_deploy_apply_clears_stale_inflight_lock_with_warning(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    ovf = tmp_path / "template.ovf"
    ovf.write_text("<Envelope />", encoding="utf-8")
    _patch_settings(monkeypatch)
    monkeypatch.setenv("VM_DEPLOY_OVF_PATH", str(ovf))
    monkeypatch.setenv("VM_DEPLOY_APPLY", "true")
    monkeypatch.setenv("VM_DEPLOY_CONFIRM", esxi_vm_deploy.VM_DEPLOY_CONFIRM_PHRASE)
    monkeypatch.setenv("VM_DEPLOY_ALLOW_CREATE", "true")
    monkeypatch.setattr(action_policy, "settings", esxi_vm_deploy.settings)
    monkeypatch.setattr(esxi_vm_deploy, "_govc_binary", lambda: "/usr/bin/govc")

    def fake_govc(args, *, env, timeout):
        if args[:2] == ["datastore.info", "-json"]:
            return _govc_datastore_present(args, env=env, timeout=timeout)
        if args[:1] == ["import.spec"]:
            return {"return_code": 0, "stdout": json.dumps({"NetworkMapping": [{"Name": "VM Network"}]}), "stderr": ""}
        if args[:1] == ["import.ovf"]:
            return {"return_code": 0, "stdout": "", "stderr": ""}
        if args[:2] == ["vm.info", "-json"]:
            return _govc_datastore_and_vm_present(args, env=env, timeout=timeout)
        raise AssertionError(f"unexpected govc call: {args}")

    monkeypatch.setattr(esxi_vm_deploy, "_run_govc", fake_govc)
    plan = {
        "vm_name": "netapp-nfs-ovf-preview-vm",
        "datastore": "netapp_nfs_ds01",
        "ovf_path": str(ovf),
    }
    lock_path = esxi_vm_deploy._inflight_lock_path(plan)
    lock_path.write_text(
        json.dumps({"started_at": (datetime.now(UTC) - timedelta(minutes=45)).isoformat(), "pid": -1}),
        encoding="utf-8",
    )

    payload = esxi_vm_deploy.apply_esxi_vm_deploy(write_report=False)

    assert payload["status"] == "completed"
    assert payload["apply"]["govc_import_ovf_attempted"] is True
    assert any("stale VM deploy in-flight lock" in warning for warning in payload["warnings"])
    assert not lock_path.exists()


def test_esxi_vm_deploy_apply_keeps_stale_lock_when_owner_process_is_alive(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    ovf = tmp_path / "template.ovf"
    ovf.write_text("<Envelope />", encoding="utf-8")
    _patch_settings(monkeypatch)
    monkeypatch.setenv("VM_DEPLOY_OVF_PATH", str(ovf))
    monkeypatch.setenv("VM_DEPLOY_APPLY", "true")
    monkeypatch.setenv("VM_DEPLOY_CONFIRM", esxi_vm_deploy.VM_DEPLOY_CONFIRM_PHRASE)
    monkeypatch.setenv("VM_DEPLOY_ALLOW_CREATE", "true")
    monkeypatch.setattr(action_policy, "settings", esxi_vm_deploy.settings)
    monkeypatch.setattr(esxi_vm_deploy, "_govc_binary", lambda: "/usr/bin/govc")

    def fake_govc(args, *, env, timeout):
        if args[:2] == ["datastore.info", "-json"]:
            return _govc_datastore_present(args, env=env, timeout=timeout)
        raise AssertionError(f"unexpected govc call while stale live lock is held: {args}")

    monkeypatch.setattr(esxi_vm_deploy, "_run_govc", fake_govc)
    plan = {
        "vm_name": "netapp-nfs-ovf-preview-vm",
        "datastore": "netapp_nfs_ds01",
        "ovf_path": str(ovf),
    }
    owner = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        lock_path = esxi_vm_deploy._inflight_lock_path(plan)
        lock_path.write_text(
            json.dumps({"started_at": (datetime.now(UTC) - timedelta(minutes=45)).isoformat(), "pid": owner.pid}),
            encoding="utf-8",
        )

        payload = esxi_vm_deploy.apply_esxi_vm_deploy(write_report=False)

        assert payload["status"] == "blocked"
        assert payload["apply"]["in_flight_refused"] is True
        assert any("could not be proven stopped" in warning for warning in payload["warnings"])
        assert lock_path.exists()
    finally:
        owner.terminate()
        owner.wait(timeout=10)


def test_esxi_vm_deploy_gate_accepts_common_true_like_env_values(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    monkeypatch.setattr(esxi_vm_deploy, "current_lab_action_policy", lambda _mode=None: _AllowPolicy())
    monkeypatch.setenv("VM_DEPLOY_APPLY", " YES ")
    monkeypatch.setenv("VM_DEPLOY_CONFIRM", esxi_vm_deploy.VM_DEPLOY_CONFIRM_PHRASE)
    monkeypatch.setenv("VM_DEPLOY_ALLOW_CREATE", "ON")
    monkeypatch.setenv("VM_DEPLOY_POWER_ON", "1")
    monkeypatch.setenv("VM_DEPLOY_POWER_ON_CONFIRM", esxi_vm_deploy.VM_DEPLOY_POWER_ON_CONFIRM_PHRASE)
    plan = {
        "vm_name": "netapp-nfs-ovf-preview-vm",
        "ovf_path": "template.ovf",
        "ovf_present": True,
        "datastore": "netapp_nfs_ds01",
        "power_on": esxi_vm_deploy._env_flag("VM_DEPLOY_POWER_ON"),
        "target_is_netapp_nfs": False,
    }
    target = {"govc_available": True, "missing_fields": []}
    datastore = {"checked": True, "exists": True}

    result = esxi_vm_deploy._apply_gates(plan, target, datastore)

    assert result["blockers"] == []
    assert result["flag_state"]["vm_deploy_apply"] is True
    assert result["flag_state"]["vm_deploy_allow_create"] is True
    assert result["flag_state"]["vm_deploy_power_on"] is True


def test_esxi_vm_deploy_gate_keeps_scalar_policy_and_missing_field_blockers_whole(monkeypatch) -> None:
    _patch_settings(monkeypatch)
    monkeypatch.setattr(esxi_vm_deploy, "current_lab_action_policy", lambda _mode=None: _ScalarBlockerPolicy())
    monkeypatch.setenv("VM_DEPLOY_APPLY", "true")
    monkeypatch.setenv("VM_DEPLOY_CONFIRM", esxi_vm_deploy.VM_DEPLOY_CONFIRM_PHRASE)
    monkeypatch.setenv("VM_DEPLOY_ALLOW_CREATE", "true")
    plan = {
        "vm_name": "edge-vm",
        "ovf_path": "template.ovf",
        "ovf_present": True,
        "datastore": "netapp_nfs_ds01",
        "power_on": False,
        "target_is_netapp_nfs": False,
    }
    target = {"govc_available": True, "missing_fields": " GOVC_URL "}
    datastore = {"checked": True, "exists": True}

    result = esxi_vm_deploy._apply_gates(plan, target, datastore)

    assert "policy blocker" in result["blockers"]
    assert "Direct ESXi govc target fields are missing: GOVC_URL." in result["blockers"]
    assert not any(blocker == "p" for blocker in result["blockers"])
    assert not any("G, O, V, C" in blocker for blocker in result["blockers"])


def test_esxi_vm_deploy_preview_dedupes_repeated_missing_fields() -> None:
    plan = {
        "ovf_present": True,
        "datastore": "netapp_nfs_ds01",
        "target_is_netapp_nfs": False,
    }
    target = {"govc_available": True, "missing_fields": ["GOVC_URL", "GOVC_URL", "GOVC_USERNAME"]}
    datastore = {"checked": True, "exists": True}

    blockers = esxi_vm_deploy._preview_blockers(plan, target, datastore)

    assert "Direct ESXi govc target fields are missing: GOVC_URL, GOVC_USERNAME." in blockers


def test_esxi_vm_deploy_unique_blockers_skip_blanks_preserving_order() -> None:
    assert esxi_vm_deploy._unique(
        ["", "datastore missing", None, "flag missing", "datastore missing", "flag missing"]
    ) == ["datastore missing", "flag missing"]


def test_esxi_vm_deploy_preview_writes_json_atomically(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    ovf = tmp_path / "template.ovf"
    ovf.write_text("<Envelope />", encoding="utf-8")
    _patch_settings(monkeypatch)
    monkeypatch.setenv("VM_DEPLOY_OVF_PATH", str(ovf))
    monkeypatch.setattr(esxi_vm_deploy, "_govc_binary", lambda: "/usr/bin/govc")
    monkeypatch.setattr(esxi_vm_deploy, "_run_govc", _govc_datastore_present)

    payload = esxi_vm_deploy.build_esxi_vm_deploy_preview(write_report=True)

    saved = json.loads(esxi_vm_deploy.PREVIEW_JSON.read_text(encoding="utf-8"))
    datastore = json.loads(esxi_vm_deploy.DATASTORE_INFO_JSON.read_text(encoding="utf-8"))
    assert saved["action"] == payload["action"]
    assert datastore["exists"] is True
    assert esxi_vm_deploy.PREVIEW_REPORT.read_text(encoding="utf-8").strip()
    assert not list(esxi_vm_deploy.CODEX_RUN_DIR.glob("*.tmp"))


def test_esxi_vm_deploy_validation_writes_vm_info_atomically(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    ovf = tmp_path / "template.ovf"
    ovf.write_text("<Envelope />", encoding="utf-8")
    _patch_settings(monkeypatch)
    monkeypatch.setenv("VM_DEPLOY_OVF_PATH", str(ovf))
    monkeypatch.setattr(esxi_vm_deploy, "_govc_binary", lambda: "/usr/bin/govc")
    monkeypatch.setattr(esxi_vm_deploy, "_run_govc", _govc_datastore_and_vm_present)

    payload = esxi_vm_deploy.validate_esxi_vm_deploy(write_report=True)

    saved = json.loads(esxi_vm_deploy.VALIDATION_JSON.read_text(encoding="utf-8"))
    vm_info = json.loads(esxi_vm_deploy.VM_INFO_JSON.read_text(encoding="utf-8"))
    assert saved["action"] == payload["action"]
    assert vm_info["exists"] is True
    assert payload["status"] == "ready"
    assert esxi_vm_deploy.VALIDATION_REPORT.read_text(encoding="utf-8").strip()
    assert not list(esxi_vm_deploy.CODEX_RUN_DIR.glob("*.tmp"))


def test_esxi_vm_deploy_apply_cleans_temp_import_options(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    ovf = tmp_path / "template.ovf"
    ovf.write_text("<Envelope />", encoding="utf-8")
    _patch_settings(monkeypatch)
    monkeypatch.setenv("VM_DEPLOY_OVF_PATH", str(ovf))
    monkeypatch.setenv("VM_DEPLOY_APPLY", "true")
    monkeypatch.setenv("VM_DEPLOY_CONFIRM", esxi_vm_deploy.VM_DEPLOY_CONFIRM_PHRASE)
    monkeypatch.setenv("VM_DEPLOY_ALLOW_CREATE", "true")
    monkeypatch.setattr(action_policy, "settings", esxi_vm_deploy.settings)
    monkeypatch.setattr(esxi_vm_deploy, "_govc_binary", lambda: "/usr/bin/govc")
    observed_options_paths: list[Path] = []

    def fake_govc(args, *, env, timeout):
        if args[:2] == ["datastore.info", "-json"]:
            return _govc_datastore_present(args, env=env, timeout=timeout)
        if args[:1] == ["import.spec"]:
            return {
                "return_code": 0,
                "stdout": json.dumps({"NetworkMapping": [{"Name": "VM Network"}]}),
                "stderr": "",
            }
        if args[:1] == ["import.ovf"]:
            options_path = Path(args[args.index("-options") + 1])
            observed_options_paths.append(options_path)
            assert options_path.parent == esxi_vm_deploy.CODEX_RUN_DIR
            assert json.loads(options_path.read_text(encoding="utf-8"))["Name"] == "netapp-nfs-ovf-preview-vm"
            return {"return_code": 0, "stdout": "", "stderr": ""}
        if args[:2] == ["vm.info", "-json"]:
            return _govc_datastore_and_vm_present(args, env=env, timeout=timeout)
        raise AssertionError(f"unexpected govc call: {args}")

    monkeypatch.setattr(esxi_vm_deploy, "_run_govc", fake_govc)

    payload = esxi_vm_deploy.apply_esxi_vm_deploy(write_report=True)

    assert payload["status"] == "completed"
    assert payload["apply"]["govc_import_ovf_attempted"] is True
    assert "VM import/create" not in payload["not_attempted"]
    assert "VM power on" in payload["not_attempted"]
    assert observed_options_paths
    assert all(not path.exists() for path in observed_options_paths)
    assert not esxi_vm_deploy._inflight_lock_path(payload["deployment_plan"]).exists()
    assert not list(esxi_vm_deploy.CODEX_RUN_DIR.glob("esxi-vm-deploy-options-*.json"))
    assert not list(esxi_vm_deploy.CODEX_RUN_DIR.glob("*.tmp"))


def test_vm_deploy_paths_use_posix_for_repo_relative_labels(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(esxi_vm_deploy, "REPO_ROOT", tmp_path)
    repo_ovf = tmp_path / "artifacts" / "Media" / "templates" / "vm.ovf"
    outside_ovf = tmp_path.parent / "external-template.ovf"

    assert esxi_vm_deploy._safe_path(repo_ovf) == "artifacts/Media/templates/vm.ovf"
    assert esxi_vm_deploy._rel(tmp_path / "artifacts" / "codex-runs" / "report.md") == "artifacts/codex-runs/report.md"
    assert esxi_vm_deploy._safe_path(outside_ovf) == str(outside_ovf)


def test_vm_deploy_import_options_self_heal_bad_json_shapes() -> None:
    plan = {
        "vm_name": "edge-vm",
        "disk_provisioning": "thin",
        "power_on": False,
        "network": "VM Network",
    }

    for stdout in (None, "", "not-json", '["not", "object"]', '"string"'):
        options = esxi_vm_deploy._import_options(stdout, plan)
        assert options["Name"] == "edge-vm"
        assert options["DiskProvisioning"] == "thin"
        assert options["PowerOn"] is False
        assert options["NetworkMapping"] == [{"Name": "VM Network", "Network": "VM Network"}]


def test_vm_deploy_plan_self_heals_explicit_ovf_exists_error(monkeypatch, tmp_path: Path) -> None:
    _patch_settings(monkeypatch)
    ovf = tmp_path / "template.ovf"
    monkeypatch.setenv("VM_DEPLOY_OVF_PATH", str(ovf))
    original_exists = Path.exists

    def flaky_exists(path: Path) -> bool:
        if path == ovf:
            raise OSError("locked")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    plan = esxi_vm_deploy._deployment_plan()

    assert plan["ovf_path"] == str(ovf)
    assert plan["ovf_present"] is False


def test_vm_deploy_apply_treats_ovf_probe_error_as_missing(monkeypatch, tmp_path: Path) -> None:
    ovf = tmp_path / "template.ovf"
    ovf.write_text("<Envelope />", encoding="utf-8")
    monkeypatch.setattr(esxi_vm_deploy, "_resolve_ovf_path", lambda: ovf)
    original_exists = Path.exists

    def flaky_exists(path: Path) -> bool:
        if path == ovf:
            raise OSError("template path unavailable")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    result = esxi_vm_deploy._run_guarded_import({"power_on": False}, {})

    assert result["status"] == "failed"
    assert result["apply"]["govc_import_spec_attempted"] is False
    assert any("OVF template is not available" in blocker for blocker in result["blockers"])


def test_vm_deploy_ovf_discovery_skips_unreadable_media_roots(monkeypatch, tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    settings_override = replace(settings, media_inventory_dirs=(str(media_root),))
    monkeypatch.delenv("VM_DEPLOY_OVF_PATH", raising=False)
    monkeypatch.setattr(esxi_vm_deploy, "settings", settings_override)
    monkeypatch.setattr(esxi_vm_deploy, "DEFAULT_MEDIA_ROOT", tmp_path / "artifacts" / "Media")
    original_is_dir = Path.is_dir

    def flaky_is_dir(path: Path) -> bool:
        if path == media_root:
            raise OSError("locked")
        return original_is_dir(path)

    monkeypatch.setattr(Path, "is_dir", flaky_is_dir)

    assert esxi_vm_deploy._resolve_ovf_path() is None


def test_vm_deploy_ovf_discovery_skips_recursive_scan_errors(monkeypatch, tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    settings_override = replace(settings, media_inventory_dirs=(str(media_root),))
    monkeypatch.delenv("VM_DEPLOY_OVF_PATH", raising=False)
    monkeypatch.setattr(esxi_vm_deploy, "settings", settings_override)
    monkeypatch.setattr(esxi_vm_deploy, "DEFAULT_MEDIA_ROOT", tmp_path / "artifacts" / "Media")
    original_rglob = Path.rglob

    def flaky_rglob(path: Path, pattern: str):  # noqa: ANN202
        if path == media_root:
            raise OSError("recursive scan failed")
        return original_rglob(path, pattern)

    monkeypatch.setattr(Path, "rglob", flaky_rglob)

    assert esxi_vm_deploy._resolve_ovf_path() is None


def test_vm_deploy_govc_binary_skips_unavailable_fallback_candidate(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(esxi_vm_deploy, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(esxi_vm_deploy.sys, "executable", str(tmp_path / "venv" / "Scripts" / "python.exe"))
    candidate = tmp_path / "venv" / "Scripts" / "govc"
    original_is_file = Path.is_file

    def flaky_is_file(path: Path) -> bool:
        if path == candidate:
            raise OSError("candidate path unavailable")
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", flaky_is_file)
    monkeypatch.setattr("shutil.which", lambda _name: None)

    assert esxi_vm_deploy._govc_binary() is None


def test_vm_deploy_govc_summary_parsers_ignore_bad_shapes() -> None:
    assert esxi_vm_deploy._json_stdout_object("not-json") == {}
    assert esxi_vm_deploy._json_stdout_object('["not", "object"]') == {}
    assert esxi_vm_deploy._datastore_summary('{"Datastores": []}') is None
    assert esxi_vm_deploy._datastore_summary('{"Datastores": [{"Summary": "bad"}]}') is None
    assert esxi_vm_deploy._vm_summary('{"VirtualMachines": []}') is None
    assert esxi_vm_deploy._vm_summary('{"VirtualMachines": ["bad"]}') is None


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
    monkeypatch.setattr(action_policy, "settings", settings_override)
    monkeypatch.setattr(action_policy, "read_lab_safety_overrides", lambda: {})


def _govc_datastore_missing(args, *, env, timeout):
    if args[:2] == ["datastore.info", "-json"]:
        return {"return_code": 1, "stdout": "", "stderr": "datastore not found"}
    raise AssertionError(f"unexpected govc call: {args}")


def _govc_datastore_present(args, *, env, timeout):
    if args[:2] == ["datastore.info", "-json"]:
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
                                "Capacity": 1024,
                                "FreeSpace": 512,
                            }
                        }
                    ]
                }
            ),
            "stderr": "",
        }
    raise AssertionError(f"unexpected govc call: {args}")


def _govc_datastore_and_vm_present(args, *, env, timeout):
    if args[:2] == ["datastore.info", "-json"]:
        return _govc_datastore_present(args, env=env, timeout=timeout)
    if args[:2] == ["vm.info", "-json"]:
        return {
            "return_code": 0,
            "stdout": json.dumps(
                {
                    "VirtualMachines": [
                        {
                            "InventoryPath": "/ha-datacenter/vm/netapp-nfs-ovf-preview-vm",
                            "Summary": {
                                "Config": {
                                    "Name": "netapp-nfs-ovf-preview-vm",
                                    "GuestFullName": "Other Linux",
                                },
                                "Runtime": {"PowerState": "poweredOff"},
                            },
                        }
                    ]
                }
            ),
            "stderr": "",
        }
    raise AssertionError(f"unexpected govc call: {args}")


def _redirect_reports(monkeypatch, tmp_path: Path) -> None:
    codex_runs = tmp_path / "artifacts" / "codex-runs"
    codex_runs.mkdir(parents=True)
    monkeypatch.setattr(esxi_vm_deploy, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(esxi_vm_deploy, "CODEX_RUN_DIR", codex_runs)
    monkeypatch.setattr(esxi_vm_deploy, "DEFAULT_MEDIA_ROOT", tmp_path / "artifacts" / "Media")
    monkeypatch.setattr(esxi_vm_deploy, "PREVIEW_REPORT", codex_runs / "esxi-vm-deploy-preview-report.md")
    monkeypatch.setattr(esxi_vm_deploy, "PREVIEW_JSON", codex_runs / "esxi-vm-deploy-preview-redacted.json")
    monkeypatch.setattr(esxi_vm_deploy, "APPLY_REPORT", codex_runs / "esxi-vm-deploy-apply-report.md")
    monkeypatch.setattr(esxi_vm_deploy, "APPLY_JSON", codex_runs / "esxi-vm-deploy-apply-redacted.json")
    monkeypatch.setattr(esxi_vm_deploy, "VALIDATION_REPORT", codex_runs / "esxi-vm-deploy-validation-report.md")
    monkeypatch.setattr(esxi_vm_deploy, "VALIDATION_JSON", codex_runs / "esxi-vm-deploy-validation-redacted.json")
    monkeypatch.setattr(esxi_vm_deploy, "IMPORT_OPTIONS_JSON", codex_runs / "esxi-vm-deploy-import-options-redacted.json")
    monkeypatch.setattr(esxi_vm_deploy, "VM_INFO_JSON", codex_runs / "esxi-vm-deploy-vm-info-redacted.json")
    monkeypatch.setattr(esxi_vm_deploy, "DATASTORE_INFO_JSON", codex_runs / "esxi-vm-deploy-datastore-info-redacted.json")


class _AllowPolicy:
    def action_blockers(self, _action_id, _category):
        return []


class _ScalarBlockerPolicy:
    def action_blockers(self, _action_id, _category):
        return " policy blocker "
