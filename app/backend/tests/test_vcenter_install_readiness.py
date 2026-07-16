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
    saved = json.loads((tmp_path / "artifacts/codex-runs/vcenter-install-readiness-redacted.json").read_text(encoding="utf-8"))
    assert saved["action"] == result["action"]
    assert (tmp_path / "artifacts/codex-runs/vcenter-install-readiness-report.md").read_text(encoding="utf-8").strip()
    assert not list((tmp_path / "artifacts/codex-runs").glob("*.tmp"))


def test_vcenter_paths_use_posix_for_repo_relative_labels(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(vcenter_netapp_readiness, "REPO_ROOT", tmp_path)
    repo_iso = tmp_path / "artifacts" / "Media" / "vcsa.iso"
    outside_iso = tmp_path.parent / "vcsa.iso"

    assert vcenter_netapp_readiness._rel(tmp_path / "artifacts" / "codex-runs" / "report.md") == "artifacts/codex-runs/report.md"
    assert vcenter_netapp_readiness._safe_media_path(repo_iso) == "artifacts/Media/vcsa.iso"
    assert vcenter_netapp_readiness._safe_media_path(outside_iso) == str(outside_iso)


def test_vcsa_deploy_candidates_are_unique_for_platform(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "vcsa"

    monkeypatch.setattr(vcenter_netapp_readiness.os, "name", "nt")
    windows_candidates = vcenter_netapp_readiness._vcsa_deploy_candidates(root)
    assert list(windows_candidates) == [
        root / "vcsa-cli-installer" / "win32" / "vcsa-deploy.exe",
        root / "vcsa-cli-installer" / "win32" / "vcsa-deploy",
        root / "vcsa-cli-installer" / "lin64" / "vcsa-deploy",
    ]

    monkeypatch.setattr(vcenter_netapp_readiness.os, "name", "posix")
    posix_candidates = vcenter_netapp_readiness._vcsa_deploy_candidates(root)
    assert list(posix_candidates) == [
        root / "vcsa-cli-installer" / "lin64" / "vcsa-deploy",
        root / "vcsa-cli-installer" / "win32" / "vcsa-deploy.exe",
    ]


def test_vcenter_json_artifact_reader_self_heals_bad_shapes(tmp_path: Path) -> None:
    artifact = tmp_path / "vcenter-artifact.json"

    artifact.write_text("{not-json", encoding="utf-8")
    assert vcenter_netapp_readiness._read_json_artifact(artifact) == {}

    artifact.write_text('["not", "an", "object"]', encoding="utf-8")
    assert vcenter_netapp_readiness._read_json_artifact(artifact) == {}

    assert vcenter_netapp_readiness._read_json_artifact(tmp_path / "missing.json") == {}


def test_vcenter_string_list_coercion_strips_and_dedupes_values() -> None:
    assert vcenter_netapp_readiness._coerce_string_list(
        " 192.0.2.53,192.0.2.53, 192.0.2.54 ,, "
    ) == ["192.0.2.53", "192.0.2.54"]
    assert vcenter_netapp_readiness._coerce_string_list(
        [" time.example.test ", "time.example.test", 123, "123", None]
    ) == ["time.example.test", "123"]
    assert vcenter_netapp_readiness._coerce_string_list(123) == []


def test_vcenter_apply_warnings_keep_scalar_lists_whole() -> None:
    warnings = vcenter_netapp_readiness._vcenter_apply_warnings(
        validation={"warnings": " Post-install inventory is still syncing. "},
        refresh_result={"errors": " Golden State refresh failed. "},
    )

    assert "Post-install inventory is still syncing." in warnings
    assert "Golden State refresh failed." in warnings
    assert not any(warning == "P" for warning in warnings)


def test_vcenter_json_contains_handles_noisy_bom_and_array_output() -> None:
    output = b'\xef\xbb\xbflog line before json\n[{"name": "Lab-DC"}, {"name": "netapp_nfs_ds01"}]'

    assert vcenter_netapp_readiness._json_contains(output, "netapp_nfs_ds01") is True
    assert vcenter_netapp_readiness._json_contains(output, "missing-datastore") is False


def test_vcenter_attach_apply_warnings_keep_scalar_validation_warning_whole() -> None:
    warnings = vcenter_netapp_readiness._vcenter_attach_apply_warnings(
        operations=[],
        validation={"warnings": " Host inventory is still refreshing. "},
    )

    assert "Host inventory is still refreshing." in warnings
    assert not any(warning == "H" for warning in warnings)


def test_vcenter_install_apply_blockers_keep_scalar_sources_whole(monkeypatch) -> None:
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "get_vcenter_install_readiness",
        lambda **_kwargs: {
            "status": "blocked",
            "blockers": " Readiness blocker. ",
            "deployment_values": {},
            "current_state": {},
            "target_state": {},
        },
    )
    monkeypatch.setattr(vcenter_netapp_readiness, "get_vcenter_install_plan", lambda **_kwargs: {"install_plan": {}})
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "get_vcenter_install_preview",
        lambda **_kwargs: {
            "status": "blocked",
            "blockers": " Preview blocker. ",
            "install_plan": {},
        },
    )
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "_vcenter_install_apply_gate_state",
        lambda **_kwargs: {"blockers": []},
    )

    payload = vcenter_netapp_readiness.get_vcenter_install_apply(write_report=False)

    assert "Readiness blocker." in payload["blockers"]
    assert "Preview blocker." in payload["blockers"]
    assert not any(blocker == "R" for blocker in payload["blockers"])


