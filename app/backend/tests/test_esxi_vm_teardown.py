from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app.core.config import settings
from app.services import esxi_vm_teardown
from app.services.guarded_action_context import GuardedActionContext

VM_NAME = "single-server-smoke-vm"
ESXI_TARGET = "esxi.test.invalid"


class _AllowReadonlyPolicy:
    def readonly_blockers(self):
        return []

    def action_blockers(self, _action_id, _category):
        return []


class FakeGovc:
    def __init__(
        self,
        *,
        power_state: str | None = "poweredOn",
        api_type: str = "HostAgent",
        fail_power_off: bool = False,
        keep_powered_on: bool = False,
        fail_destroy: bool = False,
        fail_post_destroy_query: bool = False,
        ambiguous: bool = False,
    ) -> None:
        self.power_state = power_state
        self.api_type = api_type
        self.fail_power_off = fail_power_off
        self.keep_powered_on = keep_powered_on
        self.fail_destroy = fail_destroy
        self.fail_post_destroy_query = fail_post_destroy_query
        self.ambiguous = ambiguous
        self.destroy_attempted = False
        self.calls: list[list[str]] = []

    def __call__(self, args, *, env, timeout):
        assert env["GOVC_URL"] == f"https://{ESXI_TARGET}/sdk"
        assert env["GOVC_USERNAME"] == "root"
        assert env["GOVC_PASSWORD"] == "test-vm-teardown-password"
        assert timeout in {30, 120}
        self.calls.append(list(args))
        if args == ["about", "-json"]:
            return _about_result(api_type=self.api_type)
        if args == ["vm.info", "-json", VM_NAME]:
            if self.destroy_attempted and self.fail_post_destroy_query:
                return {
                    "return_code": 1,
                    "stdout": "",
                    "stderr": "connection reset after destroy",
                }
            if self.power_state is None:
                return {
                    "return_code": 1,
                    "stdout": "",
                    "stderr": f"Virtual machine {VM_NAME} not found",
                }
            return _vm_info_result(
                power_state=self.power_state,
                ambiguous=self.ambiguous,
            )
        if args == ["vm.power", "-off", VM_NAME]:
            if self.fail_power_off:
                return {
                    "return_code": 1,
                    "stdout": "",
                    "stderr": "power off refused",
                }
            if not self.keep_powered_on:
                self.power_state = "poweredOff"
            return {"return_code": 0, "stdout": "", "stderr": ""}
        if args == ["vm.destroy", VM_NAME]:
            self.destroy_attempted = True
            if self.fail_destroy:
                return {
                    "return_code": 1,
                    "stdout": "",
                    "stderr": "destroy refused",
                }
            self.power_state = None
            return {"return_code": 0, "stdout": "", "stderr": ""}
        raise AssertionError(f"unexpected govc command: {args}")


@pytest.mark.parametrize(
    "vm_name",
    [
        "",
        " ",
        " leading",
        "trailing ",
        "-option-like",
        "../other-vm",
        "folder/vm",
        "vm*",
        "vm\nname",
        "a" * 81,
    ],
)
def test_preview_rejects_unsafe_vm_identifiers_without_executor_calls(
    monkeypatch,
    vm_name,
) -> None:
    _patch_ready_settings(monkeypatch)
    fake = FakeGovc()

    payload = esxi_vm_teardown.build_esxi_vm_teardown_preview(
        vm_name,
        executor=fake,
        write_report=False,
    )

    assert payload["status"] == "blocked"
    assert payload["request"]["valid"] is False
    assert fake.calls == []


def test_preview_is_read_only_and_describes_strict_scope(monkeypatch) -> None:
    _patch_ready_settings(monkeypatch)
    fake = FakeGovc(power_state="poweredOn")

    payload = esxi_vm_teardown.build_esxi_vm_teardown_preview(
        VM_NAME,
        executor=fake,
        write_report=False,
    )

    assert payload["status"] == "preview_ready"
    assert payload["apply_enabled"] is False
    assert payload["freshness"] == "current"
    assert payload["target_binding"]["bound"] is True
    assert payload["target_binding"]["direct_esxi"] is True
    assert payload["target_binding"]["instance_fingerprint"]
    assert payload["vm_evidence"]["exists"] is True
    assert payload["vm_evidence"]["power_state"] == "poweredOn"
    assert fake.calls == [
        ["about", "-json"],
        ["vm.info", "-json", VM_NAME],
    ]
    excluded = payload["teardown_plan"]["explicitly_excluded"]
    assert "datastore remove or wipe" in excluded
    assert "host maintenance, reset, reinstall, or reconfiguration" in excluded
    assert all(call[0] not in {"vm.power", "vm.destroy"} for call in fake.calls)


