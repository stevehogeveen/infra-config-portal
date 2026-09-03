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
        kind="api",
        label="Refresh Console Cables",
        api_endpoint="/api/v1/providers/cisco-console/identity-candidates",
        api_method="GET",
    ),
    "cisco.privilege-check": WorkflowActionExecutionSpec(
        action_id="cisco.privilege-check",
        kind="command",
        label="Run Check",
        command=("make", "provider-lab-cisco-privilege-check"),
        registry_command="make provider-lab-cisco-privilege-check",
        reports=(
            "artifacts/codex-runs/cisco-privileged-exec-fix-report.md",
            "artifacts/codex-runs/cisco-vlan10-bootstrap-fix-report.md",
            "artifacts/codex-runs/cisco-login-bootstrap-fix-report.md",
            "artifacts/codex-runs/cisco-console-commander-mode-report.md",
            "artifacts/codex-runs/cisco-4h-lab-run-details-redacted.json",
        ),
    ),
    "cisco.firmware-inventory": WorkflowActionExecutionSpec(
        action_id="cisco.firmware-inventory",
        kind="api",
        label="Check Firmware",
        api_endpoint="/api/v1/lab/firmware-inventory",
        api_method="GET",
        registry_command="make provider-lab-firmware-cisco-inventory",
        reports=("artifacts/codex-runs/cisco-firmware-inventory-report.md",),
        timeout_seconds=60,
    ),
    "cisco.validate-ssh-scp": WorkflowActionExecutionSpec(
        action_id="cisco.validate-ssh-scp",
        kind="command",
        label="Refresh Status",
        command=("make", "provider-lab-cisco-console-ethernet-readiness"),
        registry_command="make provider-lab-cisco-console-ethernet-readiness",
        reports=("artifacts/codex-runs/cisco-console-ethernet-readiness-report.md",),
    ),
    "cisco.setup-readiness": WorkflowActionExecutionSpec(
        action_id="cisco.setup-readiness",
        kind="api",
        label="Check Setup Readiness",
        api_endpoint="/api/v1/providers/cisco/setup-readiness",
        api_method="GET",
        reports=("artifacts/codex-runs/cisco-real-lab-readiness-report.md",),
    ),
    "cisco.ssh-readonly-probe": WorkflowActionExecutionSpec(
        action_id="cisco.ssh-readonly-probe",
        kind="api",
        label="Cisco SSH Read-Only Probe",
        api_endpoint="/api/v1/providers/cisco-ansible/probe",
        api_method="POST",
        registry_command="make provider-lab-cisco-console-ethernet-readiness",
        reports=("artifacts/codex-runs/cisco-ssh-validation-report.md",),
        timeout_seconds=90,
    ),
    "cisco.current-intent-diff": WorkflowActionExecutionSpec(
        action_id="cisco.current-intent-diff",
        kind="api",
        label="Cisco Current Intent Diff",
        api_endpoint="/api/v1/providers/cisco/current-intent-diff",
        api_method="POST",
        reports=(
            "artifacts/codex-runs/cisco-current-intent-diff-report.md",
            "artifacts/codex-runs/cisco-current-intent-diff-redacted.json",
        ),
        timeout_seconds=120,
    ),
    "ilo.reachability": WorkflowActionExecutionSpec(
        action_id="ilo.reachability",
        kind="api",
        label="Run Check",
        api_endpoint="/api/v1/providers/hpe-ilo/readiness",
        api_method="GET",
        registry_command="make provider-lab-ilo-reachability",
        reports=("artifacts/codex-runs/ilo-local-lab-test-report.md",),
    ),
    "ilo.auth": WorkflowActionExecutionSpec(
        action_id="ilo.auth",
        kind="api",
        label="Run Check",
        api_endpoint="/api/v1/providers/hpe-ilo/readiness",
        api_method="GET",
        registry_command="make provider-lab-ilo-authentication",
    ),
    "ilo.inventory": WorkflowActionExecutionSpec(
        action_id="ilo.inventory",
        kind="api",
        label="Refresh Status",
        api_endpoint="/api/v1/providers/hpe-ilo/baseline-preview",
        api_method="GET",
        registry_command="make provider-lab-ilo-inventory",
        reports=("artifacts/codex-runs/ilo-real-run-report.md",),
    ),
    "ilo.firmware-inventory": WorkflowActionExecutionSpec(
        action_id="ilo.firmware-inventory",
        kind="api",
        label="Check Firmware",
        api_endpoint="/api/v1/lab/firmware-inventory",
        api_method="GET",
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
    "ilo.setup-plan-preview": WorkflowActionExecutionSpec(
        action_id="ilo.setup-plan-preview",
        kind="api",
        label="Preview Setup",
        api_endpoint="/api/v1/providers/ilo-redfish/setup-plan-preview",
        api_method="GET",
        reports=("artifacts/codex-runs/hpe-full-rebuild-ilo-report.md",),
    ),
    "raid.discovery": WorkflowActionExecutionSpec(
        action_id="raid.discovery",
        kind="api",
        label="Run Discovery",
        api_endpoint="/api/v1/providers/ilo-redfish/hpe-storage-discovery",
        api_method="GET",
        registry_command="make provider-lab-hpe-storage-discovery",
        reports=("artifacts/codex-runs/hpe-raid-discovery-report.md",),
        timeout_seconds=60,
    ),
    "raid.plan": WorkflowActionExecutionSpec(
        action_id="raid.plan",
        kind="api",
        label="Preview RAID Plan",
        api_endpoint="/api/v1/providers/ilo-redfish/hpe-raid-plan-preview",
        api_method="GET",
        registry_command="make provider-lab-hpe-raid-plan",
        reports=("artifacts/codex-runs/hpe-raid-plan-report.md",),
        timeout_seconds=60,
    ),
    "raid.pending-check": WorkflowActionExecutionSpec(
        action_id="raid.pending-check",
        kind="api",
        label="Check Pending",
        api_endpoint="/api/v1/providers/ilo-redfish/hpe-raid-pending",
        api_method="GET",
        registry_command="make -C app provider-lab-hpe-raid-pending",
        reports=("artifacts/codex-runs/hpe-raid-pending-report.md",),
        timeout_seconds=60,
    ),
    "raid.validate": WorkflowActionExecutionSpec(
        action_id="raid.validate",
        kind="api",
        label="Validate RAID",
        api_endpoint="/api/v1/providers/ilo-redfish/hpe-raid-validate-after-reset",
        api_method="POST",
        registry_command="make provider-lab-hpe-raid-validate-after-reset",
        reports=("artifacts/codex-runs/hpe-raid-after-reset-validation-report.md",),
        timeout_seconds=60,
    ),
    "raid.debug": WorkflowActionExecutionSpec(
        action_id="raid.debug",
        kind="command",
        label="Collect Debug",
        command=("make", "-C", "app", "provider-lab-hpe-raid-debug"),
        registry_command="make -C app provider-lab-hpe-raid-debug",
        reports=("artifacts/codex-runs/hpe-raid-redfish-debug-report.md",),
        timeout_seconds=60,
    ),
    "esxi.readiness": WorkflowActionExecutionSpec(
        action_id="esxi.readiness",
        kind="api",
        label="Refresh Status",
        api_endpoint="/api/v1/providers/ilo-redfish/esxi-install-readiness",
        api_method="GET",
        registry_command="make provider-lab-esxi-install-readiness",
        reports=("artifacts/codex-runs/esxi-install-readiness-report.md",),
    ),
    "esxi.iso-media-check": WorkflowActionExecutionSpec(
        action_id="esxi.iso-media-check",
        kind="api",
        label="Check ISO Media",
        api_endpoint="/api/v1/media-inventory",
        api_method="GET",
        registry_command="make provider-lab-esxi-media-url",
        reports=("artifacts/codex-runs/esxi-media-url-report.md",),
        timeout_seconds=45,
    ),
    "esxi.installer-boot-detection": WorkflowActionExecutionSpec(
        action_id="esxi.installer-boot-detection",
        kind="api",
        label="Detect Installer",
        api_endpoint="/api/v1/providers/ilo-redfish/esxi-install-readiness",
        api_method="GET",
        registry_command="make provider-lab-esxi-detect-installer",
        reports=("artifacts/codex-runs/esxi-installer-boot-report.md",),
        timeout_seconds=60,
    ),
    "esxi.management-readiness": WorkflowActionExecutionSpec(
        action_id="esxi.management-readiness",
        kind="api",
        label="Check Management",
        api_endpoint="/api/v1/providers/ilo-redfish/esxi-install-readiness",
        api_method="GET",
        registry_command="make provider-lab-esxi-detect-installer",
        reports=("artifacts/codex-runs/esxi-management-readiness-report.md",),
        timeout_seconds=60,
    ),
    "esxi.management-validation": WorkflowActionExecutionSpec(
        action_id="esxi.management-validation",
        kind="api",
        label="Validate Management",
        api_endpoint="/api/v1/providers/status",
        api_method="GET",
        registry_command="make provider-lab-esxi-detect-installer",
        reports=("artifacts/codex-runs/esxi-management-readiness-report.md",),
        timeout_seconds=60,
    ),
    "esxi.recover-management": WorkflowActionExecutionSpec(
        action_id="esxi.recover-management",
        kind="command",
        label="Recover Management",
        command=("make", "provider-lab-esxi-recover-management"),
        registry_command="make provider-lab-esxi-recover-management",
        reports=(
            "artifacts/codex-runs/esxi-reachability-remediation-report.md",
            "artifacts/codex-runs/esxi-reachability-remediation-redacted.json",
        ),
        timeout_seconds=420,
    ),
    "esxi.post-recovery-validation": WorkflowActionExecutionSpec(
        action_id="esxi.post-recovery-validation",
        kind="api",
        label="Validate Recovery",
        api_endpoint="/api/v1/providers/esxi-readonly/post-recovery-validation",
        api_method="POST",
        registry_command="make provider-lab-esxi-post-recovery-validation",
        reports=(
            "artifacts/codex-runs/esxi-post-recovery-validation-report.md",
            "artifacts/codex-runs/esxi-post-recovery-validation-redacted.json",
        ),
        timeout_seconds=60,
    ),
    "esxi.ssh-api-check": WorkflowActionExecutionSpec(
        action_id="esxi.ssh-api-check",
        kind="api",
        label="Check SSH/API",
        api_endpoint="/api/v1/providers/esxi-readonly/probe",
        api_method="POST",
        registry_command="make provider-smoke PROVIDER_MODE=local-readonly PROVIDER_SMOKE_PROVIDERS=esxi-readonly",
        timeout_seconds=60,
    ),
    "esxi.netapp-datastore-preview": WorkflowActionExecutionSpec(
        action_id="esxi.netapp-datastore-preview",
        kind="api",
        label="Preview Mount",
        api_endpoint="/api/v1/providers/esxi-readonly/netapp-datastore-preview",
        api_method="GET",
        registry_command="make provider-lab-esxi-netapp-datastore-preview",
        reports=(
            "artifacts/codex-runs/esxi-netapp-nfs-datastore-preview-report.md",
            "artifacts/codex-runs/esxi-netapp-nfs-datastore-preview-redacted.json",
        ),
        timeout_seconds=60,
    ),
    "esxi.netapp-datastore-apply": WorkflowActionExecutionSpec(
        action_id="esxi.netapp-datastore-apply",
        kind="api",
        label="Mount Datastore",
        api_endpoint="/api/v1/providers/esxi-readonly/netapp-datastore-apply",
        api_method="POST",
        registry_command="make provider-lab-esxi-netapp-datastore-apply",
        reports=(
            "artifacts/codex-runs/esxi-netapp-nfs-datastore-apply-report.md",
            "artifacts/codex-runs/esxi-netapp-nfs-datastore-apply-redacted.json",
        ),
        timeout_seconds=180,
    ),
    "esxi.netapp-datastore-validate": WorkflowActionExecutionSpec(
        action_id="esxi.netapp-datastore-validate",
        kind="api",
        label="Validate Mount",
        api_endpoint="/api/v1/providers/esxi-readonly/netapp-datastore-validate",
        api_method="POST",
        registry_command="make provider-lab-esxi-netapp-datastore-validate",
        reports=(
            "artifacts/codex-runs/esxi-netapp-nfs-datastore-validation-report.md",
            "artifacts/codex-runs/esxi-netapp-nfs-datastore-validation-redacted.json",
        ),
        timeout_seconds=60,
    ),
    "esxi.iscsi-datastore-preview": WorkflowActionExecutionSpec(
        action_id="esxi.iscsi-datastore-preview",
        kind="api",
        label="Preview iSCSI Datastore",
        api_endpoint="/api/v1/providers/esxi-readonly/iscsi-datastore-preview",
        api_method="POST",
        registry_command="make provider-lab-esxi-iscsi-datastore-preview",
        reports=(
            "artifacts/codex-runs/esxi-iscsi-datastore-preview-report.md",
            "artifacts/codex-runs/esxi-iscsi-datastore-preview-redacted.json",
        ),
        timeout_seconds=90,
    ),
    "esxi.iscsi-datastore-validate": WorkflowActionExecutionSpec(
        action_id="esxi.iscsi-datastore-validate",
        kind="api",
        label="Validate iSCSI Datastore",
        api_endpoint="/api/v1/providers/esxi-readonly/iscsi-datastore-validate",
        api_method="POST",
        registry_command="make provider-lab-esxi-iscsi-datastore-validate",
        reports=(
            "artifacts/codex-runs/esxi-iscsi-datastore-validation-report.md",
            "artifacts/codex-runs/esxi-iscsi-datastore-validation-redacted.json",
        ),
        timeout_seconds=90,
    ),
    "esxi.vm-deploy-preview": WorkflowActionExecutionSpec(
        action_id="esxi.vm-deploy-preview",
        kind="api",
        label="Generate Preview",
        api_endpoint="/api/v1/providers/esxi-readonly/vm-deploy-preview",
        api_method="GET",
        registry_command="make provider-lab-esxi-vm-deploy-preview",
        reports=("artifacts/codex-runs/esxi-vm-deploy-preview-report.md",),
        timeout_seconds=60,
    ),
    "esxi.vm-deploy-apply": WorkflowActionExecutionSpec(
        action_id="esxi.vm-deploy-apply",
        kind="api",
        label="Apply",
        api_endpoint="/api/v1/providers/esxi-readonly/vm-deploy-apply",
        api_method="POST",
        registry_command="make provider-lab-esxi-vm-deploy-apply",
        reports=("artifacts/codex-runs/esxi-vm-deploy-apply-report.md",),
        timeout_seconds=1800,
    ),
    "esxi.vm-deploy-validate": WorkflowActionExecutionSpec(
        action_id="esxi.vm-deploy-validate",
        kind="api",
        label="Validate",
        api_endpoint="/api/v1/providers/esxi-readonly/vm-deploy-validate",
        api_method="POST",
        registry_command="make provider-lab-esxi-vm-deploy-validate",
        reports=("artifacts/codex-runs/esxi-vm-deploy-validation-report.md",),
        timeout_seconds=60,
    ),
    "esxi.vm-teardown-preview": WorkflowActionExecutionSpec(
        action_id="esxi.vm-teardown-preview",
        kind="api",
        label="Preview VM Removal",
        api_endpoint="/api/v1/workflows/actions/esxi.vm-teardown-preview/run",
        api_method="POST",
        reports=(
            "artifacts/codex-runs/esxi-vm-teardown-preview-report.md",
            "artifacts/codex-runs/esxi-vm-teardown-preview-redacted.json",
        ),
        timeout_seconds=60,
    ),
    "esxi.vm-teardown-apply": WorkflowActionExecutionSpec(
        action_id="esxi.vm-teardown-apply",
        kind="api",
        label="Remove One VM",
        api_endpoint="/api/v1/workflows/actions/esxi.vm-teardown-apply/run",
        api_method="POST",
        reports=(
            "artifacts/codex-runs/esxi-vm-teardown-apply-report.md",
            "artifacts/codex-runs/esxi-vm-teardown-apply-redacted.json",
        ),
        timeout_seconds=300,
    ),
    "esxi.vm-teardown-validate": WorkflowActionExecutionSpec(
        action_id="esxi.vm-teardown-validate",
        kind="api",
        label="Validate VM Is Absent",
        api_endpoint="/api/v1/workflows/actions/esxi.vm-teardown-validate/run",
        api_method="POST",
        reports=(
            "artifacts/codex-runs/esxi-vm-teardown-validation-report.md",
            "artifacts/codex-runs/esxi-vm-teardown-validation-redacted.json",
        ),
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
        kind="api",
        label="Run Check",
        api_endpoint="/api/v1/providers/netapp-ontap/console-discovery",
        api_method="POST",
        registry_command="make provider-lab-netapp-console-autodiscovery",
        reports=(
            "artifacts/codex-runs/netapp-console-autodiscovery-report.md",
            "artifacts/codex-runs/netapp-console-autodiscovery-redacted.json",
        ),
    ),
    "netapp.console-read-state": WorkflowActionExecutionSpec(
        action_id="netapp.console-read-state",
        kind="api",
        label="Read Console State",
        api_endpoint="/api/v1/providers/netapp-ontap/console-read-state",
        api_method="POST",
        registry_command="make provider-lab-netapp-console-read-state",
        reports=(
            "artifacts/codex-runs/netapp-console-state-report.md",
            "artifacts/codex-runs/netapp-console-state-redacted.json",
        ),
    ),
    "netapp.console-login-state": WorkflowActionExecutionSpec(
        action_id="netapp.console-login-state",
        kind="api",
        label="Read Login State",
        api_endpoint="/api/v1/providers/netapp-ontap/console-login-state",
        api_method="POST",
        registry_command="make provider-lab-netapp-console-login-state",
        reports=(
            "artifacts/codex-runs/netapp-console-login-state-report.md",
            "artifacts/codex-runs/netapp-console-login-state-redacted.json",
        ),
    ),
    "netapp.nfs-vcenter-readiness": WorkflowActionExecutionSpec(
        action_id="netapp.nfs-vcenter-readiness",
        kind="api",
        label="Refresh Status",
        api_endpoint="/api/v1/providers/netapp-ontap/nfs-vcenter-readiness",
        api_method="GET",
        registry_command="make provider-lab-netapp-nfs-vcenter-readiness",
        reports=("artifacts/codex-runs/netapp-nfs-vcenter-readiness-report.md",),
    ),
    "netapp.live-state": WorkflowActionExecutionSpec(
        action_id="netapp.live-state",
        kind="api",
        label="Read State",
        api_endpoint="/api/v1/providers/netapp-ontap/live-state",
        api_method="GET",
        registry_command="make provider-lab-netapp-live-state",
        reports=("artifacts/codex-runs/netapp-live-state-report.md",),
        timeout_seconds=60,
    ),
    "netapp.validate-setup": WorkflowActionExecutionSpec(
        action_id="netapp.validate-setup",
        kind="api",
        label="Validate Setup",
        api_endpoint="/api/v1/providers/netapp-ontap/validate-setup",
        api_method="POST",
        registry_command="make provider-lab-netapp-validate-setup",
        reports=("artifacts/codex-runs/netapp-live-state-report.md",),
        timeout_seconds=60,
    ),
    "netapp.address-plan": WorkflowActionExecutionSpec(
        action_id="netapp.address-plan",
        kind="api",
        label="Address Plan",
        api_endpoint="/api/v1/providers/netapp-ontap/address-plan",
        api_method="GET",
        registry_command="make provider-lab-netapp-address-plan",
        reports=(
            "artifacts/codex-runs/netapp-address-remediation-plan-report.md",
            "artifacts/codex-runs/netapp-address-remediation-plan-redacted.json",
        ),
        timeout_seconds=45,
    ),
    "netapp.address-preview": WorkflowActionExecutionSpec(
        action_id="netapp.address-preview",
        kind="api",
        label="Preview Readdress",
        api_endpoint="/api/v1/providers/netapp-ontap/address-preview",
        api_method="GET",
        registry_command="make provider-lab-netapp-address-preview",
        reports=(
            "artifacts/codex-runs/netapp-address-remediation-preview-report.md",
            "artifacts/codex-runs/netapp-address-remediation-preview-redacted.json",
        ),
        timeout_seconds=75,
    ),
    "netapp.address-apply": WorkflowActionExecutionSpec(
        action_id="netapp.address-apply",
        kind="command",
        label="Apply Readdress",
        command=("make", "provider-lab-netapp-address-apply"),
        registry_command="make provider-lab-netapp-address-apply",
        reports=(
            "artifacts/codex-runs/netapp-address-remediation-apply-report.md",
            "artifacts/codex-runs/netapp-address-remediation-apply-redacted.json",
        ),
        timeout_seconds=180,
    ),
    "netapp.address-validate": WorkflowActionExecutionSpec(
        action_id="netapp.address-validate",
        kind="api",
        label="Validate Readdress",
        api_endpoint="/api/v1/providers/netapp-ontap/address-validate",
        api_method="POST",
        registry_command="make provider-lab-netapp-address-validate",
        reports=(
            "artifacts/codex-runs/netapp-address-remediation-validation-report.md",
            "artifacts/codex-runs/netapp-address-remediation-validation-redacted.json",
        ),
        timeout_seconds=90,
    ),
    "netapp.ha-node-diagnose": WorkflowActionExecutionSpec(
        action_id="netapp.ha-node-diagnose",
        kind="api",
        label="Diagnose HA",
        api_endpoint="/api/v1/providers/netapp-ontap/ha-node-diagnose",
        api_method="POST",
        registry_command="make provider-lab-netapp-ha-node-diagnose",
        reports=(
            "artifacts/codex-runs/netapp-ha-node-remediation-report.md",
            "artifacts/codex-runs/netapp-ha-node-remediation-redacted.json",
        ),
        timeout_seconds=120,
    ),
    "netapp.factory-reset-preview": WorkflowActionExecutionSpec(
        action_id="netapp.factory-reset-preview",
        kind="api",
        label="Preview Factory Reset",
        api_endpoint="/api/v1/providers/netapp-ontap/factory-reset-preview",
        api_method="POST",
        registry_command="make provider-lab-netapp-factory-reset-preview",
        reports=(
            "artifacts/codex-runs/netapp-factory-reset-plan-report.md",
            "artifacts/codex-runs/netapp-factory-reset-plan-redacted.json",
        ),
        timeout_seconds=60,
    ),
    "netapp.factory-reset-apply": WorkflowActionExecutionSpec(
        action_id="netapp.factory-reset-apply",
        kind="api",
        label="Apply Factory Reset",
        api_endpoint="/api/v1/providers/netapp-ontap/factory-reset-apply",
        api_method="POST",
        registry_command="make provider-lab-netapp-factory-reset-apply",
        reports=(
            "artifacts/codex-runs/netapp-factory-reset-apply-report.md",
            "artifacts/codex-runs/netapp-factory-reset-apply-redacted.json",
        ),
        timeout_seconds=90,
    ),
    "netapp.factory-reset-validate": WorkflowActionExecutionSpec(
        action_id="netapp.factory-reset-validate",
        kind="api",
        label="Validate Factory Reset",
        api_endpoint="/api/v1/providers/netapp-ontap/factory-reset-validate",
        api_method="POST",
        registry_command="make provider-lab-netapp-factory-reset-validate",
        reports=(
            "artifacts/codex-runs/netapp-factory-reset-validation-report.md",
            "artifacts/codex-runs/netapp-factory-reset-validation-redacted.json",
        ),
        timeout_seconds=60,
    ),
    "netapp.setup-preview": WorkflowActionExecutionSpec(
        action_id="netapp.setup-preview",
        kind="api",
        label="Preview Setup",
        api_endpoint="/api/v1/providers/netapp-ontap/setup-preview",
        api_method="GET",
        registry_command="make provider-lab-netapp-setup-preview",
        reports=("artifacts/codex-runs/netapp-setup-preview-report.md",),
        timeout_seconds=60,
    ),
    "netapp.post-setup-validation": WorkflowActionExecutionSpec(
        action_id="netapp.post-setup-validation",
        kind="api",
        label="Validate Setup",
        api_endpoint="/api/v1/providers/netapp-ontap/post-setup-validation",
        api_method="POST",
        registry_command="make provider-lab-netapp-post-setup-validation",
        reports=("artifacts/codex-runs/netapp-post-setup-validation-report.md",),
        timeout_seconds=60,
    ),
    "netapp.nfs-setup-preview": WorkflowActionExecutionSpec(
        action_id="netapp.nfs-setup-preview",
        kind="api",
        label="Preview NFS Setup",
        api_endpoint="/api/v1/providers/netapp-ontap/nfs-setup-preview",
        api_method="GET",
        registry_command="make provider-lab-netapp-nfs-setup-preview",
        reports=("artifacts/codex-runs/netapp-nfs-setup-preview-report.md",),
        timeout_seconds=60,
    ),
    "netapp.nfs-setup-validate": WorkflowActionExecutionSpec(
        action_id="netapp.nfs-setup-validate",
        kind="api",
        label="Validate NFS Setup",
        api_endpoint="/api/v1/providers/netapp-ontap/nfs-setup-validate",
        api_method="POST",
        registry_command="make provider-lab-netapp-nfs-setup-validate",
        reports=("artifacts/codex-runs/netapp-nfs-setup-validation-report.md",),
        timeout_seconds=60,
    ),
    "netapp.iscsi-setup-preview": WorkflowActionExecutionSpec(
        action_id="netapp.iscsi-setup-preview",
        kind="api",
        label="Preview iSCSI Setup",
        api_endpoint="/api/v1/providers/netapp-ontap/iscsi-setup-preview",
        api_method="GET",
        registry_command="make provider-lab-netapp-iscsi-setup-preview",
        reports=("artifacts/codex-runs/netapp-iscsi-setup-preview-report.md",),
        timeout_seconds=60,
    ),
    "netapp.iscsi-setup-validate": WorkflowActionExecutionSpec(
        action_id="netapp.iscsi-setup-validate",
        kind="api",
        label="Validate iSCSI Setup",
        api_endpoint="/api/v1/providers/netapp-ontap/iscsi-setup-validate",
        api_method="POST",
        registry_command="make provider-lab-netapp-iscsi-setup-validate",
        reports=("artifacts/codex-runs/netapp-iscsi-setup-validation-report.md",),
        timeout_seconds=60,
    ),
    "netapp.ontap-upgrade-inventory": WorkflowActionExecutionSpec(
        action_id="netapp.ontap-upgrade-inventory",
        kind="api",
        label="Check Firmware",
        api_endpoint="/api/v1/providers/netapp-ontap/ontap-upgrade/inventory",
        api_method="GET",
        registry_command="make provider-lab-netapp-ontap-upgrade-inventory",
        reports=("artifacts/codex-runs/netapp-upgrade-inventory-report.md",),
        timeout_seconds=45,
    ),
    "netapp.component-firmware-inventory": WorkflowActionExecutionSpec(
        action_id="netapp.component-firmware-inventory",
        kind="api",
        label="Check Firmware",
        api_endpoint="/api/v1/providers/netapp-ontap/ontap-upgrade/inventory",
        api_method="GET",
        registry_command="make provider-lab-netapp-ontap-upgrade-inventory",
        reports=("artifacts/codex-runs/netapp-upgrade-inventory-report.md",),
        timeout_seconds=45,
    ),
    "netapp.ontap-upgrade-plan": WorkflowActionExecutionSpec(
        action_id="netapp.ontap-upgrade-plan",
        kind="api",
        label="Plan Upgrade",
        api_endpoint="/api/v1/providers/netapp-ontap/ontap-upgrade/plan",
        api_method="GET",
        registry_command="make provider-lab-netapp-ontap-upgrade-plan",
        reports=("artifacts/codex-runs/netapp-ontap-upgrade-plan-report.md",),
        timeout_seconds=60,
    ),
    "netapp.ontap-upgrade-validate": WorkflowActionExecutionSpec(
        action_id="netapp.ontap-upgrade-validate",
        kind="api",
        label="Validate Upgrade",
        api_endpoint="/api/v1/providers/netapp-ontap/ontap-upgrade/validate",
        api_method="POST",
        registry_command="make provider-lab-netapp-ontap-upgrade-validate",
        reports=("artifacts/codex-runs/netapp-ontap-upgrade-validation-report.md",),
        timeout_seconds=60,
    ),
    "vcenter-netapp.readiness": WorkflowActionExecutionSpec(
        action_id="vcenter-netapp.readiness",
        kind="api",
        label="Refresh Status",
        api_endpoint="/api/v1/lab/vcenter-netapp/readiness",
        api_method="GET",
        registry_command="make provider-lab-vcenter-netapp-readiness",
        reports=("artifacts/codex-runs/vcenter-netapp-readiness-report.md",),
    ),
    "vcenter-netapp.datastore-plan": WorkflowActionExecutionSpec(
        action_id="vcenter-netapp.datastore-plan",
        kind="api",
        label="Generate Plan",
        api_endpoint="/api/v1/lab/vcenter-netapp/datastore-plan",
        api_method="GET",
        registry_command="make provider-lab-vcenter-netapp-datastore-plan",
        reports=("artifacts/codex-runs/vcenter-netapp-datastore-plan-report.md",),
    ),
    "vcenter.install-readiness": WorkflowActionExecutionSpec(
        action_id="vcenter.install-readiness",
        kind="api",
        label="Check Readiness",
        api_endpoint="/api/v1/lab/vcenter/install-readiness",
        api_method="GET",
        registry_command="make provider-lab-vcenter-install-readiness",
        reports=(
            "artifacts/codex-runs/vcenter-install-readiness-report.md",
            "artifacts/codex-runs/vcenter-install-readiness-redacted.json",
        ),
    ),
    "vcenter.install-plan": WorkflowActionExecutionSpec(
        action_id="vcenter.install-plan",
        kind="api",
        label="Generate Plan",
        api_endpoint="/api/v1/lab/vcenter/install-plan",
        api_method="GET",
        registry_command="make provider-lab-vcenter-install-plan",
        reports=(
            "artifacts/codex-runs/vcenter-install-plan-report.md",
            "artifacts/codex-runs/vcenter-install-plan-redacted.json",
        ),
    ),
    "vcenter.install-preview": WorkflowActionExecutionSpec(
        action_id="vcenter.install-preview",
        kind="api",
        label="Preview Deploy",
        api_endpoint="/api/v1/lab/vcenter/install-preview",
        api_method="GET",
        registry_command="make provider-lab-vcenter-install-preview",
        reports=(
            "artifacts/codex-runs/vcenter-install-preview-report.md",
            "artifacts/codex-runs/vcenter-install-preview-redacted.json",
        ),
    ),
    "vcenter.install-apply": WorkflowActionExecutionSpec(
        action_id="vcenter.install-apply",
        kind="command",
        label="Deploy vCenter",
        command=(
            "env",
            "VCENTER_INSTALL_APPLY=true",
            "VCENTER_INSTALL_CONFIRM=DEPLOY VCENTER",
            "VCENTER_INSTALL_ALLOW_DEPLOY=true",
            "make",
            "provider-lab-vcenter-install-apply",
        ),
        registry_command="make provider-lab-vcenter-install-apply",
        reports=(
            "artifacts/codex-runs/vcenter-install-apply-report.md",
            "artifacts/codex-runs/vcenter-post-install-validation-report.md",
            "artifacts/codex-runs/vcenter-install-apply-unblock-final-report.md",
            "artifacts/codex-runs/vcenter-install-apply-redacted.json",
            "artifacts/codex-runs/vcenter-post-install-validation-redacted.json",
        ),
        timeout_seconds=7200,
    ),
    "vcenter.attach-esxi-preview": WorkflowActionExecutionSpec(
        action_id="vcenter.attach-esxi-preview",
        kind="api",
        label="Preview Attach",
        api_endpoint="/api/v1/lab/vcenter/attach-esxi-preview",
        api_method="GET",
        registry_command="make provider-lab-vcenter-attach-esxi-preview",
        reports=(
            "artifacts/codex-runs/vcenter-attach-esxi-preview-report.md",
            "artifacts/codex-runs/vcenter-attach-esxi-preview-redacted.json",
        ),
        timeout_seconds=120,
    ),
    "vcenter.attach-esxi-apply": WorkflowActionExecutionSpec(
        action_id="vcenter.attach-esxi-apply",
        kind="command",
        label="Attach ESXi",
        command=(
            "env",
            "VCENTER_ATTACH_ESXI_APPLY=true",
            "VCENTER_ATTACH_ESXI_CONFIRM=ATTACH ESXI TO VCENTER",
            "VCENTER_ATTACH_ESXI_ALLOW=true",
            "make",
            "provider-lab-vcenter-attach-esxi-apply",
        ),
        registry_command="make provider-lab-vcenter-attach-esxi-apply",
        reports=(
            "artifacts/codex-runs/vcenter-attach-esxi-apply-report.md",
            "artifacts/codex-runs/vcenter-post-attach-validation-report.md",
            "artifacts/codex-runs/vcenter-attach-esxi-datastore-final-report.md",
            "artifacts/codex-runs/vcenter-attach-esxi-apply-redacted.json",
            "artifacts/codex-runs/vcenter-post-attach-validation-redacted.json",
        ),
        timeout_seconds=1200,
    ),
    "vcenter.post-attach-validation": WorkflowActionExecutionSpec(
        action_id="vcenter.post-attach-validation",
        kind="api",
        label="Validate Attach",
        api_endpoint="/api/v1/lab/vcenter/post-attach-validation",
        api_method="GET",
        registry_command="make provider-lab-vcenter-post-attach-validation",
        reports=(
            "artifacts/codex-runs/vcenter-post-attach-validation-report.md",
            "artifacts/codex-runs/vcenter-post-attach-validation-redacted.json",
        ),
        timeout_seconds=120,
    ),
    "firmware.compliance-check": WorkflowActionExecutionSpec(
        action_id="firmware.compliance-check",
        kind="api",
        label="Check Firmware",
        api_endpoint="/api/v1/lab/firmware-compliance",
        api_method="GET",
        registry_command="make provider-lab-firmware-compliance",
        reports=(
            "artifacts/codex-runs/firmware-compliance-report.md",
            "artifacts/codex-runs/firmware-compliance-summary-redacted.json",
        ),
        timeout_seconds=45,
    ),
    "firmware.inventory": WorkflowActionExecutionSpec(
        action_id="firmware.inventory",
        kind="api",
        label="Run Inventory",
        api_endpoint="/api/v1/lab/firmware-inventory",
        api_method="GET",
        registry_command="make provider-lab-firmware-inventory",
        reports=("artifacts/codex-runs/firmware-inventory-report.md",),
        timeout_seconds=45,
    ),
    "firmware.package-inventory": WorkflowActionExecutionSpec(
        action_id="firmware.package-inventory",
        kind="api",
        label="View Packages",
        api_endpoint="/api/v1/media-inventory",
        api_method="GET",
    ),
    "firmware.waiver-check": WorkflowActionExecutionSpec(
        action_id="firmware.waiver-check",
        kind="api",
        label="Check Waiver",
        api_endpoint="/api/v1/lab/firmware-waiver-check",
        api_method="GET",
        registry_command="make provider-lab-firmware-waiver-check",
        reports=("artifacts/codex-runs/firmware-waiver-report.md",),
        timeout_seconds=45,
    ),
    "firmware.upgrade-plan": WorkflowActionExecutionSpec(
        action_id="firmware.upgrade-plan",
        kind="api",
        label="Plan Upgrade",
        api_endpoint="/api/v1/lab/firmware-compliance",
        api_method="GET",
        registry_command="make provider-lab-firmware-compliance",
        reports=("artifacts/codex-runs/firmware-compliance-gate-final-report.md",),
        timeout_seconds=45,
    ),
    "build-verification.live-status": WorkflowActionExecutionSpec(
        action_id="build-verification.live-status",
        kind="command",
        label="Refresh Status",
        command=("env", "PROVIDER_LAB_LIVE_STAGE_TIMEOUT_SECONDS=20", "make", "provider-lab-live-status"),
        registry_command="make provider-lab-live-status",
        reports=(
            "artifacts/codex-runs/provider-lab-live-status-report.md",
            "artifacts/codex-runs/provider-lab-live-status-redacted.json",
        ),
        timeout_seconds=180,
    ),
    "provider-smoke.real-lab": WorkflowActionExecutionSpec(
        action_id="provider-smoke.real-lab",
        kind="command",
        label="Run Real Smoke",
        command=(
            "env",
            "PROVIDER_MODE=local-lab-readwrite",
            "PROVIDER_SMOKE_REQUIRE_REAL=true",
            "PYTHONPATH=app\\backend",
            "app\\backend\\.venv\\Scripts\\python.exe",
            "app\\backend\\scripts\\provider_smoke.py",
        ),
        registry_command=(
            "PROVIDER_MODE=local-lab-readwrite PROVIDER_SMOKE_REQUIRE_REAL=true "
            "PYTHONPATH=app\\backend app\\backend\\.venv\\Scripts\\python.exe app\\backend\\scripts\\provider_smoke.py"
        ),
        reports=(
            "artifacts/real-lab/provider-smoke-latest.md",
            "artifacts/real-lab/provider-smoke-latest.json",
        ),
        timeout_seconds=300,
    ),
    "operator-readonly-sweep.real-lab": WorkflowActionExecutionSpec(
        action_id="operator-readonly-sweep.real-lab",
        kind="command",
        label="Run Operator Read-Only Sweep",
        command=(
            "env",
            "PROVIDER_MODE=local-lab-readwrite",
            "PYTHONPATH=app\\backend",
            "app\\backend\\.venv\\Scripts\\python.exe",
            "app\\backend\\scripts\\operator_readonly_sweep.py",
        ),
        registry_command=(
            "PROVIDER_MODE=local-lab-readwrite PYTHONPATH=app\\backend "
            "app\\backend\\.venv\\Scripts\\python.exe app\\backend\\scripts\\operator_readonly_sweep.py"
        ),
        reports=(
            "artifacts/real-lab/operator-readonly-sweep-latest.md",
            "artifacts/real-lab/operator-readonly-sweep-latest.json",
        ),
        timeout_seconds=420,
    ),
    "build-verification.run-full": WorkflowActionExecutionSpec(
        action_id="build-verification.run-full",
        kind="api",
        label="Run Verification",
        api_endpoint="/api/v1/lab/build-verification",
        api_method="GET",
        registry_command="make provider-lab-build-verification",
        reports=(
            "artifacts/codex-runs/build-verification-report.md",
            "artifacts/codex-runs/build-verification-summary-redacted.json",
        ),
        timeout_seconds=300,
    ),
    "lab-validation.summary": WorkflowActionExecutionSpec(
        action_id="lab-validation.summary",
        kind="api",
        label="Refresh Summary",
        api_endpoint="/api/v1/lab/validation",
        api_method="GET",
        registry_command="make provider-lab-validation",
        reports=(
            "artifacts/codex-runs/lab-validation-handoff-report.md",
            "artifacts/codex-runs/lab-validation-summary-redacted.json",
        ),
    ),
    "full-lab.validation": WorkflowActionExecutionSpec(
        action_id="full-lab.validation",
        kind="api",
        label="Run Validation",
        api_endpoint="/api/v1/lab/validation",
        api_method="GET",
        registry_command="make provider-lab-validation",
        reports=(
            "artifacts/codex-runs/lab-validation-handoff-report.md",
            "artifacts/codex-runs/lab-validation-summary-redacted.json",
        ),
        timeout_seconds=180,
    ),
    "full-lab.build-plan": WorkflowActionExecutionSpec(
        action_id="full-lab.build-plan",
        kind="api",
        label="Generate Plan",
        api_endpoint="/api/v1/lab/full-rebuild-summary",
        api_method="GET",
        registry_command="make provider-lab-full-rebuild-summary",
        reports=(
            "artifacts/codex-runs/full-device-rebuild-baseline-report.md",
            "artifacts/codex-runs/full-device-rebuild-4h-report.md",
        ),
        timeout_seconds=180,
    ),
    "full-lab.repair": WorkflowActionExecutionSpec(
        action_id="full-lab.repair",
        kind="api",
        label="Generate Repair Plan",
        api_endpoint="/api/v1/lab/golden-state",
        api_method="GET",
        registry_command="make provider-lab-golden-state",
        reports=(
            "artifacts/codex-runs/golden-state-productization-report.md",
            "artifacts/codex-runs/golden-state-summary-redacted.json",
        ),
        timeout_seconds=90,
    ),
    "full-lab.handoff-report": WorkflowActionExecutionSpec(
        action_id="full-lab.handoff-report",
        kind="api",
        label="Generate Handoff",
        api_endpoint="/api/v1/lab/golden-state",
        api_method="GET",
        registry_command="make provider-lab-golden-state",
        reports=(
            "artifacts/codex-runs/golden-state-productization-report.md",
            "artifacts/codex-runs/golden-state-summary-redacted.json",
        ),
        timeout_seconds=90,
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
    "lab-profile.validate-ip-profile": WorkflowActionExecutionSpec(
        action_id="lab-profile.validate-ip-profile",
        kind="api",
        label="Validate IP Profile",
        api_endpoint="/api/v1/lab/build-verification",
        api_method="GET",
        registry_command="make provider-lab-build-verification-live",
        reports=(
            "artifacts/codex-runs/lab-ip-profile-update-report.md",
            "artifacts/codex-runs/lab-ip-profile-hardening-report.md",
        ),
        timeout_seconds=90,
    ),
    "cisco.apply-bootstrap": WorkflowActionExecutionSpec(
        action_id="cisco.apply-bootstrap",
        kind="command",
        label="Apply Bootstrap",
        command=("make", "provider-lab-cisco-vlan10-bootstrap-apply"),
        registry_command="make provider-lab-cisco-vlan10-bootstrap-apply",
        reports=("artifacts/codex-runs/cisco-bootstrap-apply-report.md",),
        timeout_seconds=240,
    ),
    "ilo.virtual-media-insert": WorkflowActionExecutionSpec(
        action_id="ilo.virtual-media-insert",
        kind="command",
        label="Insert Media",
        command=("make", "provider-lab-esxi-insert-virtual-media"),
        registry_command="make provider-lab-esxi-insert-virtual-media",
        reports=("artifacts/codex-runs/esxi-virtual-media-report.md",),
        timeout_seconds=300,
    ),
    "ilo.one-time-boot": WorkflowActionExecutionSpec(
        action_id="ilo.one-time-boot",
        kind="command",
        label="Set Boot",
        command=("make", "provider-lab-esxi-one-time-boot"),
        registry_command="make provider-lab-esxi-one-time-boot",
        reports=("artifacts/codex-runs/esxi-one-time-boot-report.md",),
        timeout_seconds=180,
    ),
    "ilo.reset-server": WorkflowActionExecutionSpec(
        action_id="ilo.reset-server",
        kind="command",
        label="Reset Server",
        command=(
            "env",
            "LAB_ALLOW_POWER_ACTIONS=true",
            "HPE_RAID_RESET_CONFIRM=RESET SERVER FOR HPE RAID APPLY",
            "make",
            "provider-lab-esxi-reset-installer-boot",
        ),
        registry_command=(
            "LAB_ALLOW_POWER_ACTIONS=true HPE_RAID_RESET_CONFIRM='RESET SERVER FOR HPE RAID APPLY' "
            "make provider-lab-esxi-reset-installer-boot"
        ),
        reports=("artifacts/codex-runs/esxi-installer-boot-report.md",),
        timeout_seconds=1800,
    ),
    "raid.apply": WorkflowActionExecutionSpec(
        action_id="raid.apply",
        kind="api",
        label="Apply RAID",
        api_endpoint="/api/v1/providers/ilo-redfish/hpe-raid-apply",
        api_method="POST",
        registry_command="HPE_RAID_ALLOW_DESTRUCTIVE=true make provider-lab-hpe-raid-apply",
        reports=("artifacts/codex-runs/hpe-raid-apply-report.md",),
        timeout_seconds=900,
    ),
    "raid.factory-reset-preview": WorkflowActionExecutionSpec(
        action_id="raid.factory-reset-preview",
        kind="api",
        label="Preview RAID Factory Reset",
        api_endpoint="/api/v1/providers/ilo-redfish/hpe-raid-factory-reset-preview",
        api_method="GET",
        reports=("artifacts/codex-runs/hpe-raid-factory-reset-plan-report.md",),
        timeout_seconds=300,
    ),
    "raid.factory-reset-apply": WorkflowActionExecutionSpec(
        action_id="raid.factory-reset-apply",
        kind="api",
        label="Apply RAID Factory Reset",
        api_endpoint="/api/v1/providers/ilo-redfish/hpe-raid-factory-reset-apply",
        api_method="POST",
        registry_command="LAB_ALLOW_FACTORY_RESET=true HPE_RAID_ALLOW_FACTORY_RESET=true make provider-lab-hpe-raid-factory-reset-apply",
        reports=("artifacts/codex-runs/hpe-raid-factory-reset-apply-report.md",),
        timeout_seconds=900,
    ),
    "raid.reset-commit": WorkflowActionExecutionSpec(
        action_id="raid.reset-commit",
        kind="api",
        label="Reset / Commit",
        api_endpoint="/api/v1/providers/ilo-redfish/hpe-raid-reset",
        api_method="POST",
        registry_command="LAB_ALLOW_POWER_ACTIONS=true HPE_RAID_ALLOW_RESET=true make -C app provider-lab-server-reset-for-raid",
        reports=("artifacts/codex-runs/hpe-raid-reset-report.md",),
        timeout_seconds=1800,
    ),
    "esxi.virtual-media-insert": WorkflowActionExecutionSpec(
        action_id="esxi.virtual-media-insert",
        kind="command",
        label="Insert Media",
        command=("make", "provider-lab-esxi-insert-virtual-media"),
        registry_command="make provider-lab-esxi-insert-virtual-media",
        reports=("artifacts/codex-runs/esxi-virtual-media-report.md",),
        timeout_seconds=300,
    ),
    "esxi.one-time-boot": WorkflowActionExecutionSpec(
        action_id="esxi.one-time-boot",
        kind="command",
        label="One-Time Boot",
        command=("make", "provider-lab-esxi-one-time-boot"),
        registry_command="make provider-lab-esxi-one-time-boot",
        reports=("artifacts/codex-runs/esxi-one-time-boot-report.md",),
        timeout_seconds=180,
    ),
    "esxi.rebuild-install": WorkflowActionExecutionSpec(
        action_id="esxi.rebuild-install",
        kind="command",
        label="Boot ESXi Installer",
        command=("env", "LAB_ALLOW_POWER_ACTIONS=true", "make", "provider-lab-esxi-reset-installer-boot"),
        registry_command="make provider-lab-esxi-reset-installer-boot",
        reports=("artifacts/codex-runs/esxi-full-rebuild-boot-report.md",),
        timeout_seconds=1800,
    ),
    "netapp.setup-apply": WorkflowActionExecutionSpec(
        action_id="netapp.setup-apply",
        kind="api",
        label="Apply Setup",
        api_endpoint="/api/v1/providers/netapp-ontap/setup-apply",
        api_method="POST",
        registry_command="make provider-lab-netapp-setup-apply",
        reports=("artifacts/codex-runs/netapp-cluster-setup-apply-report.md",),
        timeout_seconds=900,
    ),
    "netapp.nfs-setup-apply": WorkflowActionExecutionSpec(
        action_id="netapp.nfs-setup-apply",
        kind="api",
        label="Apply NFS Setup",
        api_endpoint="/api/v1/providers/netapp-ontap/nfs-setup-apply",
        api_method="POST",
        registry_command="make provider-lab-netapp-nfs-setup-apply",
        reports=("artifacts/codex-runs/netapp-nfs-setup-apply-report.md",),
        timeout_seconds=900,
    ),
    "netapp.iscsi-setup-apply": WorkflowActionExecutionSpec(
        action_id="netapp.iscsi-setup-apply",
        kind="api",
        label="Apply iSCSI Setup",
        api_endpoint="/api/v1/providers/netapp-ontap/iscsi-setup-apply",
        api_method="POST",
        registry_command="make provider-lab-netapp-iscsi-setup-apply",
        reports=("artifacts/codex-runs/netapp-iscsi-setup-apply-report.md",),
        timeout_seconds=900,
    ),
    "netapp.ontap-upgrade-apply": WorkflowActionExecutionSpec(
        action_id="netapp.ontap-upgrade-apply",
        kind="command",
        label="Upgrade ONTAP",
        command=(
            "env",
            "NETAPP_ONTAP_UPGRADE_APPLY=true",
            "NETAPP_ONTAP_UPGRADE_CONFIRM=UPGRADE ONTAP",
            "make",
            "provider-lab-netapp-ontap-upgrade-apply",
        ),
        registry_command="make provider-lab-netapp-ontap-upgrade-apply",
        reports=("artifacts/codex-runs/netapp-ontap-upgrade-apply-report.md",),
        timeout_seconds=1800,
    ),
}


def get_workflow_action_execution_spec(action_id: str) -> WorkflowActionExecutionSpec | None:
    return ALLOWED_WORKFLOW_ACTION_RUNNERS.get(action_id)


def workflow_action_run_blockers(
    action: dict[str, Any],
    *,
    confirmation_phrase: str | None = None,
    confirmed_gates: list[str] | None = None,
) -> list[str]:
    mode = str(action.get("mode") or "")
    spec = get_workflow_action_execution_spec(str(action.get("action_id") or ""))
    if spec is None:
        return ["No UI runner allowlist entry exists for this action yet."]

    if str(action.get("current_availability") or "") == "not_in_scope":
        return [
            str(action.get("not_in_scope_reason") or "This action is not in scope for the active lab profile.")
        ]
    registry_blockers = [str(item) for item in action.get("blockers") or [] if item]
    if registry_blockers:
        if mode in {"write", "destructive", "upgrade"}:
            return ["guarded workflow is blocked by current action policy.", *registry_blockers]
        return registry_blockers

    if mode not in {"read_only", "report_only"}:
        setup_blockers = workflow_action_guarded_run_support_blockers(action)
        if setup_blockers:
            return setup_blockers
        confirmation_blockers = _confirmation_blockers(
            action,
            confirmation_phrase=confirmation_phrase,
            confirmed_gates=confirmed_gates,
        )
        if confirmation_blockers:
            return confirmation_blockers
        return []

    confirmations = [str(item) for item in action.get("required_confirmations") or [] if item]
    if confirmations:
        return [
            "Actions with required confirmations must use the guarded action runner.",
        ]

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


def workflow_action_guarded_run_support_blockers(action: dict[str, Any]) -> list[str]:
    mode = str(action.get("mode") or "")
    if mode not in {"write", "destructive", "upgrade"}:
        return ["This action is not a guarded write, destructive, or upgrade action."]
    if str(action.get("current_availability") or "") == "not_in_scope":
        return ["This action is not in scope for the active lab profile."]
    confirmations = [str(item) for item in action.get("required_confirmations") or [] if item]
    if not confirmations:
        return ["No exact confirmation phrase is registered for this guarded action."]
    spec = get_workflow_action_execution_spec(str(action.get("action_id") or ""))
    if spec is None:
        return ["No guarded UI runner allowlist entry exists for this action yet."]
    if spec.kind == "command":
        command = action.get("command")
        if not command or command != spec.registry_command:
            return ["Registry command does not match the guarded action runner allowlist."]
        return []
    endpoint = action.get("api_endpoint")
    method = action.get("api_method") or "GET"
    if endpoint != spec.api_endpoint or str(method).upper() != spec.api_method:
        return ["Registry API endpoint does not match the guarded action runner allowlist."]
    return []


def _confirmation_blockers(
    action: dict[str, Any],
    *,
    confirmation_phrase: str | None,
    confirmed_gates: list[str] | None,
) -> list[str]:
    required_confirmations = [str(item) for item in action.get("required_confirmations") or [] if item]
    required_gates = [str(item) for item in action.get("required_gates") or [] if item]
    confirmed_gate_set = set(str(item) for item in (confirmed_gates or []) if item)
    blockers: list[str] = []
    if required_confirmations and confirmation_phrase not in required_confirmations:
        blockers.append(f"guarded workflow requires exact confirmation phrase: {required_confirmations[0]}")
    missing_gates = [gate for gate in required_gates if gate not in confirmed_gate_set]
    if missing_gates:
        blockers.append(f"guarded workflow requires confirmed gates before running: {', '.join(missing_gates)}")
    return blockers