def test_vcenter_install_gate_keeps_scalar_policy_blocker_whole(monkeypatch) -> None:
    class ScalarPolicy:
        def action_blockers(self, _action_id: str, _category: object) -> str:
            return " policy blocker "

    monkeypatch.setattr(vcenter_netapp_readiness, "current_lab_action_policy", lambda _mode: ScalarPolicy())
    monkeypatch.setenv("VCENTER_INSTALL_APPLY", "true")
    monkeypatch.setenv("VCENTER_INSTALL_CONFIRM", vcenter_netapp_readiness.VCENTER_INSTALL_CONFIRM_PHRASE)
    monkeypatch.setenv("VCENTER_INSTALL_ALLOW_DEPLOY", "true")

    gates = vcenter_netapp_readiness._vcenter_install_apply_gate_state(
        readiness_ready=True,
        preview_ready=True,
    )

    assert gates["blockers"] == ["policy blocker"]
    assert "p" not in gates["blockers"]


def test_vcenter_attach_gate_keeps_scalar_policy_blocker_whole(monkeypatch) -> None:
    class ScalarPolicy:
        def action_blockers(self, _action_id: str, _category: object) -> str:
            return " policy blocker "

    monkeypatch.setattr(vcenter_netapp_readiness, "current_lab_action_policy", lambda _mode: ScalarPolicy())
    monkeypatch.setenv("VCENTER_ATTACH_ESXI_APPLY", "true")
    monkeypatch.setenv("VCENTER_ATTACH_ESXI_CONFIRM", vcenter_netapp_readiness.VCENTER_ATTACH_ESXI_CONFIRM_PHRASE)
    monkeypatch.setenv("VCENTER_ATTACH_ESXI_ALLOW", "true")

    gates = vcenter_netapp_readiness._vcenter_attach_apply_gate_state(preview_ready=True)

    assert gates["blockers"] == ["policy blocker"]
    assert "p" not in gates["blockers"]


def test_vcenter_artifact_value_ignores_bad_artifacts(tmp_path: Path) -> None:
    artifact = tmp_path / "console-state.json"

    artifact.write_text("{not-json", encoding="utf-8")
    assert vcenter_netapp_readiness._artifact_value(artifact, "selected_prompt_state") is None

    artifact.write_text('"cluster_setup_prompt"', encoding="utf-8")
    assert vcenter_netapp_readiness._artifact_value(artifact, "selected_prompt_state") is None

    artifact.write_text('{"selected_prompt_state": "cluster_setup_prompt"}', encoding="utf-8")
    assert vcenter_netapp_readiness._artifact_value(artifact, "selected_prompt_state") == "cluster_setup_prompt"


def test_vcenter_install_readiness_treats_management_ip_as_configured_target(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _patch_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "settings",
        _settings(vcenter_management_ip="192.168.1.206"),
    )
    monkeypatch.setattr(vcenter_netapp_readiness, "active_lab_profile_context", lambda: _profile_context())
    monkeypatch.setattr(vcenter_netapp_readiness, "_tool_available", lambda _name: False)

    result = vcenter_netapp_readiness.get_vcenter_install_readiness(check_ports=False, write_report=True)

    assert result["current_state"]["vcenter_installed"] is True
    assert result["deployment_values"]["post_install_vcenter_configured"] is True


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
    assert (tmp_path / "artifacts/codex-runs/vcenter-install-preview-report.md").read_text(encoding="utf-8").strip()


def test_vcenter_datastore_evidence_self_heals_exists_probe_errors(monkeypatch, tmp_path: Path) -> None:
    _patch_paths(monkeypatch, tmp_path)
    _write_datastore_validation(tmp_path)
    artifact = tmp_path / "artifacts" / "codex-runs" / "esxi-netapp-nfs-datastore-validation-redacted.json"
    original_exists = Path.exists

    def flaky_exists(path: Path) -> bool:
        if path == artifact:
            raise OSError("artifact probe unavailable")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    result = vcenter_netapp_readiness._datastore_ready_check("netapp_nfs_ds01")

    assert result["status"] == "ready"
    assert result["evidence_artifacts"] == []


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


