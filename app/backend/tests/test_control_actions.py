from __future__ import annotations

from types import SimpleNamespace

from app.providers.action_policy import ActionCategory
from app.providers.base import ProviderStatus
from app.services import control_actions


def test_action_read_dedupes_blockers_and_diagnostics() -> None:
    class DuplicatePolicy:
        def action_blockers(self, action_id: str, category: ActionCategory) -> list[str]:
            assert action_id == "example.write"
            return ["policy blocker", "provider blocker", "policy blocker"]

    action = control_actions.ActionDefinition(
        id="example.action",
        label="Example",
        section_id="ilo",
        device_stage="Example",
        description="Example action",
        classification="write",
        provider_ids=("example-provider",),
        policy_action_id="example.write",
        policy_category=ActionCategory.APP_STATE_WRITE,
        diagnostics=("diagnostic", "diagnostic"),
    )
    provider = ProviderStatus(
        id="example-provider",
        name="Example Provider",
        kind="example",
        mode="local-readonly",
        status="blocked",
        capabilities=[],
        message="provider blocked",
        blockers=["provider blocker", "provider blocker", "second provider blocker"],
    )

    result = control_actions._action_read(
        action,
        {"example-provider": provider},
        DuplicatePolicy(),
        {"features": {}},
    )

    assert result["blocker"] == "provider blocker; second provider blocker; policy blocker"
    assert result["diagnostics"] == ["diagnostic"]


def test_action_read_keeps_scalar_provider_and_policy_blockers_whole() -> None:
    class ScalarPolicy:
        def action_blockers(self, action_id: str, category: ActionCategory) -> str:
            assert action_id == "example.write"
            return " policy blocker "

    action = control_actions.ActionDefinition(
        id="example.action",
        label="Example",
        section_id="ilo",
        device_stage="Example",
        description="Example action",
        classification="write",
        provider_ids=("example-provider",),
        policy_action_id="example.write",
        policy_category=ActionCategory.APP_STATE_WRITE,
    )
    provider = SimpleNamespace(
        id="example-provider",
        status="blocked",
        message="provider message",
        blockers=" provider blocker ",
    )

    result = control_actions._action_read(
        action,
        {"example-provider": provider},
        ScalarPolicy(),
        {"features": {}},
    )

    assert result["blocker"] == "provider blocker; policy blocker"
    assert not any(part == "p" for part in result["blocker"].split("; "))


def test_action_read_keeps_scalar_nonblocking_provider_diagnostic_whole() -> None:
    class EmptyPolicy:
        def action_blockers(self, action_id: str, category: ActionCategory) -> list[str]:
            return []

    action = control_actions.ActionDefinition(
        id="netapp.inspect",
        label="NetApp Inspect",
        section_id="netapp",
        device_stage="NetApp",
        description="Read-only NetApp action",
        classification="read-only",
        provider_ids=("netapp-ontap",),
    )
    provider = SimpleNamespace(
        id="netapp-ontap",
        status="blocked",
        message="netapp offline",
        blockers=" netapp offline ",
    )

    result = control_actions._action_read(
        action,
        {"netapp-ontap": provider},
        EmptyPolicy(),
        {"features": {}},
    )

    assert result["blocker"] is None
    assert "netapp offline" in result["diagnostics"]
    assert "n" not in result["diagnostics"]


def test_control_profile_list_setting_honors_explicit_empty_values() -> None:
    active = {
        "_field_presence": {"global_settings": ["dns_servers"], "top_level": []},
        "dns": ["192.168.1.1"],
    }

    values, explicit = control_actions._control_profile_list_setting(
        active,
        {"dns_servers": []},
        "dns_servers",
        "dns",
    )

    assert values == []
    assert explicit is True


def test_control_profile_list_setting_inherits_absent_values() -> None:
    active = {
        "_field_presence": {"global_settings": [], "top_level": []},
        "dns": [],
    }

    values, explicit = control_actions._control_profile_list_setting(
        active,
        {"dns_servers": ["192.168.1.10"]},
        "dns_servers",
        "dns",
    )

    assert values == ["192.168.1.10"]
    assert explicit is False


def test_report_status_self_heals_locked_report_path(monkeypatch) -> None:
    class ReportPath:
        def exists(self) -> bool:
            raise OSError("locked")

    class RepoRoot:
        def __truediv__(self, path: str) -> ReportPath:
            return ReportPath()

    monkeypatch.setattr(control_actions, "REPO_ROOT", RepoRoot())

    assert control_actions._report_status("artifacts/locked-report.md") == "not_run"


def test_action_read_self_heals_disappearing_report_timestamp(monkeypatch) -> None:
    class ReportPath:
        def exists(self) -> bool:
            return True

        def stat(self) -> SimpleNamespace:
            raise FileNotFoundError("gone")

    class RepoRoot:
        def __truediv__(self, path: str) -> ReportPath:
            return ReportPath()

    class EmptyPolicy:
        def action_blockers(self, action_id: str, category: ActionCategory) -> list[str]:
            return []

    action = control_actions.ActionDefinition(
        id="example.action",
        label="Example",
        section_id="ilo",
        device_stage="Example",
        description="Example action",
        classification="read-only",
        report="artifacts/disappeared-report.md",
    )
    monkeypatch.setattr(control_actions, "REPO_ROOT", RepoRoot())

    result = control_actions._action_read(action, {}, EmptyPolicy(), {"features": {}})

    assert result["last_run_status"] == "report_available"
    assert result["last_run_at"] is None
    assert result["last_report"] == "artifacts/disappeared-report.md"


def test_firmware_rollup_dedupes_intermediate_versions_and_prechecks() -> None:
    result = control_actions._firmware_summary_for_section(
        "firmware-upgrade",
        {
            "ilo": {
                "required_intermediate_versions": ["1.0", "2.0"],
                "prechecks_required": ["backup", "maintenance window"],
            },
            "cisco": {
                "required_intermediate_versions": ["1.0", "3.0"],
                "prechecks_required": ["backup", "console access"],
            },
        },
    )

    assert result is not None
    assert result["required_intermediate_versions"] == ["1.0", "2.0", "3.0"]
    assert result["prechecks_required"] == ["backup", "maintenance window", "console access"]
