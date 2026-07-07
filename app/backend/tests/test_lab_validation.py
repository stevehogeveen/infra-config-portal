from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.services import lab_profiles
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


def test_validation_item_dedupes_supporting_lists() -> None:
    item = lab_validation._item(
        item_id="example",
        label="Example",
        category="test",
        status="warning",
        current_state="checked",
        desired_state="ready",
        setup_summary="summary",
        next_action="next",
        login_hint="hint",
        management_url=None,
        ssh_target=None,
        proof_points=[" proof ", "proof", "", None, "other"],
        evidence_artifacts=["artifacts/one.md", " artifacts/one.md ", "", "artifacts/two.md"],
        last_checked=None,
        source_type="historical_artifact",
        freshness="historical",
        blockers=[],
        warnings=["warn", " warn ", "", None, "second"],
        recheck_command="make test",
        linked_workflow_action=None,
    )

    assert item["proof_points"] == ["proof", "other"]
    assert item["evidence_artifacts"] == ["artifacts/one.md", "artifacts/two.md"]
    assert item["warnings"] == ["warn", "second"]


def test_lab_validation_report_paths_use_posix_separators(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(lab_validation, "REPO_ROOT", tmp_path)

    assert lab_validation._rel(tmp_path / "artifacts" / "codex-runs" / "report.md") == "artifacts/codex-runs/report.md"


def test_lab_profile_path_labels_use_posix_separators(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(lab_profiles, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / ".local" / "lab-profiles.json"))

    assert lab_profiles._store_path_label() == ".local/lab-profiles.json"
    assert lab_profiles._path_label(tmp_path / ".env.local.real-lab") == ".env.local.real-lab"


def test_lab_profile_read_text_lines_self_heals_exists_probe_errors(monkeypatch, tmp_path: Path) -> None:
    env_path = tmp_path / ".env.local.real-lab"
    original_exists = Path.exists

    def flaky_exists(self: Path) -> bool:
        if self == env_path:
            raise OSError("env path unavailable")
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    assert lab_profiles._read_text_lines(env_path) == []


def test_lab_profile_env_values_ignore_dotenv_parse_errors(monkeypatch, tmp_path: Path) -> None:
    env_path = tmp_path / ".env.local.real-lab"
    env_path.write_text("LAB_GATEWAY=10.0.0.1\n", encoding="utf-8")
    errors = [
        OSError("unreadable"),
        UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
        ValueError("invalid dotenv value"),
    ]

    for error in errors:
        monkeypatch.setattr(lab_profiles, "read_dotenv_values", lambda _path, error=error: (_ for _ in ()).throw(error))

        assert lab_profiles._read_env_file_values(env_path) == {}


def test_lab_profile_runtime_env_write_dedupes_managed_keys(tmp_path: Path) -> None:
    env_path = tmp_path / ".env.local.real-lab"
    env_path.write_text(
        "\n".join(
            [
                "# keep comments",
                "LAB_GATEWAY=10.0.0.1",
                "LAB_GATEWAY=10.0.0.254",
                "UNMANAGED_KEY=first",
                "UNMANAGED_KEY=second",
                "LAB_MTU=1500",
                "LAB_MTU=1500",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    updated, removed = lab_profiles._write_runtime_env(
        env_path,
        updates={"LAB_GATEWAY": "10.0.0.2", "LAB_MTU": "1500"},
        removals=set(),
    )

    lines = env_path.read_text(encoding="utf-8").splitlines()
    assert updated == ["LAB_GATEWAY"]
    assert removed == []
    assert lines.count("LAB_GATEWAY=10.0.0.2") == 1
    assert lines.count("LAB_MTU=1500") == 1
    assert "LAB_GATEWAY=10.0.0.254" not in lines
    assert "LAB_MTU=9000" not in lines
    assert lines.count("UNMANAGED_KEY=first") == 1
    assert lines.count("UNMANAGED_KEY=second") == 1


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
    assert items["esxi-iscsi-datastore"]["status"] == "not_in_scope"
    assert items["netapp-console"]["blockers"] == []
    assert items["netapp-ontap-cluster"]["blockers"] == []
    assert items["vcenter-netapp-datastore"]["blockers"] == []
    assert items["esxi-iscsi-datastore"]["blockers"] == []


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


def test_json_artifact_self_heals_corrupt_cache(monkeypatch, tmp_path: Path) -> None:
    _patch_lab_validation_paths(monkeypatch, tmp_path)
    artifact = tmp_path / "artifacts" / "codex-runs" / "netapp-console-state-redacted.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("{not valid json", encoding="utf-8")

    assert lab_validation._json_artifact("artifacts/codex-runs/netapp-console-state-redacted.json") == {}


def test_existing_artifacts_skips_paths_that_error(monkeypatch) -> None:
    class ArtifactPath:
        def __init__(self, *, exists: bool = True, exists_error: Exception | None = None) -> None:
            self._exists = exists
            self._exists_error = exists_error

        def exists(self) -> bool:
            if self._exists_error:
                raise self._exists_error
            return self._exists

    class RepoRoot:
        def __truediv__(self, path: str) -> ArtifactPath:
            return artifacts[path]

    artifacts = {
        "artifacts/ready.md": ArtifactPath(),
        "artifacts/locked.md": ArtifactPath(exists_error=OSError("locked")),
        "artifacts/missing.md": ArtifactPath(exists=False),
    }
    monkeypatch.setattr(lab_validation, "REPO_ROOT", RepoRoot())

    assert lab_validation._existing(list(artifacts)) == ["artifacts/ready.md"]


def test_last_checked_skips_artifacts_that_disappear(monkeypatch) -> None:
    class ArtifactPath:
        def __init__(self, *, mtime: float, stat_error: Exception | None = None) -> None:
            self._mtime = mtime
            self._stat_error = stat_error

        def exists(self) -> bool:
            return True

        def stat(self) -> SimpleNamespace:
            if self._stat_error:
                raise self._stat_error
            return SimpleNamespace(st_mtime=self._mtime)

    class RepoRoot:
        def __truediv__(self, path: str) -> ArtifactPath:
            return artifacts[path]

    artifacts = {
        "artifacts/older.md": ArtifactPath(mtime=1),
        "artifacts/disappeared.md": ArtifactPath(mtime=999, stat_error=FileNotFoundError("gone")),
        "artifacts/newer.md": ArtifactPath(mtime=2),
    }
    monkeypatch.setattr(lab_validation, "REPO_ROOT", RepoRoot())

    assert lab_validation._last_checked(list(artifacts)) == "1970-01-01T00:00:02+00:00"


def test_login_hints_do_not_include_secret_values() -> None:
    payload = get_lab_validation_summary(write_report=False)
    serialized = json.dumps(payload).lower()

    assert "password=" not in serialized
    assert "token=" not in serialized
    assert "bearer " not in serialized
    assert "private_key" not in serialized
    assert (
        lab_validation._login_hint("https://192.168.1.10", ["ILO_USERNAME", "ILO_PASSWORD"])
        == "https://192.168.1.10; credentials not configured: ILO_USERNAME, ILO_PASSWORD"
    )


def test_ready_cisco_shows_ssh_login_hint(monkeypatch, tmp_path: Path) -> None:
    _patch_lab_validation_paths(monkeypatch, tmp_path)
    item = build_cisco_validation_item(management_ready=True, target_ip="192.168.1.204")

    assert item["status"] == "ready"
    assert item["login_hint"] == "ssh admin@192.168.1.204"
    assert item["ssh_target"] == "admin@192.168.1.204"


def test_cisco_validation_warns_on_current_intent_drift(monkeypatch, tmp_path: Path) -> None:
    _patch_lab_validation_paths(monkeypatch, tmp_path)
    run_dir = tmp_path / "artifacts" / "codex-runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "cisco-current-intent-diff-report.md").write_text("# Cisco diff\n", encoding="utf-8")
    (run_dir / "cisco-current-intent-diff-redacted.json").write_text(
        json.dumps(
            {
                "status": "warning",
                "checked_at": "2026-07-01T01:52:57+00:00",
                "source_type": "live_probe",
                "freshness": "current",
                "current": {"vlans": [{"id": "10"}], "ports": [{"port": "Gi1/0/1"}]},
                "diff": {
                    "drift_count": 3,
                    "vlan": {"missing": ["20", "999"], "unexpected": ["1002"]},
                    "ports": [{"port": "Gi1/0/5", "issues": ["access_vlan"]}],
                    "guardrails": {
                        "bpdu_guard": {"status": "warning", "missing": ["spanning-tree bpduguard default"]},
                        "acl_lanes": {"status": "ready", "missing": []},
                        "blackhole_vlan": {"status": "warning", "missing": ["999"]},
                    },
                },
                "next_safe_action": "Review drift before guarded apply.",
            }
        ),
        encoding="utf-8",
    )

    item = build_cisco_validation_item(
        actions={"cisco.current-intent-diff": {"action_id": "cisco.current-intent-diff", "label": "Diff", "stage": "cisco"}},
        management_ready=True,
        target_ip="192.168.1.204",
    )

    assert item["status"] == "warning"
    assert item["source_type"] == "live_probe"
    assert item["freshness"] == "current"
    assert item["current_state"] == "Management SSH is reachable; current-to-intent drift count is 3."
    assert "Missing intended VLANs: 20, 999." in item["warnings"]
    assert "Unexpected VLANs present: 1002." in item["warnings"]
    assert item["linked_workflow_action"]["action_id"] == "cisco.current-intent-diff"


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
    summary = json.loads(lab_validation.SUMMARY_JSON.read_text(encoding="utf-8"))
    assert summary["overall_status"] in lab_validation.VALIDATION_STATUSES
    assert lab_validation.HANDOFF_REPORT.read_text(encoding="utf-8").strip()
    assert not list(lab_validation.CODEX_RUN_DIR.glob("*.tmp"))


def test_lab_validation_marks_esxi_iscsi_blocked_from_real_validation_artifact(
    monkeypatch,
    tmp_path,
) -> None:
    _enable_high_storage_profile(
        monkeypatch,
        tmp_path,
        features={"netapp_enabled": True, "vcenter_enabled": True, "storage_protocol": "iscsi"},
    )
    _patch_lab_validation_paths(monkeypatch, tmp_path)
    run_dir = tmp_path / "artifacts" / "codex-runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "esxi-iscsi-datastore-validation-report.md").write_text("# ESXi iSCSI\n", encoding="utf-8")
    (run_dir / "esxi-iscsi-datastore-validation-redacted.json").write_text(
        json.dumps(
            {
                "status": "blocked",
                "checked_at": "2026-07-01T00:04:46+00:00",
                "source_type": "live_probe",
                "freshness": "current",
                "message": "ESXi iSCSI datastore validation completed with read-only ESXi checks.",
                "next_safe_action": "Resolve NetApp iSCSI object and ESXi login/session blockers before designing the guarded VMFS mount lane.",
                "iscsi_plan": {
                    "datastore_name": "netapp_iscsi_ds01",
                    "preferred_iscsi_lif": "192.168.1.240",
                },
                "netapp_validation": {"status": "ready", "blockers": []},
                "current_state": {
                    "checked": True,
                    "adapter_count": 1,
                    "iscsi_path_count": 0,
                    "datastore_visible": False,
                },
                "blockers": [
                    "ESXi does not show an active iSCSI session to the NetApp target IQN.",
                    "ESXi VMFS datastore `netapp_iscsi_ds01` is not visible.",
                ],
                "warnings": [
                    "Read-only only. No ESXi iSCSI login, target add, adapter rescan, VMFS creation, datastore mount, or vCenter registration was attempted."
                ],
            }
        ),
        encoding="utf-8",
    )

    payload = get_lab_validation_summary(write_report=False)
    items = {item["id"]: item for item in payload["validation_items"]}
    iscsi = items["esxi-iscsi-datastore"]

    assert iscsi["status"] == "blocked"
    assert "NetApp ready" in iscsi["current_state"]
    assert "iSCSI paths 0" in iscsi["current_state"]
    assert len(iscsi["blockers"]) == 2
    assert any(link["component_id"] == "esxi-iscsi-datastore" for link in payload["proof_links"])


def test_lab_validation_marks_esxi_iscsi_not_in_scope_for_nfs_profile(
    monkeypatch,
    tmp_path,
) -> None:
    _enable_high_storage_profile(
        monkeypatch,
        tmp_path,
        features={"netapp_enabled": True, "vcenter_enabled": True, "storage_protocol": "nfs"},
    )

    payload = get_lab_validation_summary(write_report=False)
    items = {item["id"]: item for item in payload["validation_items"]}

    assert items["esxi-iscsi-datastore"]["status"] == "not_in_scope"
    assert "Active storage protocol is `nfs`" in items["esxi-iscsi-datastore"]["desired_state"]


def test_netapp_nfs_validation_item_uses_direct_nfs_artifact(monkeypatch, tmp_path) -> None:
    _patch_lab_validation_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(
        lab_validation,
        "settings",
        _vcenter_netapp_settings(vcenter_configured=False, vcenter_host=None, vcenter_management_ip=None),
    )
    run_dir = tmp_path / "artifacts" / "codex-runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "netapp-nfs-setup-validation-report.md").write_text("# NFS validation\n", encoding="utf-8")
    (run_dir / "netapp-nfs-setup-validation-redacted.json").write_text(
        json.dumps(
            {
                "status": "ready",
                "checked_at": "2026-07-01T00:40:14+00:00",
                "source_type": "live_probe",
                "freshness": "current",
                "message": "NetApp NFS setup validation completed with read-only checks.",
                "next_safe_action": "Mount the NFS datastore on ESXi with the guarded datastore lane.",
                "readiness": {"status": "ready"},
                "live_nfs": {
                    "status": "ready",
                    "checks": {
                        "nfs_service_records": 1,
                        "planned_nfs_lifs_2049": [
                            {"host": "192.168.1.230", "reachable": True},
                            {"host": "192.168.1.231", "reachable": True},
                        ],
                    },
                },
                "blockers": [],
                "warnings": ["vCenter is disabled by the active lab profile; direct NetApp NFS readiness can still be validated."],
            }
        ),
        encoding="utf-8",
    )

    item = lab_validation._netapp_nfs_item(
        {"configured": True},
        {"netapp.nfs-setup-validate": {"action_id": "netapp.nfs-setup-validate", "label": "Validate NFS", "stage": "netapp"}},
        profile_context={"enabled_features": {"netapp_enabled": True, "vcenter_enabled": False, "storage_protocol": "nfs"}},
    )

    assert item["status"] == "ready"
    assert item["source_type"] == "live_probe"
    assert item["freshness"] == "current"
    assert item["recheck_command"] == "make provider-lab-netapp-nfs-setup-validate"
    assert item["linked_workflow_action"]["action_id"] == "netapp.nfs-setup-validate"
    assert any("192.168.1.230, 192.168.1.231" in point for point in item["proof_points"])


def test_esxi_validation_item_uses_live_management_artifact(monkeypatch, tmp_path) -> None:
    _patch_lab_validation_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(lab_validation, "settings", _vcenter_netapp_settings(esxi_test_username="root", esxi_test_password="secret"))
    run_dir = tmp_path / "artifacts" / "codex-runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "esxi-management-readiness-report.md").write_text("# ESXi management\n", encoding="utf-8")
    (run_dir / "esxi-management-readiness-redacted.json").write_text(
        json.dumps(
            {
                "provider_id": "esxi-readonly",
                "status": "ok",
                "checked_at": "2026-07-01T01:05:00+00:00",
                "source_type": "live_probe",
                "freshness": "current",
                "message": "Read-only ESXi probe completed.",
                "https_reachability": {"reachable": True},
                "ssh_reachability": {"reachable": True},
                "vim_service_versions": {"available": True, "versions": ["8.0.3.0"]},
                "blockers": [],
                "warnings": ["ESXi credentials are configured, but no host changes were attempted."],
            }
        ),
        encoding="utf-8",
    )

    item = lab_validation._esxi_item(
        {"esxi.management-validation": {"action_id": "esxi.management-validation", "label": "Validate Management", "stage": "esxi"}},
        profile_context={"resolved_address_plan": {"esxi_management": "192.168.1.203"}},
    )

    assert item["status"] == "ready"
    assert item["source_type"] == "live_probe"
    assert item["freshness"] == "current"
    assert item["linked_workflow_action"]["action_id"] == "esxi.management-validation"
    assert item["recheck_command"] == "make provider-lab-esxi-management-validation"
    assert any("HTTPS reachable: True" in point for point in item["proof_points"])


def test_ilo_validation_item_uses_live_reachability_artifact(monkeypatch, tmp_path) -> None:
    _patch_lab_validation_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(lab_validation, "settings", _vcenter_netapp_settings(ilo_test_host="192.168.1.201", ilo_test_username="admin", ilo_test_password="secret"))
    run_dir = tmp_path / "artifacts" / "codex-runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "ilo-real-run-report.md").write_text("# iLO reachability\n", encoding="utf-8")
    (run_dir / "ilo-real-run-redacted.json").write_text(
        json.dumps(
            {
                "provider_id": "ilo-redfish",
                "status": "ok",
                "checked_at": "2026-07-01T01:10:00+00:00",
                "source_type": "live_probe",
                "freshness": "current",
                "message": "Read-only Redfish probe completed.",
                "endpoint_detection": {
                    "classification": "redfish_available",
                    "redfish_status": "available",
                    "legacy_status": "available",
                },
                "legacy_identity": {"model": "ProLiant DL360 Gen10", "ilo_generation": "ilo5"},
                "warnings": [],
            }
        ),
        encoding="utf-8",
    )

    item = lab_validation._ilo_item(
        {"ilo.reachability": {"action_id": "ilo.reachability", "label": "Reachability", "stage": "ilo"}},
    )

    assert item["status"] == "ready"
    assert item["source_type"] == "live_probe"
    assert item["freshness"] == "current"
    assert item["linked_workflow_action"]["action_id"] == "ilo.reachability"
    assert any("Redfish status: available" in point for point in item["proof_points"])


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
    monkeypatch.setattr(lab_validation, "_existing", lambda values: values)
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
                    "evidence_artifacts": ["artifacts/codex-runs/firmware-compliance-report.md"],
                },
                {
                    "device_label": "HPE Server",
                    "component_label": "HPE BIOS",
                    "current_version": "U32 v3.30",
                    "target_version": None,
                    "path_status": "manual_review",
                    "package_name": None,
                    "disabled_reason": "Manual review required: missing target baseline.",
                    "evidence_artifacts": [
                        "artifacts/codex-runs/hpe-bios-baseline.md",
                        "artifacts/codex-runs/hpe-bios-baseline.md",
                    ],
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
    assert item["evidence_artifacts"].count("artifacts/codex-runs/firmware-compliance-report.md") == 1
    assert item["evidence_artifacts"].count("artifacts/codex-runs/hpe-bios-baseline.md") == 1
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


def _enable_high_storage_profile(monkeypatch, tmp_path: Path, *, features: dict[str, object] | None = None) -> None:
    monkeypatch.setenv("LAB_PROFILE_STORE", str(tmp_path / "lab-profiles.json"))
    create_lab_profile(
        {
            "name": "High Storage Lab",
            "subnet_cidr": "192.168.1.0/24",
            "features": features or {"netapp_enabled": True, "vcenter_enabled": True},
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