def test_vcsa_deploy_windows_exe_is_found_under_mounted_iso(monkeypatch, tmp_path: Path) -> None:
    mounted = tmp_path / "vcsa-iso"
    deploy = mounted / "vcsa-cli-installer" / "win32" / "vcsa-deploy.exe"
    deploy.parent.mkdir(parents=True)
    deploy.write_text("@echo off\n", encoding="utf-8")
    monkeypatch.setattr(vcenter_netapp_readiness, "settings", _settings())
    monkeypatch.setattr(vcenter_netapp_readiness, "VCSA_MOUNT_ROOTS", (mounted,))
    monkeypatch.setattr(vcenter_netapp_readiness, "_is_windows_platform", lambda: True)

    assert vcenter_netapp_readiness._find_vcsa_deploy() == deploy


def test_vcenter_tool_path_skips_unavailable_local_candidate(monkeypatch, tmp_path: Path) -> None:
    candidate = tmp_path / "Scripts" / "govc"
    monkeypatch.setattr(vcenter_netapp_readiness, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(vcenter_netapp_readiness.sys, "executable", str(tmp_path / "Scripts" / "python.exe"))
    monkeypatch.setattr(vcenter_netapp_readiness, "which", lambda _name: None)
    original_is_file = Path.is_file

    def locked_is_file(path: Path) -> bool:
        if path == candidate:
            raise OSError("locked")
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", locked_is_file)

    assert vcenter_netapp_readiness._tool_path("govc") is None


def test_vcsa_deploy_skips_unavailable_explicit_path_and_uses_mounted_iso(monkeypatch, tmp_path: Path) -> None:
    explicit = tmp_path / "locked" / "vcsa-deploy"
    mounted = tmp_path / "vcsa-iso"
    deploy = mounted / "vcsa-cli-installer" / "lin64" / "vcsa-deploy"
    deploy.parent.mkdir(parents=True)
    deploy.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(vcenter_netapp_readiness, "settings", _settings(vcenter_vcsa_deploy_path=str(explicit)))
    monkeypatch.setattr(vcenter_netapp_readiness, "VCSA_MOUNT_ROOTS", (mounted,))
    monkeypatch.setattr(vcenter_netapp_readiness, "_tool_path", lambda _name: None)
    original_is_file = Path.is_file

    def locked_is_file(path: Path) -> bool:
        if path == explicit:
            raise OSError("locked")
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", locked_is_file)

    assert vcenter_netapp_readiness._find_vcsa_deploy() == deploy


def test_vcsa_iso_skips_unavailable_explicit_path_and_uses_media_dir(monkeypatch, tmp_path: Path) -> None:
    explicit = tmp_path / "locked" / "VMware-VCSA-all-8.0.3.iso"
    media = tmp_path / "media" / "VMware-VCSA-all-8.0.3.iso"
    media.parent.mkdir()
    media.write_bytes(b"vcsa")
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "settings",
        _settings(media_inventory_dirs=(str(media.parent),), vcenter_vcsa_iso_path=str(explicit)),
    )
    original_is_file = Path.is_file

    def locked_is_file(path: Path) -> bool:
        if path == explicit:
            raise OSError("locked")
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", locked_is_file)

    assert vcenter_netapp_readiness._find_vcsa_iso() == media


def test_vcsa_iso_discovery_skips_recursive_scan_errors(monkeypatch, tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "settings",
        _settings(media_inventory_dirs=(str(media_root),), vcenter_vcsa_iso_path=None),
    )
    monkeypatch.setattr(vcenter_netapp_readiness, "REPO_ROOT", tmp_path)
    original_rglob = Path.rglob

    def flaky_rglob(path: Path, pattern: str):  # noqa: ANN202
        if path == media_root:
            raise OSError("recursive scan failed")
        return original_rglob(path, pattern)

    monkeypatch.setattr(Path, "rglob", flaky_rglob)

    assert vcenter_netapp_readiness._find_vcsa_iso() is None