def test_preview_refuses_vcenter_instead_of_direct_esxi(monkeypatch) -> None:
    _patch_ready_settings(monkeypatch)
    fake = FakeGovc(api_type="VirtualCenter")

    payload = esxi_vm_teardown.build_esxi_vm_teardown_preview(
        VM_NAME,
        executor=fake,
        write_report=False,
    )

    assert payload["status"] == "blocked"
    assert payload["target_binding"]["bound"] is False
    assert any("HostAgent" in blocker for blocker in payload["blockers"])
    assert fake.calls == [["about", "-json"]]


def test_preview_refuses_mismatched_configured_and_govc_targets(monkeypatch) -> None:
    _patch_ready_settings(monkeypatch)
    monkeypatch.setenv("GOVC_URL", "https://different-esxi.test.invalid/sdk")
    fake = FakeGovc()

    payload = esxi_vm_teardown.build_esxi_vm_teardown_preview(
        VM_NAME,
        executor=fake,
        write_report=False,
    )

    assert payload["status"] == "blocked"
    assert payload["target"]["targets_match"] is False
    assert any("unbound target" in blocker for blocker in payload["blockers"])
    assert fake.calls == []


def test_apply_defaults_refuse_before_any_govc_command(monkeypatch) -> None:
    _patch_ready_settings(monkeypatch)
    _clear_apply_gates(monkeypatch)
    fake = FakeGovc()

    payload = esxi_vm_teardown.apply_esxi_vm_teardown(
        VM_NAME,
        executor=fake,
        write_report=False,
    )

    assert payload["status"] == "blocked"
    assert payload["apply_enabled"] is False
    assert payload["apply"]["target_probe_attempted"] is False
    assert payload["apply"]["destroy_attempted"] is False
    assert fake.calls == []
    assert any("VM_TEARDOWN_APPLY=true" in item for item in payload["blockers"])
    assert any("VM_TEARDOWN_ALLOW_DELETE=true" in item for item in payload["blockers"])
    assert any("VM_TEARDOWN_CONFIRM_VM_NAME" in item for item in payload["blockers"])
    assert any("VM_TEARDOWN_CONFIRM_ESXI_TARGET" in item for item in payload["blockers"])


def test_apply_requires_local_lab_readwrite_without_probing(monkeypatch) -> None:
    _patch_ready_settings(monkeypatch, provider_mode="local-readonly")
    _enable_apply_gates(monkeypatch)
    fake = FakeGovc()

    payload = esxi_vm_teardown.apply_esxi_vm_teardown(
        VM_NAME,
        executor=fake,
        write_report=False,
    )

    assert payload["status"] == "blocked"
    assert any("PROVIDER_MODE=local-lab-readwrite" in item for item in payload["blockers"])
    assert fake.calls == []


@pytest.mark.parametrize(
    ("name_confirmation", "target_confirmation", "expected_blocker"),
    [
        (
            "different-vm",
            ESXI_TARGET,
            "VM_TEARDOWN_CONFIRM_VM_NAME",
        ),
        (
            VM_NAME,
            "different-esxi.test.invalid",
            "VM_TEARDOWN_CONFIRM_ESXI_TARGET",
        ),
    ],
)
def test_apply_requires_exact_vm_and_target_confirmations(
    monkeypatch,
    name_confirmation,
    target_confirmation,
    expected_blocker,
) -> None:
    _patch_ready_settings(monkeypatch)
    _enable_apply_gates(
        monkeypatch,
        vm_name=name_confirmation,
        target=target_confirmation,
    )
    fake = FakeGovc()

    payload = esxi_vm_teardown.apply_esxi_vm_teardown(
        VM_NAME,
        executor=fake,
        write_report=False,
    )

    assert payload["status"] == "blocked"
    assert any(expected_blocker in item for item in payload["blockers"])
    assert fake.calls == []


