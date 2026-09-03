from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from scripts import ilo_real_reachability as script


def test_ilo_real_reachability_writes_reports_atomically(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(script, "REPORT_DIR", tmp_path)
    payload = {
        "checked_at": "2026-06-25T00:00:00+00:00",
        "provider_mode": "local-lab-readwrite",
        "classification": "redfish_root_available",
        "next_action": "Proceed to iLO authentication and inventory.",
        "target": {
            "host_configured": True,
            "host_source": "test",
            "fallback_hosts_configured": 0,
            "target_candidate_count": 1,
            "username_configured": True,
            "password_configured": True,
            "tls_verify": False,
        },
        "selected_target_source": "test",
        "diagnostics": {
            "dns": {"status": "ok"},
            "tcp": {"status": "ok", "reachable": True},
            "http": {"status": "ok"},
        },
        "candidate_attempts": [
            {
                "candidate_index": 1,
                "target_source": "test",
                "classification": "redfish_root_available",
                "tcp_reachable": True,
            }
        ],
        "blockers": [],
    }

    script._write_report(payload)
    capsys.readouterr()

    json_reports = list(tmp_path.glob("ilo-reachability-*.json"))
    markdown_reports = list(tmp_path.glob("ilo-reachability-*.md"))
    assert len(json_reports) == 1
    assert len(markdown_reports) == 1
    assert json.loads(json_reports[0].read_text(encoding="utf-8"))["classification"] == "redfish_root_available"
    assert markdown_reports[0].read_text(encoding="utf-8").strip()
    assert not list(tmp_path.glob("*.tmp"))


def test_ilo_gate_blockers_dedupes_preserving_order(monkeypatch) -> None:
    class FakeConfig:
        missing_fields = ["host", "host"]

    class FakePolicy:
        def readonly_blockers(self) -> list[str]:
            return ["ack missing", "ack missing"]

    monkeypatch.setattr(script, "settings", SimpleNamespace(provider_mode="wrong-mode"))

    blockers = script._gate_blockers(FakeConfig(), FakePolicy())

    assert blockers == [
        "PROVIDER_MODE=local-lab-readwrite is required for real iLO reachability.",
        "ack missing",
        "Missing local iLO configuration: host, host.",
    ]


def test_ilo_file_mode_self_heals_probe_errors(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / ".env.local.real-lab"
    original_exists = Path.exists

    def flaky_exists(self: Path) -> bool:
        if self == target:
            raise OSError("path unavailable")
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    assert script._file_mode(target) is None


def test_ilo_env_file_summary_self_heals_exists_errors(monkeypatch, tmp_path: Path) -> None:
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