def test_vcsa_mount_roots_are_platform_aware(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(vcenter_netapp_readiness, "_is_windows_platform", lambda: True)
    monkeypatch.setattr(vcenter_netapp_readiness.tempfile, "gettempdir", lambda: str(tmp_path))

    assert vcenter_netapp_readiness._default_vcsa_mount_roots() == (tmp_path / "vcsa-iso",)

    monkeypatch.setattr(vcenter_netapp_readiness, "_is_windows_platform", lambda: False)

    assert Path("/mnt/vcsa-iso") in vcenter_netapp_readiness._default_vcsa_mount_roots()


def test_vcsa_deploy_temp_spec_chmod_failure_does_not_abort(monkeypatch, tmp_path: Path) -> None:
    deploy = tmp_path / "vcsa-deploy"
    deploy.write_text("#!/bin/sh\n", encoding="utf-8")
    deploy.chmod(0o755)
    seen: dict[str, str] = {}

    def fake_chmod(_path: str, _mode: int) -> None:
        raise OSError("chmod unavailable")

    def fake_run(command, **_kwargs):  # noqa: ANN001, ANN003
        spec_path = command[-1]
        seen["spec"] = Path(spec_path).read_text(encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(vcenter_netapp_readiness.os, "chmod", fake_chmod)
    monkeypatch.setattr(vcenter_netapp_readiness.subprocess, "run", fake_run)

    result = vcenter_netapp_readiness._run_vcsa_deploy(
        {"new_vcsa": {"appliance": {"name": "vcsa01"}}},
        str(deploy),
    )

    assert result["vcsa_deploy_attempted"] is True
    assert result["result"] == "completed"
    assert '"vcsa01"' in seen["spec"]


def test_vcsa_deploy_treats_path_probe_errors_as_not_found(monkeypatch, tmp_path: Path) -> None:
    deploy = tmp_path / "vcsa-deploy"
    original_exists = Path.exists

    def locked_exists(path: Path) -> bool:
        if path == deploy:
            raise OSError("deploy path unavailable")
        return original_exists(path)

    monkeypatch.setattr(Path, "exists", locked_exists)

    result = vcenter_netapp_readiness._run_vcsa_deploy(
        {"new_vcsa": {"appliance": {"name": "vcsa01"}}},
        str(deploy),
    )

    assert result["vcsa_deploy_attempted"] is False
    assert result["return_code"] == 127
    assert result["result"] == "not_found"


def test_vcenter_install_apply_refuses_without_explicit_gates(monkeypatch, tmp_path: Path) -> None:
    _patch_paths(monkeypatch, tmp_path)
    media, vcsa_deploy = _write_vcsa_media(tmp_path)
    _write_datastore_validation(tmp_path)
    monkeypatch.delenv("VCENTER_INSTALL_APPLY", raising=False)
    monkeypatch.delenv("VCENTER_INSTALL_CONFIRM", raising=False)
    monkeypatch.delenv("VCENTER_INSTALL_ALLOW_DEPLOY", raising=False)
    monkeypatch.setattr(vcenter_netapp_readiness, "settings", _ready_settings(media, vcsa_deploy))
    monkeypatch.setattr(vcenter_netapp_readiness, "active_lab_profile_context", lambda: _profile_context())
    monkeypatch.setattr(vcenter_netapp_readiness, "current_lab_action_policy", lambda _mode=None: _AllowPolicy())
    monkeypatch.setattr(vcenter_netapp_readiness, "_tool_available", lambda _name: True)
    monkeypatch.setattr(vcenter_netapp_readiness, "_tcp_check", _tcp_ready)
    monkeypatch.setattr(vcenter_netapp_readiness, "_ip_available_check", _ip_available)

    def fail_deploy(_spec: dict, _deploy_path: str | None) -> dict:
        raise AssertionError("vcsa-deploy must not run without explicit gates")

    monkeypatch.setattr(vcenter_netapp_readiness, "_run_vcsa_deploy", fail_deploy)

    result = vcenter_netapp_readiness.get_vcenter_install_apply(write_report=True)

    assert result["status"] == "blocked"
    assert result["apply"]["vcsa_deploy_attempted"] is False
    assert "VCENTER_INSTALL_APPLY=true is required." in result["blockers"]
    assert (tmp_path / "artifacts/codex-runs/vcenter-install-apply-report.md").read_text(encoding="utf-8").strip()


def test_vcenter_install_gate_accepts_common_true_like_env_values(monkeypatch) -> None:
    monkeypatch.setattr(vcenter_netapp_readiness, "settings", _settings(provider_mode="local-lab-readwrite"))
    monkeypatch.setattr(vcenter_netapp_readiness, "current_lab_action_policy", lambda _mode=None: _AllowPolicy())
    monkeypatch.setenv("VCENTER_INSTALL_APPLY", " YES ")
    monkeypatch.setenv("VCENTER_INSTALL_CONFIRM", "DEPLOY VCENTER")
    monkeypatch.setenv("VCENTER_INSTALL_ALLOW_DEPLOY", "1")

    result = vcenter_netapp_readiness._vcenter_install_apply_gate_state(
        readiness_ready=True,
        preview_ready=True,
    )

    assert result["blockers"] == []
    assert result["flag_state"]["install_apply"] is True
    assert result["flag_state"]["install_allow_deploy"] is True


def test_vcenter_install_apply_runs_vcsa_deploy_and_redacts_secrets(monkeypatch, tmp_path: Path) -> None:
    _patch_paths(monkeypatch, tmp_path)
    media, vcsa_deploy = _write_vcsa_media(tmp_path)
    _write_datastore_validation(tmp_path)
    monkeypatch.setenv("VCENTER_INSTALL_APPLY", "true")
    monkeypatch.setenv("VCENTER_INSTALL_CONFIRM", "DEPLOY VCENTER")
    monkeypatch.setenv("VCENTER_INSTALL_ALLOW_DEPLOY", "true")
    monkeypatch.setattr(vcenter_netapp_readiness, "settings", _ready_settings(media, vcsa_deploy))
    monkeypatch.setattr(vcenter_netapp_readiness, "active_lab_profile_context", lambda: _profile_context())
    monkeypatch.setattr(vcenter_netapp_readiness, "current_lab_action_policy", lambda _mode=None: _AllowPolicy())
    monkeypatch.setattr(vcenter_netapp_readiness, "_tool_available", lambda _name: True)
    monkeypatch.setattr(vcenter_netapp_readiness, "_tcp_check", _tcp_ready)
    monkeypatch.setattr(vcenter_netapp_readiness, "_ip_available_check", _ip_available)
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "_server_certificate_sha1_thumbprint",
        lambda _host: "AA:BB:CC",
    )
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "validate_vcenter_post_install",
        lambda **_kwargs: {"status": "ready", "blockers": [], "warnings": []},
    )
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "_refresh_post_install_reports",
        lambda: {"refreshed": {"golden_state_status": "ready", "lab_validation_status": "ready"}, "errors": []},
    )

    def fake_deploy(spec: dict, deploy_path: str | None) -> dict:
        assert deploy_path == str(vcsa_deploy.resolve())
        assert spec["new_vcsa"]["sso"]["password"] == "super-secret-sso"
        assert spec["new_vcsa"]["os"]["password"] == "super-secret-root"
        assert spec["new_vcsa"]["os"]["time_tools_sync"] is True
        assert "ntp_servers" not in spec["new_vcsa"]["os"]
        assert spec["new_vcsa"]["esxi"]["password"] == "super-secret-esxi"
        assert spec["new_vcsa"]["esxi"]["ssl_certificate_verification"] == {"thumbprint": "AA:BB:CC"}
        return {
            "vcsa_deploy_attempted": True,
            "return_code": 0,
            "result": "completed",
            "stdout_summary": "deployed super-secret-sso",
            "stderr_summary": "",
            "command": "vcsa-deploy install --accept-eula --acknowledge-ceip <generated-vcsa-spec.json>",
        }

    monkeypatch.setattr(vcenter_netapp_readiness, "_run_vcsa_deploy", fake_deploy)

    result = vcenter_netapp_readiness.get_vcenter_install_apply(write_report=True)
    serialized = json.dumps(result)

    assert result["status"] == "completed"
    assert result["apply"]["vcsa_deploy_attempted"] is True
    assert result["apply_enabled"] is True
    assert "super-secret" not in serialized
    assert (tmp_path / "artifacts/codex-runs/vcenter-install-spec-redacted.json").exists()
    assert (tmp_path / "artifacts/codex-runs/vcenter-install-apply-unblock-final-report.md").read_text(encoding="utf-8").strip()


