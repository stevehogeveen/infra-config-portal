from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


WorkflowActionExecutionKind = Literal["command", "api"]


@dataclass(frozen=True)
class WorkflowActionExecutionSpec:
    action_id: str
    kind: WorkflowActionExecutionKind
    label: str
    command: tuple[str, ...] = ()
    registry_command: str | None = None
    api_endpoint: str | None = None
    api_method: str = "GET"
    reports: tuple[str, ...] = ()
    timeout_seconds: int = 180


ALLOWED_WORKFLOW_ACTION_RUNNERS: dict[str, WorkflowActionExecutionSpec] = {
    "cisco.discover-console": WorkflowActionExecutionSpec(
        action_id="cisco.discover-console",
        kind="command",
        label="Run Check",
        command=("make", "provider-lab-serial-console-discovery"),
        registry_command="make provider-lab-serial-console-discovery",
        reports=(
            "artifacts/codex-runs/serial-console-discovery-report.md",
            "artifacts/codex-runs/serial-console-discovery-redacted.json",
        ),
    ),
    "cisco.privilege-check": WorkflowActionExecutionSpec(
        action_id="cisco.privilege-check",
        kind="command",
        label="Run Check",
        command=("make", "provider-lab-cisco-privilege-check"),
        registry_command="make provider-lab-cisco-privilege-check",
        reports=("artifacts/codex-runs/cisco-privilege-check-report.md",),
    ),
    "cisco.firmware-inventory": WorkflowActionExecutionSpec(
        action_id="cisco.firmware-inventory",
        kind="command",
        label="Check Firmware",
        command=("make", "provider-lab-firmware-cisco-inventory"),
        registry_command="make provider-lab-firmware-cisco-inventory",
        reports=("artifacts/codex-runs/cisco-firmware-inventory-report.md",),
        timeout_seconds=35,
    ),
    "cisco.validate-ssh-scp": WorkflowActionExecutionSpec(
        action_id="cisco.validate-ssh-scp",
        kind="command",
        label="Refresh Status",
        command=("make", "provider-lab-cisco-console-ethernet-readiness"),
        registry_command="make provider-lab-cisco-console-ethernet-readiness",
        reports=("artifacts/codex-runs/cisco-console-ethernet-readiness-report.md",),
    ),
    "ilo.reachability": WorkflowActionExecutionSpec(
        action_id="ilo.reachability",
        kind="command",
        label="Run Check",
        command=("make", "provider-lab-ilo-reachability"),
        registry_command="make provider-lab-ilo-reachability",
        reports=("artifacts/codex-runs/ilo-local-lab-test-report.md",),
    ),
    "ilo.auth": WorkflowActionExecutionSpec(
        action_id="ilo.auth",
        kind="command",
        label="Run Check",
        command=("make", "provider-lab-ilo-authentication"),
        registry_command="make provider-lab-ilo-authentication",
    ),
    "ilo.inventory": WorkflowActionExecutionSpec(
        action_id="ilo.inventory",
        kind="command",
        label="Refresh Status",
        command=("make", "provider-lab-ilo-inventory"),
        registry_command="make provider-lab-ilo-inventory",
        reports=("artifacts/codex-runs/ilo-real-run-report.md",),
    ),
    "ilo.firmware-inventory": WorkflowActionExecutionSpec(
        action_id="ilo.firmware-inventory",
        kind="command",
        label="Check Firmware",
        command=("make", "provider-lab-firmware-inventory"),
        registry_command="make provider-lab-firmware-inventory",
        reports=("artifacts/codex-runs/firmware-inventory-report.md",),
        timeout_seconds=45,
    ),
    "ilo.baseline-preview": WorkflowActionExecutionSpec(
        action_id="ilo.baseline-preview",
        kind="api",
        label="Preview Baseline",
        api_endpoint="/api/v1/providers/hpe-ilo/baseline-preview",
        api_method="GET",
    ),
    "esxi.readiness": WorkflowActionExecutionSpec(
        action_id="esxi.readiness",
        kind="command",
        label="Refresh Status",
        command=("make", "provider-lab-esxi-install-readiness"),
        registry_command="make provider-lab-esxi-install-readiness",
        reports=("artifacts/codex-runs/esxi-install-readiness-report.md",),
    ),
    "esxi.vm-deploy-preview": WorkflowActionExecutionSpec(
        action_id="esxi.vm-deploy-preview",
        kind="command",
        label="Generate Preview",
        command=("make", "provider-lab-esxi-vm-deploy-preview"),
        registry_command="make provider-lab-esxi-vm-deploy-preview",
        reports=("artifacts/codex-runs/esxi-vm-deploy-preview-report.md",),
        timeout_seconds=60,
    ),
    "esxi.vm-deploy-apply": WorkflowActionExecutionSpec(
        action_id="esxi.vm-deploy-apply",
        kind="command",
        label="Apply",
        command=("make", "provider-lab-esxi-vm-deploy-apply"),
        registry_command="make provider-lab-esxi-vm-deploy-apply",
        reports=("artifacts/codex-runs/esxi-vm-deploy-apply-report.md",),
        timeout_seconds=1800,
    ),
    "esxi.vm-deploy-validate": WorkflowActionExecutionSpec(
        action_id="esxi.vm-deploy-validate",
        kind="command",
        label="Validate",
        command=("make", "provider-lab-esxi-vm-deploy-validate"),
        registry_command="make provider-lab-esxi-vm-deploy-validate",
        reports=("artifacts/codex-runs/esxi-vm-deploy-validation-report.md",),
        timeout_seconds=60,
    ),
    "netapp.serial-console-discovery": WorkflowActionExecutionSpec(
        action_id="netapp.serial-console-discovery",
        kind="command",
        label="Run Check",
        command=("make", "provider-lab-serial-console-discovery"),
        registry_command="make provider-lab-serial-console-discovery",
        reports=(
            "artifacts/codex-runs/serial-console-discovery-report.md",
            "artifacts/codex-runs/serial-console-discovery-redacted.json",
        ),
    ),
    "netapp.console-autodiscovery": WorkflowActionExecutionSpec(
        action_id="netapp.console-autodiscovery",
        kind="command",
        label="Run Check",
        command=("make", "provider-lab-netapp-console-autodiscovery"),
        registry_command="make provider-lab-netapp-console-autodiscovery",
        reports=(
            "artifacts/codex-runs/netapp-console-autodiscovery-report.md",
            "artifacts/codex-runs/netapp-console-autodiscovery-redacted.json",
        ),
    ),
    "netapp.console-read-state": WorkflowActionExecutionSpec(
        action_id="netapp.console-read-state",
        kind="command",
        label="Read Console State",
        command=("make", "provider-lab-netapp-console-read-state"),
        registry_command="make provider-lab-netapp-console-read-state",
        reports=(
            "artifacts/codex-runs/netapp-console-state-report.md",
            "artifacts/codex-runs/netapp-console-state-redacted.json",
        ),
    ),
    "netapp.console-login-state": WorkflowActionExecutionSpec(
        action_id="netapp.console-login-state",
        kind="command",
        label="Read Login State",
        command=("make", "provider-lab-netapp-console-login-state"),
        registry_command="make provider-lab-netapp-console-login-state",
        reports=(
            "artifacts/codex-runs/netapp-console-login-state-report.md",
            "artifacts/codex-runs/netapp-console-login-state-redacted.json",
        ),
    ),
    "netapp.nfs-vcenter-readiness": WorkflowActionExecutionSpec(
        action_id="netapp.nfs-vcenter-readiness",
        kind="command",
        label="Refresh Status",
        command=("make", "provider-lab-netapp-nfs-vcenter-readiness"),
        registry_command="make provider-lab-netapp-nfs-vcenter-readiness",
        reports=("artifacts/codex-runs/netapp-nfs-vcenter-readiness-report.md",),
    ),
    "netapp.ontap-upgrade-inventory": WorkflowActionExecutionSpec(
        action_id="netapp.ontap-upgrade-inventory",
        kind="command",
        label="Check Firmware",
        command=("make", "provider-lab-netapp-ontap-upgrade-inventory"),
        registry_command="make provider-lab-netapp-ontap-upgrade-inventory",
        reports=("artifacts/codex-runs/netapp-upgrade-inventory-report.md",),
        timeout_seconds=45,
    ),
    "netapp.component-firmware-inventory": WorkflowActionExecutionSpec(
        action_id="netapp.component-firmware-inventory",
        kind="command",
        label="Check Firmware",
        command=("make", "provider-lab-netapp-ontap-upgrade-inventory"),
        registry_command="make provider-lab-netapp-ontap-upgrade-inventory",
        reports=("artifacts/codex-runs/netapp-upgrade-inventory-report.md",),
        timeout_seconds=45,
    ),
    "vcenter-netapp.readiness": WorkflowActionExecutionSpec(
        action_id="vcenter-netapp.readiness",
        kind="command",
        label="Refresh Status",
        command=("make", "provider-lab-vcenter-netapp-readiness"),
        registry_command="make provider-lab-vcenter-netapp-readiness",
        reports=("artifacts/codex-runs/vcenter-netapp-readiness-report.md",),
    ),
    "vcenter-netapp.datastore-plan": WorkflowActionExecutionSpec(
        action_id="vcenter-netapp.datastore-plan",
        kind="command",
        label="Generate Plan",
        command=("make", "provider-lab-vcenter-netapp-datastore-plan"),
        registry_command="make provider-lab-vcenter-netapp-datastore-plan",
        reports=("artifacts/codex-runs/vcenter-netapp-datastore-plan-report.md",),
    ),
    "firmware.compliance-check": WorkflowActionExecutionSpec(
        action_id="firmware.compliance-check",
        kind="command",
        label="Check Firmware",
        command=("make", "provider-lab-firmware-compliance"),
        registry_command="make provider-lab-firmware-compliance",
        reports=(
            "artifacts/codex-runs/firmware-compliance-report.md",
            "artifacts/codex-runs/firmware-compliance-summary-redacted.json",
        ),
        timeout_seconds=45,
    ),
    "build-verification.run-full": WorkflowActionExecutionSpec(
        action_id="build-verification.run-full",
        kind="command",
        label="Run Verification",
        command=("make", "provider-lab-build-verification"),
        registry_command="make provider-lab-build-verification",
        reports=(
            "artifacts/codex-runs/build-verification-report.md",
            "artifacts/codex-runs/build-verification-summary-redacted.json",
        ),
        timeout_seconds=300,
    ),
    "lab-validation.summary": WorkflowActionExecutionSpec(
        action_id="lab-validation.summary",
        kind="command",
        label="Refresh Summary",
        command=("make", "provider-lab-validation"),
        registry_command="make provider-lab-validation",
        reports=(
            "artifacts/codex-runs/lab-validation-handoff-report.md",
            "artifacts/codex-runs/lab-validation-summary-redacted.json",
        ),
    ),
    "build-verification.toolchain-check": WorkflowActionExecutionSpec(
        action_id="build-verification.toolchain-check",
        kind="command",
        label="Check Toolchain",
        command=("make", "provider-lab-toolchain-check"),
        registry_command="make provider-lab-toolchain-check",
        reports=("artifacts/codex-runs/toolchain-availability-report.md",),
    ),
    "reports.issue-center": WorkflowActionExecutionSpec(
        action_id="reports.issue-center",
        kind="api",
        label="Refresh Status",
        api_endpoint="/api/v1/reports/issues",
        api_method="GET",
    ),
    "reports.summary": WorkflowActionExecutionSpec(
        action_id="reports.summary",
        kind="api",
        label="Refresh Status",
        api_endpoint="/api/v1/reports/summary",
        api_method="GET",
    ),
    "lab-profile.view-active": WorkflowActionExecutionSpec(
        action_id="lab-profile.view-active",
        kind="api",
        label="Refresh Status",
        api_endpoint="/api/v1/lab/profiles",
        api_method="GET",
        reports=("artifacts/codex-runs/lab-ip-profile-update-report.md",),
    ),
}


