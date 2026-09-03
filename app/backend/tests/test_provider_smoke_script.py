from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts import provider_smoke as script


def test_provider_smoke_file_mode_self_heals_probe_errors(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / ".env.local.real-lab"
    original_exists = Path.exists

    def flaky_exists(self: Path) -> bool:
        if self == target:
            raise OSError("path unavailable")
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    assert script._file_mode(target) is None


def test_provider_smoke_preflight_self_heals_env_path_probe_errors(monkeypatch, tmp_path: Path) -> None:
    target = tmp_path / ".env.local.real-lab"
    monkeypatch.setattr(script, "REAL_LAB_ENV", target)
    monkeypatch.setattr(script, "_required_env_summary", lambda _provider_ids=None: [])
    monkeypatch.setattr(script, "_tool_availability", lambda _provider_ids=None: {})
    monkeypatch.setattr(script, "_target_summary", lambda _provider_ids=None: {})
    monkeypatch.setattr(script, "_tcp_preflight", lambda _provider_ids=None: {})
    original_exists = Path.exists

    def flaky_exists(self: Path) -> bool:
        if self == target:
            raise OSError("path unavailable")
        return original_exists(self)

    monkeypatch.setattr(Path, "exists", flaky_exists)

    summary = script._preflight_summary(["ilo-redfish"])

    assert summary["env_file"]["exists"] is False
    assert summary["env_file"]["mode"] is None


def test_provider_smoke_serial_candidates_self_heal_glob_errors(monkeypatch) -> None:
    original_exists = Path.exists
    original_glob = Path.glob

    def flaky_exists(self: Path) -> bool:
        if self == Path("/dev/serial/by-id"):
            raise OSError("serial path unavailable")
        return original_exists(self)

    def flaky_glob(self: Path, pattern: str):  # noqa: ANN202
        if self == Path("/dev"):
            raise OSError("serial glob failed")
        return original_glob(self, pattern)

    monkeypatch.setattr(Path, "exists", flaky_exists)
    monkeypatch.setattr(Path, "glob", flaky_glob)

    summary = script._serial_candidate_summary()

    assert summary["stable_by_id_count"] == 0
    assert summary["ttyUSB_count"] == 0
    assert summary["ttyACM_count"] == 0


def test_provider_smoke_markdown_keeps_scalar_probe_blockers_and_warnings_whole() -> None:
    report = {
        "checked_at": "2026-06-26T00:00:00+00:00",
        "provider_mode": "local-readonly",
        "preflight": {},
        "guarded_rebuild_planning": {},
        "provider_status": [],
        "probes": [
            {
                "provider_id": "cisco-ansible",
                "status": "blocked",
                "message": "blocked",
                "ssh_reachability": {},
                "tool_availability": {},
                "blockers": "ssh unavailable",
                "warnings": "retry later",
            }
        ],
    }

    markdown = script._markdown_report(report)

    assert "  - blocker: ssh unavailable" in markdown
    assert "  - warning: retry later" in markdown
    assert "  - blocker: s\n" not in markdown
    assert "  - warning: r\n" not in markdown


def test_provider_smoke_next_action_keeps_scalar_provider_blocker_whole() -> None:
    provider = {"id": "cisco-ansible", "status": "blocked", "blockers": "ssh unavailable"}

    assert script._provider_next_action(provider) == "ssh unavailable"


def test_provider_smoke_env_flag_accepts_common_true_values(monkeypatch) -> None:
    monkeypatch.setenv("PROVIDER_SMOKE_REQUIRE_REAL", "YES")

    assert script._env_flag("PROVIDER_SMOKE_REQUIRE_REAL") is True


def test_provider_smoke_env_flag_can_default_to_true(monkeypatch) -> None:
    monkeypatch.delenv("PROVIDER_SMOKE_REQUIRE_REAL", raising=False)

    assert script._env_flag("PROVIDER_SMOKE_REQUIRE_REAL", default=True) is True


def test_provider_smoke_env_flag_false_overrides_default_true(monkeypatch) -> None:
    monkeypatch.setenv("PROVIDER_SMOKE_REQUIRE_REAL", "false")

    assert script._env_flag("PROVIDER_SMOKE_REQUIRE_REAL", default=True) is False


def test_provider_smoke_require_real_mode_fails_before_mock_probe(monkeypatch) -> None:
    written: list[dict] = []

    monkeypatch.setenv("PROVIDER_SMOKE_REQUIRE_REAL", "true")
    monkeypatch.setattr(script, "settings", SimpleNamespace(provider_mode="mock"))
    monkeypatch.setattr(script, "_selected_provider_ids", lambda: ["cisco-ansible"])
    monkeypatch.setattr(script, "_preflight_summary", lambda _provider_ids=None: {})
    monkeypatch.setattr(script, "_guarded_rebuild_planning", lambda: {})
    monkeypatch.setattr(script, "_redaction_values", lambda: [])
    monkeypatch.setattr(script, "_write_report", lambda report: written.append(report))

    assert script.main() == 2
    assert written[0]["quality_gate"]["status"] == "failed"
    assert written[0]["probes"] == []