def test_vcsa_deploy_command_skips_esxi_tls_when_lab_tls_verify_is_disabled(monkeypatch, tmp_path: Path) -> None:
    media, vcsa_deploy = _write_vcsa_media(tmp_path)
    monkeypatch.setattr(vcenter_netapp_readiness, "settings", _ready_settings(media, vcsa_deploy))

    command = vcenter_netapp_readiness._vcsa_deploy_install_command("vcsa-deploy", "spec.json")

    assert "--no-ssl-certificate-verification" in command
    assert command[-1] == "spec.json"


def test_vcenter_management_ip_stale_neighbor_does_not_block(monkeypatch) -> None:
    monkeypatch.setattr(vcenter_netapp_readiness, "_ping", lambda _address: False)
    monkeypatch.setattr(vcenter_netapp_readiness, "_tcp_open", lambda _address, _port: False)
    monkeypatch.setattr(vcenter_netapp_readiness, "_neighbor_state", lambda _address: "STALE")

    result = vcenter_netapp_readiness._ip_available_check("vCenter management IP", "192.168.1.206", check_ports=True)

    assert result["status"] == "ready"
    assert result["available"] is True
    assert result["neighbor_state"] == "STALE"


def test_vcenter_validation_defaults_to_insecure_tls_for_local_lab(monkeypatch, tmp_path: Path) -> None:
    media, vcsa_deploy = _write_vcsa_media(tmp_path)
    monkeypatch.delenv("VCENTER_VERIFY_TLS", raising=False)
    monkeypatch.delenv("GOVC_TLS_VERIFY", raising=False)
    monkeypatch.setattr(vcenter_netapp_readiness, "settings", _ready_settings(media, vcsa_deploy))

    assert vcenter_netapp_readiness._vcenter_validation_verify_tls() is False


def test_vcenter_validation_defaults_to_insecure_tls_for_local_readonly(monkeypatch, tmp_path: Path) -> None:
    media, vcsa_deploy = _write_vcsa_media(tmp_path)
    monkeypatch.delenv("VCENTER_VERIFY_TLS", raising=False)
    monkeypatch.delenv("GOVC_TLS_VERIFY", raising=False)
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "settings",
        _settings(
            provider_mode="local-readonly",
            vcenter_vcsa_deploy_path=str(vcsa_deploy),
            media_inventory_dirs=(str(media.parent),),
        ),
    )

    assert vcenter_netapp_readiness._vcenter_validation_verify_tls() is False