def get_workflow_action_execution_spec(action_id: str) -> WorkflowActionExecutionSpec | None:
    return ALLOWED_WORKFLOW_ACTION_RUNNERS.get(action_id)


def workflow_action_run_blockers(action: dict[str, Any]) -> list[str]:
    mode = str(action.get("mode") or "")
    if mode not in {"read_only", "report_only"}:
        return [f"{mode or 'unknown'} actions require a guarded workflow and cannot be run from this UI pass."]

    confirmations = [str(item) for item in action.get("required_confirmations") or [] if item]
    if confirmations:
        return [
            "Actions with required confirmations are not runnable from the read-only action runner.",
        ]

    spec = get_workflow_action_execution_spec(str(action.get("action_id") or ""))
    if spec is None:
        return ["No read-only UI runner allowlist entry exists for this action yet."]

    if spec.kind == "command":
        command = action.get("command")
        if not command or command != spec.registry_command:
            return ["Registry command does not match the safe action runner allowlist."]
        return []

    endpoint = action.get("api_endpoint")
    method = action.get("api_method") or "GET"
    if endpoint != spec.api_endpoint or str(method).upper() != spec.api_method:
        return ["Registry API endpoint does not match the safe action runner allowlist."]
    return []


def workflow_action_is_ui_runnable(action: dict[str, Any]) -> bool:
    return not workflow_action_run_blockers(action)