def test_apply_powers_off_proves_state_then_destroys_and_proves_absence(
    monkeypatch,
) -> None:
    _patch_ready_settings(monkeypatch)
    _enable_apply_gates(monkeypatch)
    fake = FakeGovc(power_state="poweredOn")

    payload = esxi_vm_teardown.apply_esxi_vm_teardown(
        VM_NAME,
        executor=fake,
        write_report=False,
    )

    assert payload["status"] == "completed"
    assert payload["apply"]["power_off_attempted"] is True
    assert payload["apply"]["powered_off_proven"] is True
    assert payload["apply"]["destroy_attempted"] is True
    assert payload["apply"]["absence_validation_attempted"] is True
    assert payload["apply"]["absence_confirmed"] is True
    assert payload["vm_evidence"]["absence_confirmed"] is True
    assert fake.calls == [
        ["about", "-json"],
        ["vm.info", "-json", VM_NAME],
        ["vm.power", "-off", VM_NAME],
        ["vm.info", "-json", VM_NAME],
        ["vm.destroy", VM_NAME],
        ["vm.info", "-json", VM_NAME],
    ]
    commands = [entry["command"] for entry in payload["audit"]["operations"]]
    assert commands == [["govc", *call] for call in fake.calls]
    assert not any(command[1].startswith(("datastore.", "host.")) for command in commands)


def test_apply_skips_power_command_only_when_fresh_evidence_is_powered_off(
    monkeypatch,
) -> None:
    _patch_ready_settings(monkeypatch)
    _enable_apply_gates(monkeypatch)
    fake = FakeGovc(power_state="poweredOff")

    payload = esxi_vm_teardown.apply_esxi_vm_teardown(
        VM_NAME,
        executor=fake,
        write_report=False,
    )

    assert payload["status"] == "completed"
    assert payload["apply"]["power_off_attempted"] is False
    assert payload["apply"]["powered_off_proven"] is True
    assert fake.calls == [
        ["about", "-json"],
        ["vm.info", "-json", VM_NAME],
        ["vm.destroy", VM_NAME],
        ["vm.info", "-json", VM_NAME],
    ]


def test_apply_stops_before_destroy_when_power_off_fails(monkeypatch) -> None:
    _patch_ready_settings(monkeypatch)
    _enable_apply_gates(monkeypatch)
    fake = FakeGovc(fail_power_off=True)

    payload = esxi_vm_teardown.apply_esxi_vm_teardown(
        VM_NAME,
        executor=fake,
        write_report=False,
    )

    assert payload["status"] == "failed"
    assert payload["apply"]["power_off_attempted"] is True
    assert payload["apply"]["destroy_attempted"] is False
    assert ["vm.destroy", VM_NAME] not in fake.calls


def test_apply_stops_before_destroy_when_powered_off_state_is_not_proven(
    monkeypatch,
) -> None:
    _patch_ready_settings(monkeypatch)
    _enable_apply_gates(monkeypatch)
    fake = FakeGovc(keep_powered_on=True)

    payload = esxi_vm_teardown.apply_esxi_vm_teardown(
        VM_NAME,
        executor=fake,
        write_report=False,
    )

    assert payload["status"] == "failed"
    assert payload["apply"]["powered_off_proven"] is False
    assert payload["apply"]["destroy_attempted"] is False
    assert fake.calls[-1] == ["vm.info", "-json", VM_NAME]


def test_apply_reports_destroy_failure_without_claiming_absence(monkeypatch) -> None:
    _patch_ready_settings(monkeypatch)
    _enable_apply_gates(monkeypatch)
    fake = FakeGovc(power_state="poweredOff", fail_destroy=True)

    payload = esxi_vm_teardown.apply_esxi_vm_teardown(
        VM_NAME,
        executor=fake,
        write_report=False,
    )

    assert payload["status"] == "failed"
    assert payload["apply"]["destroy_attempted"] is True
    assert payload["apply"]["absence_validation_attempted"] is False
    assert payload["apply"]["absence_confirmed"] is False