def test_vcenter_validation_prefers_sso_credentials_over_generic_govc(monkeypatch, tmp_path: Path) -> None:
    media, vcsa_deploy = _write_vcsa_media(tmp_path)
    monkeypatch.delenv("VCENTER_USERNAME", raising=False)
    monkeypatch.delenv("VCENTER_PASSWORD", raising=False)
    monkeypatch.setenv("GOVC_USERNAME", "root")
    monkeypatch.setenv("GOVC_PASSWORD", "esxi-password")
    monkeypatch.setattr(vcenter_netapp_readiness, "settings", _ready_settings(media, vcsa_deploy))

    assert vcenter_netapp_readiness._vcenter_validation_username() == "Administrator@vsphere.local"
    assert vcenter_netapp_readiness._vcenter_validation_password() == "super-secret-sso"


def test_vcenter_validation_canonicalizes_explicit_administrator_username(monkeypatch, tmp_path: Path) -> None:
    media, vcsa_deploy = _write_vcsa_media(tmp_path)
    monkeypatch.setenv("VCENTER_USERNAME", "administrator@vsphere.local")
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "settings",
        _settings(
            provider_mode="local-lab-readwrite",
            vcenter_sso_admin_username=None,
            vcenter_sso_admin_password=None,
            vcenter_vcsa_deploy_path=str(vcsa_deploy),
            media_inventory_dirs=(str(media.parent),),
        ),
    )

    assert vcenter_netapp_readiness._vcenter_validation_username() == "Administrator@vsphere.local"


def test_vcenter_attach_preview_plans_datacenter_cluster_and_host_attach(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _patch_paths(monkeypatch, tmp_path)
    media, vcsa_deploy = _write_vcsa_media(tmp_path)
    monkeypatch.setattr(vcenter_netapp_readiness, "settings", _ready_settings(media, vcsa_deploy))
    monkeypatch.setattr(vcenter_netapp_readiness, "_tool_available", lambda _name: True)
    monkeypatch.setattr(vcenter_netapp_readiness, "_tcp_check", _tcp_ready)
    monkeypatch.setattr(vcenter_netapp_readiness, "_server_certificate_sha1_thumbprint", lambda _host: "AA:BB:CC")
    monkeypatch.setattr(vcenter_netapp_readiness, "_run_vcenter_govc", _empty_vcenter_inventory)

    result = vcenter_netapp_readiness.get_vcenter_attach_esxi_preview(write_report=True)
    serialized = json.dumps(result)

    assert result["status"] == "ready"
    assert result["action"] == "vcenter-attach-esxi-preview"
    assert result["attach_plan"]["steps"][0]["status"] == "will_create"
    assert result["attach_plan"]["steps"][2]["status"] == "will_attach"
    assert result["checks"]["esxi_certificate_thumbprint"]["status"] == "ready"
    assert "super-secret" not in serialized
    assert (tmp_path / "artifacts/codex-runs/vcenter-attach-esxi-preview-report.md").read_text(encoding="utf-8").strip()


def test_vcenter_attach_apply_refuses_without_explicit_gates(monkeypatch, tmp_path: Path) -> None:
    _patch_paths(monkeypatch, tmp_path)
    media, vcsa_deploy = _write_vcsa_media(tmp_path)
    monkeypatch.delenv("VCENTER_ATTACH_ESXI_APPLY", raising=False)
    monkeypatch.delenv("VCENTER_ATTACH_ESXI_CONFIRM", raising=False)
    monkeypatch.delenv("VCENTER_ATTACH_ESXI_ALLOW", raising=False)
    monkeypatch.setattr(vcenter_netapp_readiness, "settings", _ready_settings(media, vcsa_deploy))
    monkeypatch.setattr(vcenter_netapp_readiness, "current_lab_action_policy", lambda _mode=None: _AllowPolicy())
    monkeypatch.setattr(vcenter_netapp_readiness, "_tool_available", lambda _name: True)
    monkeypatch.setattr(vcenter_netapp_readiness, "_tcp_check", _tcp_ready)
    monkeypatch.setattr(vcenter_netapp_readiness, "_server_certificate_sha1_thumbprint", lambda _host: "AA:BB:CC")
    monkeypatch.setattr(vcenter_netapp_readiness, "_run_vcenter_govc", _empty_vcenter_inventory)

    def fail_operation(_target: dict) -> dict:
        raise AssertionError("attach operations must not run without explicit gates")

    monkeypatch.setattr(vcenter_netapp_readiness, "_ensure_vcenter_datacenter", fail_operation)

    result = vcenter_netapp_readiness.get_vcenter_attach_esxi_apply(write_report=True)

    assert result["status"] == "blocked"
    assert "VCENTER_ATTACH_ESXI_APPLY=true is required." in result["blockers"]
    assert not result["operations"]
    assert (tmp_path / "artifacts/codex-runs/vcenter-attach-esxi-apply-report.md").read_text(encoding="utf-8").strip()


def test_vcenter_attach_gate_accepts_common_true_like_env_values(monkeypatch) -> None:
    monkeypatch.setattr(vcenter_netapp_readiness, "settings", _settings(provider_mode="local-lab-readwrite"))
    monkeypatch.setattr(vcenter_netapp_readiness, "current_lab_action_policy", lambda _mode=None: _AllowPolicy())
    monkeypatch.setenv("VCENTER_ATTACH_ESXI_APPLY", "ON")
    monkeypatch.setenv("VCENTER_ATTACH_ESXI_CONFIRM", "ATTACH ESXI TO VCENTER")
    monkeypatch.setenv("VCENTER_ATTACH_ESXI_ALLOW", " y ")

    result = vcenter_netapp_readiness._vcenter_attach_apply_gate_state(preview_ready=True)

    assert result["blockers"] == []
    assert result["flag_state"]["attach_apply"] is True
    assert result["flag_state"]["attach_allow"] is True


def test_vcenter_attach_apply_runs_operations_and_redacts_secrets(monkeypatch, tmp_path: Path) -> None:
    _patch_paths(monkeypatch, tmp_path)
    media, vcsa_deploy = _write_vcsa_media(tmp_path)
    monkeypatch.setenv("VCENTER_ATTACH_ESXI_APPLY", "true")
    monkeypatch.setenv("VCENTER_ATTACH_ESXI_CONFIRM", "ATTACH ESXI TO VCENTER")
    monkeypatch.setenv("VCENTER_ATTACH_ESXI_ALLOW", "true")
    monkeypatch.setattr(vcenter_netapp_readiness, "settings", _ready_settings(media, vcsa_deploy))
    monkeypatch.setattr(vcenter_netapp_readiness, "current_lab_action_policy", lambda _mode=None: _AllowPolicy())
    monkeypatch.setattr(vcenter_netapp_readiness, "_tool_available", lambda _name: True)
    monkeypatch.setattr(vcenter_netapp_readiness, "_tcp_check", _tcp_ready)
    monkeypatch.setattr(vcenter_netapp_readiness, "_server_certificate_sha1_thumbprint", lambda _host: "AA:BB:CC")
    monkeypatch.setattr(vcenter_netapp_readiness, "_run_vcenter_govc", _empty_vcenter_inventory)
    monkeypatch.setattr(vcenter_netapp_readiness, "_refresh_post_install_reports", lambda: {"refreshed": {}, "errors": []})
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "_ensure_vcenter_datacenter",
        lambda _target: _operation("datacenter.ensure", changed=True),
    )
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "_ensure_vcenter_cluster",
        lambda _target: _operation("cluster.ensure", changed=True),
    )
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "_attach_esxi_host_to_vcenter",
        lambda _target: _operation("esxi.attach", changed=True, stderr="super-secret-esxi"),
    )
    monkeypatch.setattr(
        vcenter_netapp_readiness,
        "validate_vcenter_post_attach",
        lambda **_kwargs: {"status": "ready", "blockers": [], "warnings": []},
    )

    result = vcenter_netapp_readiness.get_vcenter_attach_esxi_apply(write_report=True)
    serialized = json.dumps(result)

    assert result["status"] == "completed"
    assert [operation["operation"] for operation in result["operations"]] == [
        "datacenter.ensure",
        "cluster.ensure",
        "esxi.attach",
    ]
    assert "super-secret" not in serialized
    assert (tmp_path / "artifacts/codex-runs/vcenter-attach-esxi-datastore-final-report.md").read_text(encoding="utf-8").strip()


