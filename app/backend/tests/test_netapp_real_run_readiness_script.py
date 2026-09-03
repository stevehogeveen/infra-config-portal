from __future__ import annotations

import json
from pathlib import Path

from scripts import netapp_real_run_readiness as script


def test_netapp_real_run_readiness_writes_reports_atomically(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(script, "REPORT_DIR", tmp_path)
    payload = {
        "checked_at": "2026-06-25T00:00:00+00:00",
        "provider_mode": "local-readonly",
        "safe_real_run_scope": "netapp-readiness-only",
        "safety": {
            "netapp_configured": False,
            "local_readonly_ack": True,
            "apply_enabled": False,
            "probe_enabled": False,
            "upgrade_enabled": False,
        },
        "setup_readiness": {"status": "blocked"},
        "upgrade_readiness": {"status": "blocked"},
        "comparison_counts": {"matched": 0, "unknown": 1, "warning": 0, "blocker": 1},
        "operator_steps": ["Review readiness."],
        "not_attempted": ["ONTAP API discovery"],
        "console_blockers": ["Console not checked."],
        "comparison_blockers": [],
        "upgrade_blockers": [],
    }

    script._write_report(payload)

    json_reports = list(tmp_path.glob("netapp-readiness-*.json"))
    markdown_reports = list(tmp_path.glob("netapp-readiness-*.md"))
    assert len(json_reports) == 1
    assert len(markdown_reports) == 1
    assert json.loads(json_reports[0].read_text(encoding="utf-8"))["provider_mode"] == "local-readonly"
    assert markdown_reports[0].read_text(encoding="utf-8").strip()
    assert not list(tmp_path.glob("*.tmp"))


def test_netapp_file_mode_self_heals_stat_errors(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / ".env.local.real-lab"
    target.write_text("NETAPP_CONFIGURED=false\n", encoding="utf-8")
    original_stat = Path.stat

    def flaky_stat(self: Path, *args, **kwargs):  # noqa: ANN001, ANN202
        if self == target:
            raise OSError("stat failed")
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky_stat)

    assert script._file_mode(target) is None


def test_netapp_env_file_summary_self_heals_exists_errors(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / ".env.local.real-lab"
    monkeypatch.setattr(script, "REAL_LAB_ENV", target)
    original_exists = Path.exists

    def flaky_exists(self: Path) -> bool:
        if self == target:
            raise OSError("path unavailable")
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    assert script._env_file_summary() == {
        "path": ".env.local.real-lab",
        "exists": False,
        "mode": None,
    }