def test_apply_does_not_claim_success_when_post_destroy_probe_fails(
    monkeypatch,
) -> None:
    _patch_ready_settings(monkeypatch)
    _enable_apply_gates(monkeypatch)
    fake = FakeGovc(
        power_state="poweredOff",
        fail_post_destroy_query=True,
    )

    payload = esxi_vm_teardown.apply_esxi_vm_teardown(
        VM_NAME,
        executor=fake,
        write_report=False,
    )

    assert payload["status"] == "failed"
    assert payload["apply"]["destroy_attempted"] is True
    assert payload["apply"]["absence_validation_attempted"] is True
    assert payload["apply"]["absence_confirmed"] is False
    assert any("did not prove" in item for item in payload["blockers"])


def test_apply_is_noop_when_fresh_evidence_proves_vm_already_absent(
    monkeypatch,
) -> None:
    _patch_ready_settings(monkeypatch)
    _enable_apply_gates(monkeypatch)
    fake = FakeGovc(power_state=None)

    payload = esxi_vm_teardown.apply_esxi_vm_teardown(
        VM_NAME,
        executor=fake,
        write_report=False,
    )

    assert payload["status"] == "completed"
    assert payload["apply"]["destroy_attempted"] is False
    assert payload["apply"]["absence_confirmed"] is True
    assert fake.calls == [
        ["about", "-json"],
        ["vm.info", "-json", VM_NAME],
    ]


def test_apply_refuses_ambiguous_vm_inventory_without_write(monkeypatch) -> None:
    _patch_ready_settings(monkeypatch)
    _enable_apply_gates(monkeypatch)
    fake = FakeGovc(ambiguous=True)

    payload = esxi_vm_teardown.apply_esxi_vm_teardown(
        VM_NAME,
        executor=fake,
        write_report=False,
    )

    assert payload["status"] == "blocked"
    assert any("ambiguous" in item for item in payload["blockers"])
    assert fake.calls == [
        ["about", "-json"],
        ["vm.info", "-json", VM_NAME],
    ]


def test_guarded_context_can_supply_every_apply_gate(monkeypatch) -> None:
    _patch_ready_settings(monkeypatch)
    _clear_apply_gates(monkeypatch)
    fake = FakeGovc(power_state="poweredOff")
    context = GuardedActionContext(
        action_id=esxi_vm_teardown.ACTION_ID,
        confirmed_gates=(
            ("VM_TEARDOWN_APPLY", "true"),
            ("VM_TEARDOWN_ALLOW_DELETE", "true"),
            ("VM_TEARDOWN_ALLOW_POWER_OFF", "true"),
            ("LAB_ALLOW_POWER_ACTIONS", "true"),
            ("VM_TEARDOWN_CONFIRM_VM_NAME", VM_NAME),
            ("VM_TEARDOWN_CONFIRM_ESXI_TARGET", ESXI_TARGET),
        ),
        confirmation_phrase=esxi_vm_teardown.VM_TEARDOWN_CONFIRM_PHRASE,
    )

    payload = esxi_vm_teardown.apply_esxi_vm_teardown(
        VM_NAME,
        executor=fake,
        write_report=False,
        guarded_context=context,
    )

    assert payload["status"] == "completed"
    assert all(payload["flag_state"].values())


def test_guarded_context_for_another_action_is_ignored(monkeypatch) -> None:
    _patch_ready_settings(monkeypatch)
    _clear_apply_gates(monkeypatch)
    fake = FakeGovc()
    context = GuardedActionContext(
        action_id="another.action",
        confirmed_gates=(("VM_TEARDOWN_APPLY", "true"),),
        confirmation_phrase=esxi_vm_teardown.VM_TEARDOWN_CONFIRM_PHRASE,
    )

    payload = esxi_vm_teardown.apply_esxi_vm_teardown(
        VM_NAME,
        executor=fake,
        write_report=False,
        guarded_context=context,
    )

    assert payload["status"] == "blocked"
    assert payload["flag_state"]["vm_teardown_apply"] is False
    assert fake.calls == []