def test_vcenter_post_attach_validation_requires_host_datastore_and_vm_inventory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _patch_paths(monkeypatch, tmp_path)
    media, vcsa_deploy = _write_vcsa_media(tmp_path)
    monkeypatch.setattr(vcenter_netapp_readiness, "settings", _ready_settings(media, vcsa_deploy))
    monkeypatch.setattr(vcenter_netapp_readiness, "_tool_available", lambda _name: True)
    monkeypatch.setattr(vcenter_netapp_readiness, "_run_vcenter_govc", _ready_vcenter_inventory)

    result = vcenter_netapp_readiness.validate_vcenter_post_attach(write_report=True)

    assert result["status"] == "ready"
    assert result["checks"]["datacenter_visible"]["visible"] is True
    assert result["checks"]["esxi_visible"]["visible"] is True
    assert result["checks"]["netapp_datastore_visible"]["visible"] is True
    assert result["checks"]["vm_inventory_visible"]["count"] == 1
    assert (tmp_path / "artifacts/codex-runs/vcenter-post-attach-validation-report.md").read_text(encoding="utf-8").strip()


def _patch_paths(monkeypatch, tmp_path: Path) -> None:
    run_dir = tmp_path / "artifacts" / "codex-runs"
    monkeypatch.setattr(vcenter_netapp_readiness, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(vcenter_netapp_readiness, "CODEX_RUN_DIR", run_dir)
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_INSTALL_READINESS_REPORT", run_dir / "vcenter-install-readiness-report.md")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_INSTALL_PLAN_REPORT", run_dir / "vcenter-install-plan-report.md")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_INSTALL_PREVIEW_REPORT", run_dir / "vcenter-install-preview-report.md")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_INSTALL_APPLY_REPORT", run_dir / "vcenter-install-apply-report.md")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_POST_INSTALL_VALIDATION_REPORT", run_dir / "vcenter-post-install-validation-report.md")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_INSTALL_APPLY_FINAL_REPORT", run_dir / "vcenter-install-apply-unblock-final-report.md")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_ATTACH_ESXI_PREVIEW_REPORT", run_dir / "vcenter-attach-esxi-preview-report.md")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_ATTACH_ESXI_APPLY_REPORT", run_dir / "vcenter-attach-esxi-apply-report.md")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_POST_ATTACH_VALIDATION_REPORT", run_dir / "vcenter-post-attach-validation-report.md")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_ATTACH_ESXI_FINAL_REPORT", run_dir / "vcenter-attach-esxi-datastore-final-report.md")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_INSTALL_READINESS_JSON", run_dir / "vcenter-install-readiness-redacted.json")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_INSTALL_PLAN_JSON", run_dir / "vcenter-install-plan-redacted.json")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_INSTALL_PREVIEW_JSON", run_dir / "vcenter-install-preview-redacted.json")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_INSTALL_APPLY_JSON", run_dir / "vcenter-install-apply-redacted.json")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_POST_INSTALL_VALIDATION_JSON", run_dir / "vcenter-post-install-validation-redacted.json")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_ATTACH_ESXI_PREVIEW_JSON", run_dir / "vcenter-attach-esxi-preview-redacted.json")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_ATTACH_ESXI_APPLY_JSON", run_dir / "vcenter-attach-esxi-apply-redacted.json")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_POST_ATTACH_VALIDATION_JSON", run_dir / "vcenter-post-attach-validation-redacted.json")
    monkeypatch.setattr(vcenter_netapp_readiness, "VCENTER_INSTALL_SPEC_REDACTED_JSON", run_dir / "vcenter-install-spec-redacted.json")


