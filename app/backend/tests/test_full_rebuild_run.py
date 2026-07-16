from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from app.services import full_rebuild_run


def test_summary_target_is_report_only(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)

    def fail_run(*args, **kwargs):  # noqa: ANN002, ANN003
        cmd = args[0] if args else kwargs.get("args", [])
        if cmd[:1] == ["git"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        raise AssertionError("summary generation must not call live subprocess stages")

    monkeypatch.setattr(full_rebuild_run.subprocess, "run", fail_run)

    result = full_rebuild_run.build_full_rebuild_summary_reports()

    assert result["status"] == "summary_only"
    assert result["blockers"] == []
    assert result["source_type"] == "historical_artifact"
    assert result["is_current"] is False
    saved = json.loads(full_rebuild_run.SUMMARY_JSON.read_text(encoding="utf-8"))
    assert saved["status"] == "summary_only"
    generated_reports = [
        full_rebuild_run.BASELINE_REPORT,
        full_rebuild_run.CISCO_BOOTSTRAP_REPORT,
        full_rebuild_run.HPE_ILO_REPORT,
        full_rebuild_run.HPE_RAID_REPORT,
        full_rebuild_run.ESXI_BOOT_REPORT,
        full_rebuild_run.FINAL_REPORT,
    ]
    for report_path in generated_reports:
        assert report_path.read_text(encoding="utf-8").strip()
    assert not list(tmp_path.glob("*.tmp"))


def test_real_full_rebuild_invokes_live_stages(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    monkeypatch.delenv("PYTHON", raising=False)
    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        if cmd[:1] == ["git"]:
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout='{"status":"completed","blockers":[],"warnings":[]}\n',
            stderr="",
        )

    monkeypatch.setattr(full_rebuild_run.subprocess, "run", fake_run)
    monkeypatch.setattr(full_rebuild_run, "REAL_LAB_ENV", Path("/does/not/exist"))

    result = full_rebuild_run.run_full_rebuild_execution()

    command_text = [" ".join(call) for call in calls]
    assert result["status"] == "completed"
    assert all(call[0] == sys.executable for call in calls if call[:1] != ["git"])
    assert any("scripts/cisco_real_lab_workflow.py --apply" in command for command in command_text)
    assert any("scripts/ilo_real_reachability.py" in command for command in command_text)
    assert any("scripts/hpe_raid_workflow.py discovery" in command for command in command_text)
    assert any("scripts/esxi_boot_workflow.py insert-virtual-media" in command for command in command_text)
    assert not any("automated Codex" in blocker for blocker in result["blockers"])
    saved = json.loads(full_rebuild_run.EXECUTION_SUMMARY_JSON.read_text(encoding="utf-8"))
    assert saved["status"] == "completed"
    assert not list(tmp_path.glob("*.tmp"))


def test_live_stage_dedupes_parsed_blockers_and_warnings(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("PYTHON", raising=False)
    monkeypatch.setenv("FULL_REBUILD_STAGE_TIMEOUT_SECONDS", "not-a-number")
    timeouts: list[int] = []

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        timeouts.append(kwargs["timeout"])
        return subprocess.CompletedProcess(
            cmd,
            1,
            stdout=json.dumps(
                {
                    "status": "blocked",
                    "message": "blocked with repeated evidence",
                    "blockers": ["missing iso", "bad ip", "missing iso"],
                    "warnings": ["retry later", "retry later", "manual check"],
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(full_rebuild_run.subprocess, "run", fake_run)
    monkeypatch.setattr(full_rebuild_run, "REAL_LAB_ENV", Path("/does/not/exist"))

    result = full_rebuild_run._run_live_stage(["scripts/example.py"], tmp_path / "example.md")

    assert result["blockers"] == ["missing iso", "bad ip"]
    assert result["warnings"] == ["retry later", "manual check"]
    assert timeouts == [1800]


def test_live_stage_keeps_scalar_blocker_and_warning_whole(monkeypatch, tmp_path: Path) -> None:
    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            cmd,
            1,
            stdout=json.dumps(
                {
                    "status": "blocked",
                    "blockers": "missing iso",
                    "warnings": "retry later",
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(full_rebuild_run.subprocess, "run", fake_run)
    monkeypatch.setattr(full_rebuild_run, "REAL_LAB_ENV", Path("/does/not/exist"))

    result = full_rebuild_run._run_live_stage(["scripts/example.py"], tmp_path / "example.md")

    assert result["blockers"] == ["missing iso"]
    assert result["warnings"] == ["retry later"]


def test_live_stage_timeout_preserves_safe_output_tail(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("FULL_REBUILD_STAGE_TIMEOUT_SECONDS", "2")

    def fake_run(cmd: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd, 2, output=b"ready-\xff", stderr=None)

    monkeypatch.setattr(full_rebuild_run.subprocess, "run", fake_run)

    result = full_rebuild_run._run_live_stage(["scripts/example.py"], tmp_path / "example.md")

    assert result["status"] == "blocked"
    assert result["returncode"] == 124
    assert result["summary"] == {"stdout_tail": "ready-\ufffd", "stderr_tail": ""}


def test_combined_stage_dedupes_blockers_and_warnings() -> None:
    result = full_rebuild_run._combined_stage(
        "combined",
        [
            {"status": "blocked", "blockers": ["missing iso", "bad ip"], "warnings": ["retry later"]},
            {"status": "blocked", "blockers": ["missing iso", "no console"], "warnings": ["retry later", "manual check"]},
        ],
    )

    assert result["status"] == "blocked"
    assert result["blockers"] == ["missing iso", "bad ip", "no console"]
    assert result["warnings"] == ["retry later", "manual check"]


def test_combined_stage_keeps_scalar_blockers_and_warnings_whole() -> None:
    result = full_rebuild_run._combined_stage(
        "combined",
        [
            {"status": "blocked", "blockers": "missing iso", "warnings": "retry later"},
            {"status": "blocked", "blockers": ["missing iso", "bad ip"], "warnings": ["retry later"]},
        ],
    )

    assert result["status"] == "blocked"
    assert result["blockers"] == ["missing iso", "bad ip"]
    assert result["warnings"] == ["retry later"]


def test_get_full_rebuild_summary_self_heals_corrupt_cache(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
    full_rebuild_run.SUMMARY_JSON.write_text("[not an object]", encoding="utf-8")

    result = full_rebuild_run.get_full_rebuild_summary()

    assert result["status"] == "not_run"
    assert result["source_type"] == "not_checked"


def test_report_summary_self_heals_disappearing_report(monkeypatch, tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    report.write_text("# Report\n\nstatus: ready\n", encoding="utf-8")
    original_stat = Path.stat

    def flaky_stat(self: Path, *args: Any, **kwargs: Any):  # noqa: ANN401
        if self == report:
            raise FileNotFoundError("report disappeared")
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky_stat)

    summary = full_rebuild_run._report_summary(report)

    assert summary == {"status": "missing", "path": str(report)}


def test_report_summary_self_heals_exists_probe_errors(monkeypatch, tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    original_exists = Path.exists

    def flaky_exists(self: Path) -> bool:
        if self == report:
            raise OSError("report path unavailable")
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    summary = full_rebuild_run._report_summary(report)

    assert summary == {"status": "missing", "path": str(report)}


def test_report_summary_replaces_bad_encoding(tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    report.write_bytes(b"# Report\n\n- status: ready\xff\n")

    summary = full_rebuild_run._report_summary(report)

    assert summary["status"] == "present"
    assert summary["path"] == str(report)
    assert summary["extract"] == "# Report\n- status: ready\ufffd"


def test_report_blockers_self_heals_unreadable_report(monkeypatch, tmp_path: Path) -> None:
    report = tmp_path / "report.md"
    report.write_text("## Blockers\n\n- missing iso\n", encoding="utf-8")
    original_read_text = Path.read_text

    def flaky_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if self == report:
            raise OSError("report cannot be read")
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", flaky_read_text)

    assert full_rebuild_run._report_blockers(report) == []


def test_execution_warnings_self_heals_env_probe_errors(monkeypatch, tmp_path: Path) -> None:
    env_path = tmp_path / ".env.local.real-lab"
    monkeypatch.setattr(full_rebuild_run, "REAL_LAB_ENV", env_path)
    original_exists = Path.exists

    def flaky_exists(self: Path) -> bool:
        if self == env_path:
            raise OSError("env path unavailable")
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    warnings = full_rebuild_run._execution_warnings()

    assert any(".env.local.real-lab was not found" in warning for warning in warnings)


def test_cisco_privilege_stage_self_heals_report_probe_errors(monkeypatch, tmp_path: Path) -> None:
    report = tmp_path / "cisco-privilege.md"
    monkeypatch.setattr(full_rebuild_run, "CISCO_PRIVILEGE_REPORT", report)
    original_exists = Path.exists

    def flaky_exists(self: Path) -> bool:
        if self == report:
            raise OSError("report path unavailable")
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    stage = full_rebuild_run._cisco_privilege_stage({"cisco_privilege": {"extract": ""}})

    assert stage["status"] == "blocked"
    assert "Cisco privilege report is missing." in stage["blockers"]


def _redirect_reports(monkeypatch, tmp_path: Path) -> None:
    paths = {
        "BASELINE_REPORT": tmp_path / "baseline.md",
        "CISCO_PRIVILEGE_REPORT": tmp_path / "cisco-privilege.md",
        "CISCO_BOOTSTRAP_REPORT": tmp_path / "cisco-bootstrap.md",
        "HPE_ILO_REPORT": tmp_path / "hpe-ilo.md",
        "HPE_RAID_REPORT": tmp_path / "hpe-raid.md",
        "ESXI_BOOT_REPORT": tmp_path / "esxi-boot.md",
        "FINAL_REPORT": tmp_path / "final.md",
        "SUMMARY_JSON": tmp_path / "summary.json",
        "EXECUTION_SUMMARY_JSON": tmp_path / "execution.json",
    }
    for name, path in paths.items():
        monkeypatch.setattr(full_rebuild_run, name, path)
    monkeypatch.setattr(
        full_rebuild_run,
        "REQUESTED_REPORTS",
        {
            "baseline": paths["BASELINE_REPORT"],
            "cisco_privilege": paths["CISCO_PRIVILEGE_REPORT"],
            "cisco_bootstrap": paths["CISCO_BOOTSTRAP_REPORT"],
            "hpe_ilo": paths["HPE_ILO_REPORT"],
            "hpe_raid": paths["HPE_RAID_REPORT"],
            "esxi_boot": paths["ESXI_BOOT_REPORT"],
            "final": paths["FINAL_REPORT"],
        },
    )
    monkeypatch.setattr(
        full_rebuild_run,
        "SOURCE_REPORTS",
        {
            "cisco_console": tmp_path / "cisco-console.md",
            "cisco_privilege": tmp_path / "cisco-privilege-source.md",
            "cisco_bootstrap_apply": tmp_path / "cisco-bootstrap-apply.md",
            "ilo_reachability": tmp_path / "ilo-reachability.md",
            "raid_discovery": tmp_path / "raid-discovery.md",
            "raid_plan": tmp_path / "raid-plan.md",
            "raid_pending": tmp_path / "raid-pending.md",
            "raid_validate_after_reset": tmp_path / "raid-validate.md",
            "esxi_readiness": tmp_path / "esxi-readiness.md",
            "esxi_media": tmp_path / "esxi-media.md",
            "esxi_virtual_media": tmp_path / "esxi-virtual-media.md",
            "esxi_one_time_boot": tmp_path / "esxi-one-time-boot.md",
            "esxi_installer_boot": tmp_path / "esxi-installer-boot.md",
        },
    )