def test_apply_enforces_action_policy_before_any_executor_call(monkeypatch) -> None:
    _patch_ready_settings(monkeypatch)
    _enable_apply_gates(monkeypatch)
    fake = FakeGovc()

    class DenyVmTeardownPolicy:
        def readonly_blockers(self):
            return []

        def action_blockers(self, action_id, category):
            assert action_id == "vm.teardown"
            assert category == esxi_vm_teardown.ActionCategory.VM_DEPLOY
            return ["VM teardown policy denied this apply."]

    monkeypatch.setattr(
        esxi_vm_teardown,
        "current_lab_action_policy",
        lambda _mode=None: DenyVmTeardownPolicy(),
    )

    payload = esxi_vm_teardown.apply_esxi_vm_teardown(
        VM_NAME,
        executor=fake,
        write_report=False,
    )

    assert payload["status"] == "blocked"
    assert payload["apply"]["destroy_attempted"] is False
    assert payload["blockers"] == ["VM teardown policy denied this apply."]
    assert fake.calls == []


def test_validate_requires_fresh_confirmed_absence(monkeypatch) -> None:
    _patch_ready_settings(monkeypatch)
    absent = FakeGovc(power_state=None)
    present = FakeGovc(power_state="poweredOff")

    absent_payload = esxi_vm_teardown.validate_esxi_vm_teardown(
        VM_NAME,
        executor=absent,
        write_report=False,
    )
    present_payload = esxi_vm_teardown.validate_esxi_vm_teardown(
        VM_NAME,
        executor=present,
        write_report=False,
    )

    assert absent_payload["status"] == "ready"
    assert absent_payload["vm_evidence"]["absence_confirmed"] is True
    assert absent_payload["freshness"] == "current"
    assert present_payload["status"] == "blocked"
    assert any("still present" in item for item in present_payload["blockers"])


def test_validate_does_not_treat_generic_query_failure_as_absence(
    monkeypatch,
) -> None:
    _patch_ready_settings(monkeypatch)

    def failing_executor(args, *, env, timeout):
        if args == ["about", "-json"]:
            return _about_result()
        if args == ["vm.info", "-json", VM_NAME]:
            return {
                "return_code": 1,
                "stdout": "",
                "stderr": "TLS handshake failed",
            }
        raise AssertionError(args)

    payload = esxi_vm_teardown.validate_esxi_vm_teardown(
        VM_NAME,
        executor=failing_executor,
        write_report=False,
    )

    assert payload["status"] == "blocked"
    assert payload["vm_evidence"]["absence_confirmed"] is False
    assert any("without proving VM absence" in item for item in payload["blockers"])