def _settings(**overrides) -> SimpleNamespace:
    values = {
        "provider_mode": "local-readonly",
        "media_inventory_dirs": (),
        "lab_subnet_cidr": "192.168.1.0/24",
        "esxi_test_host": "192.168.1.203",
        "esxi_test_username": None,
        "esxi_test_password": None,
        "esxi_test_verify_tls": False,
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
        "vcenter_datacenter_name": "Lab-DC",
        "vcenter_cluster_name": "Lab-Cluster",
        "vcenter_vcsa_iso_path": None,
        "vcenter_vcsa_deploy_path": None,
        "vcenter_deployment_size": "tiny",
        "vcenter_network": None,
        "vcenter_portgroup": None,
        "vcenter_verify_tls": False,
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


class _AllowPolicy:
    def action_blockers(self, _action_id: str, _category: object) -> list[str]:
        return []


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


def _write_vcsa_media(root: Path) -> tuple[Path, Path]:
    media = root / "artifacts" / "Media" / "VMware-VCSA-all-8.0.3.iso"
    vcsa_deploy = root / "vcsa-cli-installer" / "lin64" / "vcsa-deploy"
    media.parent.mkdir(parents=True)
    vcsa_deploy.parent.mkdir(parents=True)
    media.write_bytes(b"vcsa")
    vcsa_deploy.write_text("#!/bin/sh\n", encoding="utf-8")
    vcsa_deploy.chmod(0o755)
    return media, vcsa_deploy


def _ready_settings(media: Path, vcsa_deploy: Path) -> SimpleNamespace:
    return _settings(
        provider_mode="local-lab-readwrite",
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
    )


def _empty_vcenter_inventory(args: list[str], *, timeout: int) -> dict:
    if args == ["about"]:
        return {"status": "ready", "return_code": 0, "stdout": "vCenter", "stderr": ""}
    return {"status": "ready", "return_code": 0, "stdout": "", "stderr": ""}


def _ready_vcenter_inventory(args: list[str], *, timeout: int) -> dict:
    if args == ["about"]:
        return {"status": "ready", "return_code": 0, "stdout": "vCenter", "stderr": ""}
    text = " ".join(args)
    if "-type d" in text:
        stdout = "/Lab-DC\n"
    elif "-type c" in text:
        stdout = "/Lab-DC/host/Lab-Cluster\n"
    elif "-type h" in text:
        stdout = "/Lab-DC/host/Lab-Cluster/192.168.1.203\n"
    elif "-type s" in text:
        stdout = "/Lab-DC/datastore/netapp_nfs_ds01\n"
    elif "-type m" in text:
        stdout = "/Lab-DC/vm/vcsa01\n"
    else:
        stdout = ""
    return {"status": "ready", "return_code": 0, "stdout": stdout, "stderr": ""}


def _operation(operation: str, *, changed: bool, stderr: str = "") -> dict:
    return {
        "operation": operation,
        "status": "ready",
        "attempted": changed,
        "changed": changed,
        "detail": f"{operation} completed.",
        "command_preview": operation,
        "return_code": 0,
        "stdout_summary": "",
        "stderr_summary": stderr,
    }
