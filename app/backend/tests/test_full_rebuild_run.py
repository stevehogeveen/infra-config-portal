from __future__ import annotations

import subprocess
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
    assert result["mock_results_used"] is False


def test_real_full_rebuild_invokes_live_stages(monkeypatch, tmp_path: Path) -> None:
    _redirect_reports(monkeypatch, tmp_path)
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
    assert any("scripts/cisco_real_lab_workflow.py --apply" in command for command in command_text)
    assert any("scripts/ilo_real_reachability.py" in command for command in command_text)
    assert any("scripts/hpe_raid_workflow.py discovery" in command for command in command_text)
    assert any("scripts/esxi_boot_workflow.py insert-virtual-media" in command for command in command_text)
    assert not any("automated Codex" in blocker for blocker in result["blockers"])


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