def test_payload_and_written_evidence_redact_executor_secrets(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _patch_ready_settings(monkeypatch)
    _redirect_reports(monkeypatch, tmp_path)
    secret = "test-vm-teardown-password"

    def leaking_executor(args, *, env, timeout):
        assert env["GOVC_PASSWORD"] == secret
        return {
            "return_code": 1,
            "stdout": "",
            "stderr": f"authentication failed password={secret}",
        }

    payload = esxi_vm_teardown.build_esxi_vm_teardown_preview(
        VM_NAME,
        executor=leaking_executor,
        write_report=True,
    )

    serialized = json.dumps(payload)
    assert secret not in serialized
    assert "password=REDACTED" in serialized
    assert secret not in esxi_vm_teardown.PREVIEW_JSON.read_text(encoding="utf-8")
    assert secret not in esxi_vm_teardown.PREVIEW_REPORT.read_text(encoding="utf-8")


def test_fixed_command_builder_has_no_datastore_or_host_operation() -> None:
    assert esxi_vm_teardown._fixed_args("about", None) == ["about", "-json"]
    assert esxi_vm_teardown._fixed_args("vm_info", VM_NAME) == [
        "vm.info",
        "-json",
        VM_NAME,
    ]
    assert esxi_vm_teardown._fixed_args("power_off", VM_NAME) == [
        "vm.power",
        "-off",
        VM_NAME,
    ]
    assert esxi_vm_teardown._fixed_args("destroy", VM_NAME) == [
        "vm.destroy",
        VM_NAME,
    ]
    with pytest.raises(ValueError):
        esxi_vm_teardown._fixed_args("datastore_destroy", VM_NAME)
    with pytest.raises(ValueError):
        esxi_vm_teardown._fixed_args("destroy", "*")


def _patch_ready_settings(monkeypatch, *, provider_mode="local-lab-readwrite") -> None:
    override = replace(
        settings,
        provider_mode=provider_mode,
        lab_environment="isolated-real-lab",
        lab_acknowledge_real_hardware=True,
        lab_acknowledge_device_reconfiguration=True,
        lab_acknowledge_data_loss_risk=True,
        lab_acknowledge_lab_only=True,
        lab_allow_power_actions=True,
        esxi_configured=True,
        esxi_test_host=ESXI_TARGET,
        esxi_test_username="root",
        esxi_test_password="test-vm-teardown-password",
        esxi_test_verify_tls=False,
    )
    monkeypatch.setattr(esxi_vm_teardown, "settings", override)
    monkeypatch.setattr(
        esxi_vm_teardown,
        "current_lab_action_policy",
        lambda _mode=None: _AllowReadonlyPolicy(),
    )
    monkeypatch.setenv("GOVC_URL", f"https://{ESXI_TARGET}/sdk")
    monkeypatch.setenv("GOVC_USERNAME", "root")
    monkeypatch.setenv("GOVC_PASSWORD", "test-vm-teardown-password")


def _clear_apply_gates(monkeypatch) -> None:
    for name in (
        "VM_TEARDOWN_APPLY",
        "VM_TEARDOWN_ALLOW_DELETE",
        "VM_TEARDOWN_ALLOW_POWER_OFF",
        "LAB_ALLOW_POWER_ACTIONS",
        "VM_TEARDOWN_CONFIRM",
        "VM_TEARDOWN_CONFIRM_VM_NAME",
        "VM_TEARDOWN_CONFIRM_ESXI_TARGET",
    ):
        monkeypatch.delenv(name, raising=False)


def _enable_apply_gates(
    monkeypatch,
    *,
    vm_name: str = VM_NAME,
    target: str = ESXI_TARGET,
) -> None:
    monkeypatch.setenv("VM_TEARDOWN_APPLY", "true")
    monkeypatch.setenv("VM_TEARDOWN_ALLOW_DELETE", "true")
    monkeypatch.setenv("VM_TEARDOWN_ALLOW_POWER_OFF", "true")
    monkeypatch.setenv("LAB_ALLOW_POWER_ACTIONS", "true")
    monkeypatch.setenv(
        "VM_TEARDOWN_CONFIRM",
        esxi_vm_teardown.VM_TEARDOWN_CONFIRM_PHRASE,
    )
    monkeypatch.setenv("VM_TEARDOWN_CONFIRM_VM_NAME", vm_name)
    monkeypatch.setenv("VM_TEARDOWN_CONFIRM_ESXI_TARGET", target)


def _about_result(*, api_type: str = "HostAgent") -> dict:
    return {
        "return_code": 0,
        "stdout": json.dumps(
            {
                "About": {
                    "Name": "VMware ESXi",
                    "Version": "8.0.3",
                    "Build": "12345678",
                    "ApiType": api_type,
                    "InstanceUuid": "11111111-2222-3333-4444-555555555555",
                }
            }
        ),
        "stderr": "",
    }


def _vm_info_result(
    *,
    power_state: str,
    ambiguous: bool = False,
) -> dict:
    vm = {
        "InventoryPath": f"/ha-datacenter/vm/{VM_NAME}",
        "Summary": {
            "Config": {"Name": VM_NAME},
            "Runtime": {"PowerState": power_state},
        },
    }
    virtual_machines = [vm, dict(vm)] if ambiguous else [vm]
    return {
        "return_code": 0,
        "stdout": json.dumps({"VirtualMachines": virtual_machines}),
        "stderr": "",
    }


def _redirect_reports(monkeypatch, tmp_path: Path) -> None:
    codex_runs = tmp_path / "artifacts" / "codex-runs"
    monkeypatch.setattr(esxi_vm_teardown, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(esxi_vm_teardown, "CODEX_RUN_DIR", codex_runs)
    monkeypatch.setattr(
        esxi_vm_teardown,
        "PREVIEW_REPORT",
        codex_runs / "esxi-vm-teardown-preview-report.md",
    )
    monkeypatch.setattr(
        esxi_vm_teardown,
        "PREVIEW_JSON",
        codex_runs / "esxi-vm-teardown-preview-redacted.json",
    )
