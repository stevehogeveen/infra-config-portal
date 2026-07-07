from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from app.providers.action_policy import ActionCategory, current_lab_action_policy
from app.services.control_actions import ACTIONS, ActionDefinition, REPO_ROOT
from app.services.lab_profiles import active_lab_profile_context
from app.services.list_utils import unique_preserving_order, unique_strings
from app.services.path_utils import path_exists, path_mtime
from app.services.workflow_action_allowlist import (
    workflow_action_guarded_run_support_blockers,
    workflow_action_run_blockers,
)
from app.services.workflow_action_run_store import (
    latest_workflow_action_run_traces_by_action,
    latest_workflow_action_run_trace,
    run_trace_to_registry_trace,
)

WorkflowCategory = Literal[
    "discover",
    "inventory",
    "plan",
    "apply",
    "verify",
    "report",
    "reset",
    "upgrade",
    "waive",
    "reclaim",
]
WorkflowMode = Literal["read_only", "write", "destructive", "upgrade", "report_only"]
WorkflowSourceType = Literal["make_target", "backend_script", "api_endpoint", "manual_guidance"]
RunTraceSourceType = Literal["live_probe", "live_cached", "historical_artifact", "test_fixture", "not_checked"]

DEFAULT_STALE_AFTER_SECONDS = 24 * 60 * 60


class WorkflowRegistryNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class WorkflowActionSeed:
    action_id: str
    label: str
    stage: str
    provider: str
    category: WorkflowCategory
    mode: WorkflowMode
    description: str
    source_type: WorkflowSourceType
    command: str | None = None
    api_endpoint: str | None = None
    api_method: str | None = None
    required_mode: str = "local-readonly or local-lab-readwrite for real lab checks"
    required_gates: tuple[str, ...] = ()
    required_confirmations: tuple[str, ...] = ()
    required_credentials: tuple[str, ...] = ()
    safety_notes: tuple[str, ...] = ()
    inputs: tuple[dict[str, Any], ...] = ()
    outputs: tuple[str, ...] = ()
    reports: tuple[str, ...] = ()
    policy_action_id: str | None = None
    policy_category: ActionCategory | None = None
    stale_after_seconds: int = DEFAULT_STALE_AFTER_SECONDS


@dataclass(frozen=True)
class WorkflowStageSeed:
    stage_id: str
    label: str
    order: int
    current_state: str
    desired_state: str
    dependencies: tuple[str, ...] = ()
    reports: tuple[str, ...] = ()


STAGE_SEEDS: tuple[WorkflowStageSeed, ...] = (
    WorkflowStageSeed(
        "lab-profile",
        "Lab Profile",
        10,
        "Active addressing profile selected and checked.",
        "Known lab profile values are valid before provider checks.",
        reports=("artifacts/codex-runs/lab-ip-profile-update-report.md",),
    ),
    WorkflowStageSeed(
        "firmware",
        "Firmware",
        20,
        "Inventory, compliance, waivers, and upgrade planning evidence.",
        "Firmware baseline is checked before major apply or rebuild work.",
        dependencies=("lab-profile",),
    ),
    WorkflowStageSeed(
        "cisco",
        "Cisco",
        30,
        "Console-first discovery, privilege, bootstrap, and readiness checks.",
        "Console access is proven before guarded network bootstrap.",
        dependencies=("lab-profile", "firmware"),
    ),
    WorkflowStageSeed(
        "ilo",
        "HPE / iLO",
        40,
        "Reachability, auth, inventory, virtual media, boot, and reset controls.",
        "iLO inventory and boot controls are known before RAID or ESXi work.",
        dependencies=("lab-profile", "firmware"),
    ),
    WorkflowStageSeed(
        "raid",
        "RAID",
        50,
        "Smart Array discovery, plan, apply gate, pending state, reset, and validation.",
        "Storage layout is planned and validated before ESXi install.",
        dependencies=("ilo",),
    ),
    WorkflowStageSeed(
        "esxi",
        "ESXi",
        60,
        "Install readiness, media URL, virtual media, one-time boot, and management checks.",
        "ESXi install and management readiness are proven after iLO and RAID gates.",
        dependencies=("ilo", "raid"),
    ),
    WorkflowStageSeed(
        "netapp",
        "NetApp",
        70,
        "Serial console, setup preview/apply gates, ONTAP upgrade center, and NFS/vCenter readiness.",
        "Planned NetApp intent and upgrade readiness remain separate from current live validation.",
        dependencies=("lab-profile", "cisco", "esxi"),
    ),
    WorkflowStageSeed(
        "vcenter",
        "vCenter",
        80,
        "VCSA media, ESXi target, NetApp datastore handoff, and install planning evidence.",
        "vCenter install planning starts only after ESXi management and NetApp NFS datastore readiness.",
        dependencies=("esxi", "netapp"),
    ),
    WorkflowStageSeed(
        "build-verification",
        "Build Verification",
        90,
        "Product certification, live-status summaries, and toolchain checks.",
        "All required stages are verified before the run is called complete.",
        dependencies=("cisco", "ilo", "raid", "esxi", "netapp", "vcenter", "firmware"),
    ),
    WorkflowStageSeed(
        "reports",
        "Reports",
        100,
        "Issue, evidence, and action-history report surfaces.",
        "Reports link back to source actions and stay evidence, not primary blockers.",
        dependencies=("build-verification",),
    ),
)

STAGE_BY_ID = {stage.stage_id: stage for stage in STAGE_SEEDS}

CONTROL_STAGE_MAP = {
    "firmware-upgrade": "firmware",
    "verification": "build-verification",
}

CONTROL_PROVIDER_MAP = {
    "lab-profile": "lab-profile",
    "cisco": "cisco",
    "ilo": "hpe-ilo",
    "raid": "raid",
    "esxi": "esxi",
    "netapp": "netapp",
    "vcenter": "vcenter",
    "firmware-upgrade": "firmware",
    "verification": "build-verification",
    "reports": "reports",
}

CREDENTIALS_BY_PROVIDER = {
    "cisco-console": "Cisco console access path and optional local enable reference.",
    "cisco-ansible": "Cisco management credential reference after SSH/SCP readiness.",
    "ilo-redfish": "iLO credential reference with values redacted.",
    "esxi-readonly": "ESXi management credential reference when ESXI_CONFIGURED=true.",
    "netapp-ontap": "NetApp console or ONTAP credential reference when configured.",
    "vcenter": "vCenter deployment and SSO credential references when configured.",
}

CATEGORY_BY_CONTROL_ACTION = {
    "cisco.discover-console": "discover",
    "cisco.reclaim-console": "reclaim",
    "commander.reclaim-serial-port": "reclaim",
    "cisco.privilege-check": "verify",
    "cisco.firmware-inventory": "inventory",
    "cisco.apply-bootstrap": "apply",
    "cisco.validate-ssh-scp": "verify",
    "cisco.save-config": "apply",
    "cisco.reload-if-needed": "reset",
    "ilo.reachability": "discover",
    "ilo.auth": "verify",
    "ilo.inventory": "inventory",
    "ilo.baseline-preview": "plan",
    "ilo.virtual-media-insert": "apply",
    "ilo.one-time-boot": "apply",
    "ilo.reset-server": "reset",
    "ilo.firmware-inventory": "inventory",
    "raid.discovery": "discover",
    "raid.plan": "plan",
    "raid.apply": "apply",
    "raid.factory-reset-preview": "plan",
    "raid.factory-reset-apply": "reset",
    "raid.pending-check": "verify",
    "raid.reset-commit": "reset",
    "raid.validate": "verify",
    "esxi.readiness": "verify",
    "esxi.iso-media-check": "verify",
    "esxi.kickstart-generation": "plan",
    "esxi.rebuild-install": "apply",
    "esxi.management-validation": "verify",
    "esxi.ssh-api-check": "verify",
    "esxi.vm-deploy-preview": "plan",
    "esxi.vm-deploy-apply": "apply",
    "esxi.vm-deploy-validate": "verify",
    "netapp.console-autodiscovery": "discover",
    "netapp.console-read-state": "verify",
    "netapp.console-login-state": "verify",
    "netapp.live-state": "verify",
    "netapp.validate-setup": "verify",
    "netapp.address-plan": "plan",
    "netapp.address-preview": "plan",
    "netapp.address-apply": "apply",
    "netapp.address-validate": "verify",
    "netapp.ha-node-diagnose": "verify",
    "netapp.factory-reset-preview": "plan",
    "netapp.factory-reset-apply": "reset",
    "netapp.factory-reset-validate": "verify",
    "netapp.setup-preview": "plan",
    "netapp.setup-apply": "apply",
    "netapp.post-setup-validation": "verify",
    "netapp.nfs-vcenter-readiness": "verify",
    "netapp.nfs-setup-preview": "plan",
    "netapp.nfs-setup-apply": "apply",
    "netapp.nfs-setup-validate": "verify",
    "netapp.iscsi-setup-preview": "plan",
    "netapp.iscsi-setup-apply": "apply",
    "netapp.iscsi-setup-validate": "verify",
    "netapp.ontap-upgrade-inventory": "inventory",
    "netapp.ontap-upgrade-plan": "plan",
    "netapp.ontap-upgrade-validate": "verify",
    "netapp.ontap-upgrade-apply": "upgrade",
    "netapp.component-firmware-inventory": "inventory",
    "vcenter.attach-esxi-preview": "plan",
    "vcenter.attach-esxi-apply": "apply",
    "vcenter.post-attach-validation": "verify",
    "vcenter.install-apply": "apply",
    "firmware.inventory": "inventory",
    "firmware.compliance-check": "verify",
    "firmware.waiver-check": "waive",
    "firmware.package-inventory": "inventory",
    "firmware.create-waiver": "waive",
    "firmware.upgrade-plan": "upgrade",
    "firmware.upgrade-apply-placeholder": "upgrade",
    "commander.force-live-discovery": "discover",
    "commander.ignore-cached-artifact": "verify",
    "commander.run-live-check": "verify",
    "provider-smoke.real-lab": "verify",
    "build-verification.run-full": "verify",
    "build-verification.run-scoped": "verify",
    "build-verification.export-certification-report": "report",
}

CONTROL_ACTION_API_ENDPOINTS: dict[str, tuple[str, str]] = {
    "cisco.discover-console": ("/api/v1/providers/cisco-console/prompt-readiness", "POST"),
    "cisco.firmware-inventory": ("/api/v1/lab/firmware-inventory", "GET"),
    "ilo.firmware-inventory": ("/api/v1/lab/firmware-inventory", "GET"),
    "esxi.installer-boot-detection": ("/api/v1/providers/ilo-redfish/esxi-install-readiness", "GET"),
    "esxi.iso-media-check": ("/api/v1/media-inventory", "GET"),
    "esxi.management-readiness": ("/api/v1/providers/ilo-redfish/esxi-install-readiness", "GET"),
    "esxi.post-recovery-validation": ("/api/v1/providers/esxi-readonly/post-recovery-validation", "POST"),
    "esxi.ssh-api-check": ("/api/v1/providers/esxi-readonly/probe", "POST"),
    "netapp.address-plan": ("/api/v1/providers/netapp-ontap/address-plan", "GET"),
    "netapp.address-preview": ("/api/v1/providers/netapp-ontap/address-preview", "GET"),
    "netapp.address-validate": ("/api/v1/providers/netapp-ontap/address-validate", "POST"),
    "netapp.console-autodiscovery": ("/api/v1/providers/netapp-ontap/console-discovery", "POST"),
    "netapp.console-read-state": ("/api/v1/providers/netapp-ontap/console-read-state", "POST"),
    "netapp.nfs-vcenter-readiness": ("/api/v1/providers/netapp-ontap/nfs-vcenter-readiness", "GET"),
    "netapp.post-setup-validation": ("/api/v1/providers/netapp-ontap/post-setup-validation", "POST"),
}

EXTRA_ACTIONS: tuple[WorkflowActionSeed, ...] = (
    WorkflowActionSeed(
        "lab-profile.view-active",
        "View Active Profile",
        "lab-profile",
        "lab-profile",
        "inventory",
        "read_only",
        "Read the active lab profile, known lab profile, and non-secret configured flags.",
        "api_endpoint",
        api_endpoint="/api/v1/lab/profiles",
        api_method="GET",
        outputs=("active lab profile", "runtime profile", "subnet capability options"),
        reports=("artifacts/codex-runs/lab-ip-profile-update-report.md",),
    ),
    WorkflowActionSeed(
        "lab-profile.validate-ip-profile",
        "Validate IP Profile",
        "lab-profile",
        "lab-profile",
        "verify",
        "read_only",
        "Run the lab IP profile validation used by Build Verification.",
        "api_endpoint",
        api_endpoint="/api/v1/lab/build-verification",
        api_method="GET",
        command="make provider-lab-build-verification-live",
        outputs=("lab IP profile report", "stale or invalid value findings"),
        reports=(
            "artifacts/codex-runs/lab-ip-profile-update-report.md",
            "artifacts/codex-runs/lab-ip-profile-hardening-report.md",
        ),
    ),
    WorkflowActionSeed(
        "cisco.setup-readiness",
        "Cisco Setup Readiness",
        "cisco",
        "cisco",
        "verify",
        "read_only",
        "Read Cisco setup wizard, console, management, and next safe action readiness.",
        "api_endpoint",
        api_endpoint="/api/v1/providers/cisco/setup-readiness",
        api_method="GET",
        outputs=("setup phase", "console readiness", "management readiness", "next safe action"),
        reports=("artifacts/codex-runs/cisco-real-lab-readiness-report.md",),
    ),
    WorkflowActionSeed(
        "cisco.ssh-readonly-probe",
        "Cisco SSH Read-Only Probe",
        "cisco",
        "cisco",
        "verify",
        "read_only",
        "Run fixed read-only Cisco SSH show commands and capture parsed evidence for current-to-intent review.",
        "api_endpoint",
        command="make provider-lab-cisco-console-ethernet-readiness",
        api_endpoint="/api/v1/providers/cisco-ansible/probe",
        api_method="POST",
        outputs=("show version", "show interfaces status", "show vlan brief", "safe show-command evidence"),
        reports=("artifacts/codex-runs/cisco-ssh-validation-report.md",),
        safety_notes=("No configure terminal, write memory, reload, copy, erase, or configuration command is run.",),
    ),
    WorkflowActionSeed(
        "cisco.current-intent-diff",
        "Cisco Current Intent Diff",
        "cisco",
        "cisco",
        "verify",
        "read_only",
        "Compare parsed live Cisco VLAN/interface state against intended lab VLAN and port policy.",
        "api_endpoint",
        api_endpoint="/api/v1/providers/cisco/current-intent-diff",
        api_method="POST",
        outputs=("VLAN drift", "interface drift", "not-checked BPDU/ACL lanes", "candidate next action"),
        reports=(
            "artifacts/codex-runs/cisco-current-intent-diff-report.md",
            "artifacts/codex-runs/cisco-current-intent-diff-redacted.json",
        ),
        safety_notes=("No configure terminal, write memory, reload, copy, erase, or remediation command is run.",),
    ),
    WorkflowActionSeed(
        "ilo.setup-plan-preview",
        "iLO Setup Plan Preview",
        "ilo",
        "ilo",
        "plan",
        "read_only",
        "Preview desired iLO setup intent and blocked apply gates without applying settings.",
        "api_endpoint",
        api_endpoint="/api/v1/providers/ilo-redfish/setup-plan-preview",
        api_method="GET",
        outputs=("desired setup intent", "plan preview", "blocked apply gates"),
        reports=("artifacts/codex-runs/hpe-full-rebuild-ilo-report.md",),
    ),
    WorkflowActionSeed(
        "raid.debug",
        "Debug",
        "raid",
        "raid",
        "verify",
        "read_only",
        "Collect read-only Smart Array debug evidence for blocked RAID planning.",
        "make_target",
        command="make -C app provider-lab-hpe-raid-debug",
        reports=("artifacts/codex-runs/hpe-raid-redfish-debug-report.md",),
        required_credentials=("iLO credential reference with values redacted.",),
    ),
    WorkflowActionSeed(
        "raid.factory-reset-preview",
        "Preview RAID Factory Reset",
        "raid",
        "raid",
        "plan",
        "read_only",
        "Preview the explicit HPE logical-drive delete/recreate lane without sending destructive commands.",
        "api_endpoint",
        api_endpoint="/api/v1/providers/ilo-redfish/hpe-raid-factory-reset-preview",
        api_method="GET",
        outputs=("logical drives to delete", "recreate payload", "missing executor status"),
        reports=("artifacts/codex-runs/hpe-raid-factory-reset-plan-report.md",),
        required_credentials=("iLO credential reference with values redacted.",),
    ),
    WorkflowActionSeed(
        "raid.factory-reset-apply",
        "Apply RAID Factory Reset",
        "raid",
        "raid",
        "reset",
        "destructive",
        "Guarded HPE logical-drive delete/recreate lane; currently refuses until the delete executor is implemented and proven.",
        "api_endpoint",
        api_endpoint="/api/v1/providers/ilo-redfish/hpe-raid-factory-reset-apply",
        api_method="POST",
        outputs=("factory reset refusal report", "not-attempted destructive operations", "next build action"),
        reports=("artifacts/codex-runs/hpe-raid-factory-reset-apply-report.md",),
        required_gates=(
            "LAB_ALLOW_FACTORY_RESET=true",
            "HPE_RAID_ALLOW_FACTORY_RESET=true",
        ),
        required_confirmations=("FACTORY RESET HPE RAID",),
        required_credentials=("iLO credential reference with values redacted.",),
    ),
    WorkflowActionSeed(
        "esxi.virtual-media-insert",
        "Virtual Media Insert",
        "esxi",
        "esxi",
        "apply",
        "write",
        "Insert validated ESXi install media through the guarded iLO virtual media path.",
        "make_target",
        command="make provider-lab-esxi-insert-virtual-media",
        reports=("artifacts/codex-runs/esxi-virtual-media-report.md",),
        required_mode="local-lab-readwrite",
        required_confirmations=("INSERT ESXI VIRTUAL MEDIA",),
        required_credentials=("iLO credential reference with values redacted.",),
        policy_action_id="ilo.virtual-media",
        policy_category=ActionCategory.VIRTUAL_MEDIA,
    ),
    WorkflowActionSeed(
        "esxi.one-time-boot",
        "One-Time Boot",
        "esxi",
        "esxi",
        "apply",
        "write",
        "Set the one-time boot target for ESXi install media after media validation.",
        "make_target",
        command="make provider-lab-esxi-one-time-boot",
        reports=("artifacts/codex-runs/esxi-one-time-boot-report.md",),
        required_mode="local-lab-readwrite",
        required_confirmations=("SET ONE TIME ESXI BOOT",),
        required_credentials=("iLO credential reference with values redacted.",),
        policy_action_id="ilo.boot-settings",
        policy_category=ActionCategory.BOOT_CONFIG,
    ),
    WorkflowActionSeed(
        "esxi.installer-boot-detection",
        "Installer Boot Detection",
        "esxi",
        "esxi",
        "verify",
        "read_only",
        "Detect whether the ESXi installer boot path reached the expected state.",
        "api_endpoint",
        command="make provider-lab-esxi-detect-installer",
        api_endpoint="/api/v1/providers/ilo-redfish/esxi-install-readiness",
        api_method="GET",
        reports=("artifacts/codex-runs/esxi-installer-boot-report.md",),
        required_credentials=("iLO and ESXi readiness references with values redacted.",),
    ),
    WorkflowActionSeed(
        "esxi.management-readiness",
        "Management Readiness",
        "esxi",
        "esxi",
        "verify",
        "read_only",
        "Validate ESXi management readiness after install or rebuild.",
        "api_endpoint",
        command="make provider-lab-esxi-detect-installer",
        api_endpoint="/api/v1/providers/ilo-redfish/esxi-install-readiness",
        api_method="GET",
        reports=("artifacts/codex-runs/esxi-management-readiness-report.md",),
        required_gates=("ESXI_CONFIGURED=true",),
        required_credentials=("ESXi management credential reference when ESXI_CONFIGURED=true.",),
    ),
    WorkflowActionSeed(
        "esxi.recover-management",
        "ESXi Recover Management",
        "esxi",
        "esxi",
        "apply",
        "destructive",
        "Diagnose ESXi reachability and run guarded iLO power-on recovery only after explicit gates pass.",
        "make_target",
        command="make provider-lab-esxi-recover-management",
        reports=("artifacts/codex-runs/esxi-reachability-remediation-report.md",),
        required_mode="local-lab-readwrite",
        required_gates=("iLO Redfish auth ready", "ESXi HTTPS unreachable", "host power state verified Off", "ESXI_RECOVERY_APPLY=true"),
        required_confirmations=("RECOVER ESXI MANAGEMENT",),
        required_credentials=("iLO credential reference with values redacted.",),
        policy_action_id="ilo.power-action",
        policy_category=ActionCategory.POWER_ACTION,
    ),
    WorkflowActionSeed(
        "esxi.post-recovery-validation",
        "ESXi Post-Recovery Validation",
        "esxi",
        "esxi",
        "verify",
        "read_only",
        "Validate ESXi management HTTPS and SSH reachability after recovery.",
        "make_target",
        command="make provider-lab-esxi-post-recovery-validation",
        reports=("artifacts/codex-runs/esxi-post-recovery-validation-report.md",),
        required_gates=("ESXI_CONFIGURED=true",),
        required_credentials=("ESXi management credential reference with values redacted.",),
    ),
    WorkflowActionSeed(
        "esxi.netapp-datastore-preview",
        "ESXi Mount NetApp Datastore Preview",
        "esxi",
        "esxi",
        "plan",
        "read_only",
        "Preview the NetApp NFS datastore mount target and govc command.",
        "make_target",
        command="make provider-lab-esxi-netapp-datastore-preview",
        reports=("artifacts/codex-runs/esxi-netapp-nfs-datastore-preview-report.md",),
        required_gates=("ESXI_CONFIGURED=true", "NetApp NFS ready"),
        required_credentials=("ESXi management credential reference with values redacted.",),
    ),
    WorkflowActionSeed(
        "esxi.netapp-datastore-apply",
        "ESXi Mount NetApp Datastore",
        "esxi",
        "esxi",
        "apply",
        "write",
        "Mount the NetApp NFS datastore on direct ESXi through guarded govc datastore.create.",
        "make_target",
        command="make provider-lab-esxi-netapp-datastore-apply",
        reports=("artifacts/codex-runs/esxi-netapp-nfs-datastore-apply-report.md",),
        required_mode="local-lab-readwrite",
        required_gates=("fresh datastore preview", "ESXi management reachable", "ESXI_NETAPP_DATASTORE_APPLY=true"),
        required_confirmations=("MOUNT NETAPP NFS DATASTORE",),
        required_credentials=("ESXi management credential reference with values redacted.",),
        policy_action_id="esxi.datastore-vswitch-vmkernel",
        policy_category=ActionCategory.STORAGE_CONFIG,
    ),
    WorkflowActionSeed(
        "esxi.netapp-datastore-validate",
        "ESXi Validate NetApp Datastore",
        "esxi",
        "esxi",
        "verify",
        "read_only",
        "Validate the NetApp NFS datastore is visible and accessible on ESXi.",
        "make_target",
        command="make provider-lab-esxi-netapp-datastore-validate",
        reports=("artifacts/codex-runs/esxi-netapp-nfs-datastore-validation-report.md",),
        required_gates=("ESXI_CONFIGURED=true",),
        required_credentials=("ESXi management credential reference with values redacted.",),
    ),
    WorkflowActionSeed(
        "esxi.iscsi-datastore-preview",
        "ESXi Preview iSCSI Datastore",
        "esxi",
        "esxi",
        "plan",
        "read_only",
        "Preview ESXi iSCSI adapter, session, LUN/device, and VMFS datastore evidence without writes.",
        "api_endpoint",
        api_endpoint="/api/v1/providers/esxi-readonly/iscsi-datastore-preview",
        api_method="POST",
        outputs=("ESXi iSCSI adapter proof", "target session proof", "VMFS datastore visibility"),
        reports=("artifacts/codex-runs/esxi-iscsi-datastore-preview-report.md",),
        required_gates=("ESXI_CONFIGURED=true", "NetApp iSCSI validation ready"),
        required_credentials=("ESXi management credential reference with values redacted.",),
    ),
    WorkflowActionSeed(
        "esxi.iscsi-datastore-validate",
        "ESXi Validate iSCSI Datastore",
        "esxi",
        "esxi",
        "verify",
        "read_only",
        "Validate ESXi can see the intended iSCSI target/session and VMFS datastore using read-only esxcli checks.",
        "api_endpoint",
        api_endpoint="/api/v1/providers/esxi-readonly/iscsi-datastore-validate",
        api_method="POST",
        outputs=("ESXi iSCSI adapter proof", "target session proof", "VMFS datastore visibility"),
        reports=("artifacts/codex-runs/esxi-iscsi-datastore-validation-report.md",),
        required_gates=("ESXI_CONFIGURED=true",),
        required_credentials=("ESXi management credential reference with values redacted.",),
    ),
    WorkflowActionSeed(
        "netapp.iscsi-setup-preview",
        "Preview iSCSI Setup",
        "netapp",
        "netapp-ontap",
        "plan",
        "read_only",
        "Preview iSCSI service, LIF, LUN, igroup, initiator, and datastore intent without creating anything.",
        "api_endpoint",
        api_endpoint="/api/v1/providers/netapp-ontap/iscsi-setup-preview",
        api_method="GET",
        outputs=("iSCSI LIF readiness", "planned LUN", "planned igroup", "future datastore target"),
        reports=("artifacts/codex-runs/netapp-iscsi-setup-preview-report.md",),
        required_credentials=("NetApp API credential reference with values redacted.",),
    ),
    WorkflowActionSeed(
        "netapp.iscsi-setup-validate",
        "Validate iSCSI Setup",
        "netapp",
        "netapp-ontap",
        "verify",
        "read_only",
        "Validate iSCSI protocol readiness and confirm whether ONTAP LUN, igroup, and map objects exist.",
        "api_endpoint",
        api_endpoint="/api/v1/providers/netapp-ontap/iscsi-setup-validate",
        api_method="POST",
        outputs=("iSCSI service proof", "TCP/3260 LIF proof", "LUN/igroup/map inventory"),
        reports=("artifacts/codex-runs/netapp-iscsi-setup-validation-report.md",),
        required_credentials=("NetApp API credential reference with values redacted.",),
    ),
    WorkflowActionSeed(
        "netapp.iscsi-setup-apply",
        "Apply iSCSI Setup",
        "netapp",
        "netapp-ontap",
        "apply",
        "write",
        "Create missing ONTAP iSCSI LUN, igroup, and LUN map objects after explicit real-lab apply gates pass.",
        "api_endpoint",
        api_endpoint="/api/v1/providers/netapp-ontap/iscsi-setup-apply",
        api_method="POST",
        outputs=("LUN create/check", "igroup create/check", "LUN map create/check"),
        reports=("artifacts/codex-runs/netapp-iscsi-setup-apply-report.md",),
        required_gates=(
            "PROVIDER_MODE=local-lab-readwrite",
            "NETAPP_ISCSI_SETUP_APPLY=true",
            'NETAPP_ISCSI_SETUP_CONFIRM="APPLY NETAPP ISCSI SETUP"',
            "NETAPP_ISCSI_SETUP_ALLOW_STORAGE_CREATE=true",
        ),
        required_confirmations=("APPLY NETAPP ISCSI SETUP",),
        required_credentials=("NetApp API credential reference with values redacted.",),
        policy_action_id="netapp.iscsi-setup",
        policy_category=ActionCategory.STORAGE_CONFIG,
    ),
    WorkflowActionSeed(
        "esxi.vm-deploy-preview",
        "VM Deploy Preview",
        "esxi",
        "esxi",
        "plan",
        "read_only",
        "Preview direct ESXi OVF deployment and datastore placement without importing a VM.",
        "api_endpoint",
        command="make provider-lab-esxi-vm-deploy-preview",
        api_endpoint="/api/v1/providers/esxi-readonly/vm-deploy-preview",
        api_method="POST",
        reports=("artifacts/codex-runs/esxi-vm-deploy-preview-report.md",),
        required_gates=("ESXI_CONFIGURED=true",),
        required_credentials=("ESXi management credential reference with values redacted.",),
    ),
    WorkflowActionSeed(
        "esxi.vm-deploy-apply",
        "VM Deploy Apply",
        "esxi",
        "esxi",
        "apply",
        "write",
        "Guarded direct ESXi govc import.ovf lane with explicit datastore and power-on gates.",
        "api_endpoint",
        command="make provider-lab-esxi-vm-deploy-apply",
        api_endpoint="/api/v1/providers/esxi-readonly/vm-deploy-apply",
        api_method="POST",
        reports=("artifacts/codex-runs/esxi-vm-deploy-apply-report.md",),
        required_mode="local-lab-readwrite",
        required_gates=("fresh VM deploy preview", "target datastore visible", "VM_DEPLOY_APPLY=true", "VM_DEPLOY_ALLOW_CREATE=true"),
        required_confirmations=("DEPLOY ESXI OVF VM",),
        required_credentials=("ESXi management credential reference with values redacted.",),
        safety_notes=("OVF import can take several minutes on real hardware; keep this run open and do not resubmit while it is running.",),
        policy_action_id="vm.deploy-ovf",
        policy_category=ActionCategory.VM_DEPLOY,
    ),
    WorkflowActionSeed(
        "esxi.vm-deploy-validate",
        "VM Deploy Validate",
        "esxi",
        "esxi",
        "verify",
        "read_only",
        "Validate direct ESXi VM and datastore visibility with read-only govc checks.",
        "api_endpoint",
        command="make provider-lab-esxi-vm-deploy-validate",
        api_endpoint="/api/v1/providers/esxi-readonly/vm-deploy-validate",
        api_method="POST",
        reports=("artifacts/codex-runs/esxi-vm-deploy-validation-report.md",),
        required_gates=("ESXI_CONFIGURED=true",),
        required_credentials=("ESXi management credential reference with values redacted.",),
    ),
    WorkflowActionSeed(
        "netapp.serial-console-discovery",
        "Serial Console Discovery",
        "netapp",
        "netapp",
        "discover",
        "read_only",
        "Run shared serial console discovery before NetApp-specific console autodiscovery.",
        "make_target",
        command="make provider-lab-serial-console-discovery",
        reports=(
            "artifacts/codex-runs/serial-console-discovery-report.md",
            "artifacts/codex-runs/serial-console-discovery-redacted.json",
        ),
    ),
    WorkflowActionSeed(
        "vcenter-netapp.readiness",
        "vCenter-NetApp Readiness",
        "netapp",
        "vcenter-netapp",
        "verify",
        "read_only",
        "Evaluate vCenter/govc, ESXi management, NetApp cluster, and planned NFS prerequisites for a future datastore lane.",
        "api_endpoint",
        command="make provider-lab-vcenter-netapp-readiness",
        api_endpoint="/api/v1/lab/vcenter-netapp/readiness",
        api_method="GET",
        reports=("artifacts/codex-runs/vcenter-netapp-readiness-report.md",),
        required_credentials=(
            "vCenter credential reference with values redacted when configured.",
            "NetApp API credential reference with values redacted when configured.",
        ),
    ),
    WorkflowActionSeed(
        "vcenter-netapp.datastore-plan",
        "vCenter-NetApp Datastore Plan",
        "netapp",
        "vcenter-netapp",
        "plan",
        "read_only",
        "Generate the preview-only NFS datastore add plan and command preview without mounting storage.",
        "api_endpoint",
        command="make provider-lab-vcenter-netapp-datastore-plan",
        api_endpoint="/api/v1/lab/vcenter-netapp/datastore-plan",
        api_method="GET",
        reports=("artifacts/codex-runs/vcenter-netapp-datastore-plan-report.md",),
        required_credentials=(
            "vCenter credential reference with values redacted when configured.",
            "NetApp API credential reference with values redacted when configured.",
        ),
    ),
    WorkflowActionSeed(
        "vcenter.install-readiness",
        "vCenter Install Readiness",
        "vcenter",
        "vcenter",
        "verify",
        "read_only",
        "Evaluate VCSA media, ESXi reachability, NetApp datastore prerequisites, and missing vCenter values.",
        "make_target",
        command="make provider-lab-vcenter-install-readiness",
        reports=("artifacts/codex-runs/vcenter-install-readiness-report.md",),
        required_credentials=(
            "vCenter deployment credential reference with values redacted when configured.",
            "ESXi management credential reference with values redacted.",
        ),
    ),
    WorkflowActionSeed(
        "vcenter.install-plan",
        "vCenter Install Plan",
        "vcenter",
        "vcenter",
        "plan",
        "read_only",
        "Generate the preview-only VCSA deployment plan after prerequisites are ready.",
        "make_target",
        command="make provider-lab-vcenter-install-plan",
        reports=("artifacts/codex-runs/vcenter-install-plan-report.md",),
        required_gates=("ESXi management reachable", "NetApp datastore ready", "VCSA ISO available"),
        required_credentials=(
            "vCenter deployment credential reference with values redacted when configured.",
            "ESXi management credential reference with values redacted.",
        ),
    ),
    WorkflowActionSeed(
        "vcenter.install-preview",
        "vCenter Preview Deploy",
        "vcenter",
        "vcenter",
        "preview",
        "read_only",
        "Generate the redacted VCSA deploy preview without starting deployment.",
        "make_target",
        command="make provider-lab-vcenter-install-preview",
        reports=("artifacts/codex-runs/vcenter-install-preview-report.md",),
        required_gates=("ESXi management reachable", "NetApp datastore ready", "VCSA ISO available"),
        required_credentials=(
            "Local-only VCSA root and SSO credential references with values redacted.",
            "ESXi management credential reference with values redacted.",
        ),
    ),
    WorkflowActionSeed(
        "vcenter-netapp.datastore-apply-placeholder",
        "Future Datastore Apply",
        "netapp",
        "vcenter-netapp",
        "apply",
        "write",
        "Future write-capable datastore mount lane. It is intentionally not runnable until guarded apply gates are implemented.",
        "manual_guidance",
        required_mode="local-lab-readwrite",
        required_gates=("NETAPP_CONFIGURED live verification", "VCENTER_CONFIGURED=true", "fresh datastore plan"),
        required_confirmations=("APPLY VCENTER NETAPP DATASTORE",),
        required_credentials=(
            "vCenter credential reference with values redacted.",
            "NetApp API credential reference with values redacted.",
        ),
        safety_notes=(
            "Write-capable placeholder only; no registry runner or backend apply endpoint exists.",
            "Future apply must require fresh discovery, approval, audit logging, and rollback notes.",
        ),
    ),
    WorkflowActionSeed(
        "provider-smoke.real-lab",
        "Run Real Provider Smoke",
        "build-verification",
        "provider-smoke",
        "verify",
        "read_only",
        "Run real provider smoke checks and fail fast if provider mode is still mock.",
        "backend_script",
        command=(
            "PROVIDER_MODE=local-lab-readwrite PROVIDER_SMOKE_REQUIRE_REAL=true "
            "PYTHONPATH=app\\backend app\\backend\\.venv\\Scripts\\python.exe app\\backend\\scripts\\provider_smoke.py"
        ),
        outputs=("real provider status", "TCP preflight", "read-only provider probes", "redacted smoke report"),
        reports=("artifacts/real-lab/provider-smoke-latest.md",),
        safety_notes=("No destructive or write action is run by provider smoke.",),
    ),
    WorkflowActionSeed(
        "operator-readonly-sweep.real-lab",
        "Run Operator Read-Only Sweep",
        "build-verification",
        "operator-sweep",
        "verify",
        "read_only",
        "Run the main operator read-only workflow actions against the active real-lab profile, including storage protocol validation and scenario skips.",
        "backend_script",
        command=(
            "PROVIDER_MODE=local-lab-readwrite PYTHONPATH=app\\backend "
            "app\\backend\\.venv\\Scripts\\python.exe app\\backend\\scripts\\operator_readonly_sweep.py"
        ),
        outputs=("read-only workflow action results", "scenario skips", "trace artifact links", "redacted sweep report"),
        reports=("artifacts/real-lab/operator-readonly-sweep-latest.md",),
        safety_notes=("No destructive, write, reset, create, or upgrade action is run by the operator read-only sweep.",),
    ),
    WorkflowActionSeed(
        "build-verification.live-status",
        "Live Status / Current State",
        "build-verification",
        "build-verification",
        "verify",
        "read_only",
        "Refresh provider live-status/current-state evidence without treating mock state as real.",
        "make_target",
        command="make provider-lab-live-status",
        reports=(
            "artifacts/codex-runs/provider-lab-live-status-report.md",
            "artifacts/codex-runs/provider-lab-live-status-redacted.json",
        ),
    ),
    WorkflowActionSeed(
        "lab-validation.summary",
        "Lab Validation Summary",
        "build-verification",
        "lab-validation",
        "report",
        "read_only",
        "Generate the Lab Validation / Handoff summary with login hints, proof links, and next actions.",
        "api_endpoint",
        command="make provider-lab-validation",
        api_endpoint="/api/v1/lab/validation",
        api_method="GET",
        reports=(
            "artifacts/codex-runs/lab-validation-handoff-report.md",
            "artifacts/codex-runs/lab-validation-summary-redacted.json",
        ),
    ),
    WorkflowActionSeed(
        "full-lab.validation",
        "Run Full Lab Validation",
        "build-verification",
        "full-lab",
        "verify",
        "read_only",
        "Run the existing Lab Validation / Handoff workflow and refresh proof links without provider writes.",
        "api_endpoint",
        command="make provider-lab-validation",
        api_endpoint="/api/v1/lab/validation",
        api_method="GET",
        reports=(
            "artifacts/codex-runs/lab-validation-handoff-report.md",
            "artifacts/codex-runs/lab-validation-summary-redacted.json",
        ),
        safety_notes=("No destructive or write action is run by this validation workflow.",),
    ),
    WorkflowActionSeed(
        "full-lab.build-plan",
        "Run Full Lab Build Plan",
        "build-verification",
        "full-lab",
        "plan",
        "read_only",
        "Generate the existing full lab rebuild summary as a build plan surface without applying changes.",
        "api_endpoint",
        command="make provider-lab-full-rebuild-summary",
        api_endpoint="/api/v1/lab/full-rebuild-summary",
        api_method="GET",
        reports=(
            "artifacts/codex-runs/full-device-rebuild-baseline-report.md",
            "artifacts/codex-runs/full-device-rebuild-4h-report.md",
        ),
        safety_notes=("Summary/report only; rebuild execution remains a separate guarded workflow.",),
    ),
    WorkflowActionSeed(
        "full-lab.repair",
        "Run Full Lab Repair",
        "build-verification",
        "full-lab",
        "plan",
        "report_only",
        "Generate golden-state drift and repair guidance that links to existing stage-specific actions.",
        "api_endpoint",
        command="make provider-lab-golden-state",
        api_endpoint="/api/v1/lab/golden-state",
        api_method="GET",
        reports=(
            "artifacts/codex-runs/golden-state-productization-report.md",
            "artifacts/codex-runs/golden-state-summary-redacted.json",
        ),
        safety_notes=("Report-only repair guidance; row repair actions use existing guarded workflow entries.",),
    ),
    WorkflowActionSeed(
        "full-lab.handoff-report",
        "Generate Handoff Report",
        "reports",
        "full-lab",
        "report",
        "report_only",
        "Write the golden-state operator handoff report from redacted evidence and configured status only.",
        "api_endpoint",
        command="make provider-lab-golden-state",
        api_endpoint="/api/v1/lab/golden-state",
        api_method="GET",
        reports=(
            "artifacts/codex-runs/golden-state-productization-report.md",
            "artifacts/codex-runs/golden-state-summary-redacted.json",
        ),
        safety_notes=("No hardware workflow or provider write is run by this report action.",),
    ),
    WorkflowActionSeed(
        "build-verification.toolchain-check",
        "Toolchain Check",
        "build-verification",
        "toolchain",
        "verify",
        "read_only",
        "Check required local provider tools without contacting infrastructure.",
        "make_target",
        command="make provider-lab-toolchain-check",
        reports=("artifacts/codex-runs/toolchain-availability-report.md",),
    ),
    WorkflowActionSeed(
        "reports.issue-center",
        "Report Center / Issues",
        "reports",
        "reports",
        "report",
        "report_only",
        "Read the normalized Report Center issue list and evidence groupings.",
        "api_endpoint",
        api_endpoint="/api/v1/reports/issues",
        api_method="GET",
        required_mode="mock or local provider mode",
        outputs=("issue cards", "source summaries", "evidence artifact links"),
    ),
    WorkflowActionSeed(
        "reports.summary",
        "Report Summary",
        "reports",
        "reports",
        "report",
        "report_only",
        "Read compact report counts and page badges.",
        "api_endpoint",
        api_endpoint="/api/v1/reports/summary",
        api_method="GET",
        required_mode="mock or local provider mode",
        outputs=("report counts", "page badges", "top issues"),
    ),
)


def list_workflow_actions() -> list[dict[str, Any]]:
    return _build_registry()["actions"]


def list_workflow_stages() -> list[dict[str, Any]]:
    return _build_registry()["stages"]


def get_workflow_action(action_id: str) -> dict[str, Any]:
    for action in list_workflow_actions():
        if action["action_id"] == action_id:
            return action
    raise WorkflowRegistryNotFoundError(action_id)


def workflow_action_exists(action_id: str) -> bool:
    return any(seed.action_id == action_id for seed in _workflow_action_seeds())


def get_workflow_stage(stage_id: str) -> dict[str, Any]:
    for stage in list_workflow_stages():
        if stage["stage_id"] == stage_id:
            return stage
    raise WorkflowRegistryNotFoundError(stage_id)


def list_workflow_actions_for_stage(stage_id: str) -> list[dict[str, Any]]:
    stage = get_workflow_stage(stage_id)
    return list(stage["actions"])


def find_workflow_action_for_issue(issue: dict[str, Any]) -> dict[str, str | None]:
    actions = list_workflow_actions()
    report_paths = _unique(
        [
            *_issue_report_values(issue.get("source_report")),
            *_issue_report_values(issue.get("evidence_artifacts")),
        ]
    )
    for report_path in report_paths:
        if not report_path:
            continue
        for action in actions:
            if report_path in set(action.get("reports") or []):
                return _issue_link(action)

    source = str(issue.get("source") or "")
    source_stage = str(issue.get("source_stage") or "")
    candidates = [
        action
        for action in actions
        if action.get("stage") == _stage_for_report_source(source)
        or action.get("provider") == source
    ]
    for action in candidates:
        action_id = str(action.get("action_id") or "")
        if source_stage and source_stage.replace("_", "-") in action_id:
            return _issue_link(action)
    if candidates:
        return _issue_link(candidates[0])
    return {
        "source_stage_id": _stage_for_report_source(source),
        "source_stage_label": STAGE_BY_ID.get(_stage_for_report_source(source), None).label
        if _stage_for_report_source(source) in STAGE_BY_ID
        else None,
        "source_action_id": None,
        "source_action_label": None,
        "source_action_link": None,
    }


def _build_registry() -> dict[str, list[dict[str, Any]]]:
    seeds = _workflow_action_seeds()
    latest_runs = latest_workflow_action_run_traces_by_action()
    actions = [_action_read(seed, latest_runs.get(seed.action_id), lookup_latest=False) for seed in seeds]
    actions.sort(key=lambda action: (STAGE_BY_ID[action["stage"]].order, action["action_id"]))
    stages = [_stage_read(stage_seed, actions) for stage_seed in STAGE_SEEDS]
    return {"actions": actions, "stages": stages}


def _workflow_action_seeds() -> list[WorkflowActionSeed]:
    seeds = [_seed_from_control_action(action) for action in ACTIONS]
    seeds.extend(EXTRA_ACTIONS)
    return _dedupe_seeds(seeds)


def _seed_from_control_action(action: ActionDefinition) -> WorkflowActionSeed:
    stage_id = CONTROL_STAGE_MAP.get(action.section_id, action.section_id)
    mode = _mode_from_control_classification(action.classification)
    report = (action.report,) if action.report else ()
    endpoint_override = CONTROL_ACTION_API_ENDPOINTS.get(action.id)
    api_endpoint = endpoint_override[0] if endpoint_override else action.endpoint
    api_method = endpoint_override[1] if endpoint_override else action.method
    return WorkflowActionSeed(
        action_id=action.id,
        label=action.label,
        stage=stage_id,
        provider=CONTROL_PROVIDER_MAP.get(action.section_id, action.section_id),
        category=CATEGORY_BY_CONTROL_ACTION.get(action.id, _category_from_action(action)),
        mode=mode,
        description=action.description,
        source_type=_source_type_for_action(action),
        command=action.command,
        api_endpoint=api_endpoint,
        api_method=api_method,
        required_mode=_required_mode_for_mode(mode),
        required_gates=action.required_flags,
        required_confirmations=action.required_confirmations,
        required_credentials=_credentials_for_provider_ids(action.provider_ids),
        safety_notes=_safety_notes_for_action(action, mode),
        inputs=tuple(
            {
                "name": item.name,
                "label": item.label,
                "required": item.required,
                "secret": item.secret,
                "description": item.description,
            }
            for item in action.required_inputs
        ),
        outputs=_outputs_for_action(action),
        reports=report,
        policy_action_id=action.policy_action_id,
        policy_category=action.policy_category,
    )


def _action_read(
    seed: WorkflowActionSeed,
    latest_run: dict[str, Any] | None = None,
    *,
    lookup_latest: bool = True,
) -> dict[str, Any]:
    blockers = _blockers_for_seed(seed)
    not_in_scope_reason = _not_in_scope_reason_for_seed(seed)
    if latest_run is None and lookup_latest:
        latest_run = latest_workflow_action_run_trace(seed.action_id)
    latest_report_artifacts = _workflow_report_artifacts(latest_run)
    reports = _unique(
        [
            *list(seed.reports),
            *latest_report_artifacts,
        ]
    )
    existing_reports = _existing_reports(reports)
    last_report = (
        str(latest_run.get("trace_artifact"))
        if latest_run and latest_run.get("trace_artifact")
        else _latest_report(existing_reports)
    )
    last_status = (
        str(latest_run.get("status"))
        if latest_run and latest_run.get("status")
        else "report_available"
        if last_report
        else "not_checked"
    )
    runner_action = _runner_action_probe(seed)
    ui_run_blockers = workflow_action_run_blockers(runner_action)
    if not_in_scope_reason:
        ui_run_blockers = _unique([not_in_scope_reason, *ui_run_blockers])
    ui_run_supported = not ui_run_blockers
    guarded_run_blockers = workflow_action_guarded_run_support_blockers(runner_action)
    guarded_run_supported = not guarded_run_blockers
    availability = (
        "not_in_scope"
        if not_in_scope_reason
        else "blocked"
        if blockers
        else "available"
        if ui_run_supported
        else _availability_for_seed(seed)
    )
    trace = _run_trace(seed, last_report, blockers, availability, latest_run)
    evidence_artifacts = _unique(
        [
            *existing_reports,
            *latest_report_artifacts,
            *([str(latest_run.get("trace_artifact"))] if latest_run and latest_run.get("trace_artifact") else []),
        ]
    )
    return {
        "action_id": seed.action_id,
        "label": seed.label,
        "stage": seed.stage,
        "stage_label": STAGE_BY_ID[seed.stage].label,
        "provider": seed.provider,
        "category": seed.category,
        "mode": seed.mode,
        "description": seed.description,
        "source_type": seed.source_type,
        "command": seed.command,
        "api_endpoint": seed.api_endpoint,
        "api_method": seed.api_method,
        "required_mode": seed.required_mode,
        "required_gates": list(seed.required_gates),
        "required_confirmations": list(seed.required_confirmations),
        "required_credentials": list(seed.required_credentials),
        "safety_notes": list(seed.safety_notes),
        "inputs": list(seed.inputs),
        "outputs": list(seed.outputs),
        "reports": reports,
        "last_run_report": last_report,
        "last_run_status": last_status,
        "current_availability": availability,
        "blockers": blockers,
        "not_in_scope_reason": not_in_scope_reason,
        "next_action": _next_action(seed, blockers, availability),
        "evidence_artifacts": evidence_artifacts,
        "stale_after_seconds": seed.stale_after_seconds,
        "last_run_trace": trace,
        "ui_run_supported": ui_run_supported,
        "ui_run_blockers": ui_run_blockers,
        "guarded_run_supported": guarded_run_supported,
        "guarded_run_blockers": guarded_run_blockers,
        "run_endpoint": f"/api/v1/workflows/actions/{seed.action_id}/run",
        "runs_endpoint": f"/api/v1/workflows/actions/{seed.action_id}/runs",
    }


def _stage_read(stage: WorkflowStageSeed, actions: list[dict[str, Any]]) -> dict[str, Any]:
    stage_actions = [action for action in actions if action["stage"] == stage.stage_id]
    blocked = [action for action in stage_actions if action["current_availability"] == "blocked"]
    reports = _unique([*stage.reports, *(report for action in stage_actions for report in action["reports"])])
    if stage_actions and all(action["current_availability"] == "not_in_scope" for action in stage_actions):
        state = "not_in_scope"
    elif blocked:
        state = "blocked"
    elif any(action["last_run_status"] == "report_available" for action in stage_actions):
        state = "historical"
    elif stage_actions:
        state = "not_checked"
    else:
        state = "not_available"
    primary = _primary_action(stage_actions)
    return {
        "stage_id": stage.stage_id,
        "label": stage.label,
        "order": stage.order,
        "current_state": state,
        "desired_state": stage.desired_state,
        "primary_action": primary["action_id"] if primary else None,
        "secondary_actions": [
            action["action_id"] for action in stage_actions if not primary or action["action_id"] != primary["action_id"]
        ],
        "dependencies": list(stage.dependencies),
        "reports": reports,
        "action_count": len(stage_actions),
        "blocked_count": len(blocked),
        "report_count": len(_existing_reports(reports)),
        "actions": stage_actions,
    }


def _run_trace(
    seed: WorkflowActionSeed,
    last_report: str | None,
    blockers: list[str],
    availability: str,
    latest_run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if latest_run:
        return run_trace_to_registry_trace(latest_run)
    started_at = None
    finished_at = None
    source_type: RunTraceSourceType = "not_checked"
    freshness = "not_checked"
    status = "not_checked"
    report_artifacts: list[str] = []
    if last_report:
        report_mtime = _report_mtime(last_report)
        if report_mtime is not None:
            finished_at = datetime.fromtimestamp(report_mtime, UTC).isoformat()
            source_type = "historical_artifact"
            freshness = "historical"
            status = "report_available"
            report_artifacts = [last_report]
    elif blockers:
        status = "blocked"
    return {
        "run_id": f"artifact:{seed.action_id}" if last_report else f"not-checked:{seed.action_id}",
        "action_id": seed.action_id,
        "stage_id": seed.stage,
        "started_at": started_at,
        "finished_at": finished_at,
        "status": status,
        "source_type": source_type,
        "freshness": freshness,
        "command": seed.command,
        "report_artifacts": report_artifacts,
        "summary": (
            "Historical report evidence is available; rerun the action to refresh current state."
            if last_report
            else "No current run trace has been recorded for this action."
        ),
        "blockers": blockers,
        "warnings": ["Historical artifacts are evidence only, not current live blockers."] if last_report else [],
        "next_action": _next_action(seed, blockers, availability),
    }


def _blockers_for_seed(seed: WorkflowActionSeed) -> list[str]:
    blockers: list[str] = []
    if seed.policy_action_id and seed.policy_category:
        try:
            blockers.extend(unique_strings(current_lab_action_policy().action_blockers(seed.policy_action_id, seed.policy_category)))
        except Exception:
            blockers.append("Action policy could not be evaluated safely.")
    return _unique(blockers)


def _not_in_scope_reason_for_seed(seed: WorkflowActionSeed) -> str | None:
    features = active_lab_profile_context().get("enabled_features") or {}
    if (seed.stage == "netapp" or "netapp" in seed.provider or seed.action_id.startswith("netapp.")) and not features.get("netapp_enabled"):
        return "NetApp is disabled by the active lab profile."
    if seed.action_id.startswith("vcenter.install-"):
        if not features.get("netapp_enabled"):
            return "NetApp is disabled by the active lab profile."
        return None
    if ("vcenter" in seed.provider or seed.action_id.startswith("vcenter-netapp.")) and (
        not features.get("netapp_enabled") or not features.get("vcenter_enabled")
    ):
        return "NetApp or vCenter is disabled by the active lab profile."
    return None


def _availability_for_seed(seed: WorkflowActionSeed) -> str:
    if seed.mode == "report_only" and seed.api_endpoint:
        return "manual_command_required"
    if seed.command or seed.api_endpoint:
        return "manual_command_required"
    return "not_available"


def _runner_action_probe(seed: WorkflowActionSeed) -> dict[str, Any]:
    return {
        "action_id": seed.action_id,
        "mode": seed.mode,
        "required_confirmations": list(seed.required_confirmations),
        "command": seed.command,
        "api_endpoint": seed.api_endpoint,
        "api_method": seed.api_method,
    }


def _dedupe_seeds(seeds: list[WorkflowActionSeed]) -> list[WorkflowActionSeed]:
    return unique_preserving_order(seeds, key=lambda seed: seed.action_id)


def _next_action(seed: WorkflowActionSeed, blockers: list[str], availability: str) -> str:
    if availability == "not_in_scope":
        return "This action is not in scope for the active lab profile."
    if blockers:
        return blockers[0]
    if availability == "available" and seed.api_endpoint:
        return "Run Check from the UI to refresh current state."
    if availability == "available" and seed.command:
        return "Run Check from the UI to refresh current state."
    if seed.command:
        return f"Review gates, then copy `{seed.command}` when this stage is in scope."
    if seed.api_endpoint:
        return f"Review gates, then call {seed.api_method or 'GET'} {seed.api_endpoint}."
    return "Review this registry action before implementing an execution lane."


def _primary_action(actions: list[dict[str, Any]]) -> dict[str, Any] | None:
    preferred_categories = ("discover", "inventory", "verify", "plan", "report")
    for category in preferred_categories:
        for action in actions:
            if action["category"] == category and action["mode"] in {"read_only", "report_only"}:
                return action
    return actions[0] if actions else None


def _mode_from_control_classification(classification: str) -> WorkflowMode:
    if classification == "read-only":
        return "read_only"
    if classification == "write":
        return "write"
    if classification == "destructive":
        return "destructive"
    return "upgrade"


def _required_mode_for_mode(mode: WorkflowMode) -> str:
    if mode in {"write", "destructive", "upgrade"}:
        return "local-lab-readwrite"
    if mode == "report_only":
        return "mock or local provider mode"
    return "local-readonly or local-lab-readwrite for live checks"


def _source_type_for_action(action: ActionDefinition) -> WorkflowSourceType:
    if action.id in CONTROL_ACTION_API_ENDPOINTS:
        return "api_endpoint"
    if action.endpoint:
        return "api_endpoint"
    if action.command and "scripts/" in action.command:
        return "backend_script"
    if action.command:
        return "make_target"
    return "manual_guidance"


def _category_from_action(action: ActionDefinition) -> WorkflowCategory:
    text = f"{action.id} {action.label}".lower()
    if "reclaim" in text:
        return "reclaim"
    if "waiver" in text or "waive" in text:
        return "waive"
    if "upgrade" in text:
        return "upgrade"
    if "reset" in text or "reload" in text or "rebuild" in text:
        return "reset"
    if "apply" in text or "bootstrap" in text or "save" in text:
        return "apply"
    if "plan" in text or "preview" in text:
        return "plan"
    if "inventory" in text or "package" in text:
        return "inventory"
    if "discover" in text or "discovery" in text:
        return "discover"
    if "report" in text or "export" in text:
        return "report"
    return "verify"


def _credentials_for_provider_ids(provider_ids: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(_unique(CREDENTIALS_BY_PROVIDER[provider_id] for provider_id in provider_ids if provider_id in CREDENTIALS_BY_PROVIDER))


def _safety_notes_for_action(action: ActionDefinition, mode: WorkflowMode) -> tuple[str, ...]:
    notes = ["No registry endpoint executes this action; commands are copyable operator guidance."]
    if mode == "read_only":
        notes.append("Mock/test state must not be treated as current real lab state.")
    if mode in {"write", "destructive", "upgrade"}:
        notes.append("Requires explicit local gates and confirmation before any real provider write.")
    if mode == "destructive":
        notes.append("Destructive action; discover and plan evidence must be fresh before apply.")
    return tuple(notes)


def _outputs_for_action(action: ActionDefinition) -> tuple[str, ...]:
    outputs: list[str] = []
    if action.endpoint:
        outputs.append("typed API response")
    if action.report:
        outputs.append("redacted report artifact")
    if not outputs:
        outputs.append("manual command guidance")
    return tuple(outputs)


def _latest_report(reports: list[str]) -> str | None:
    latest_report = None
    latest_mtime = None
    for report in reports:
        report_mtime = _report_mtime(report)
        if report_mtime is None:
            continue
        if latest_mtime is None or report_mtime > latest_mtime:
            latest_report = report
            latest_mtime = report_mtime
    return latest_report


def _report_mtime(report: str) -> float | None:
    return path_mtime(REPO_ROOT / report)


def _existing_reports(reports: list[str]) -> list[str]:
    existing: list[str] = []
    for report in reports:
        if path_exists(REPO_ROOT / report):
            existing.append(report)
    return existing


def _workflow_report_artifacts(latest_run: dict[str, Any] | None) -> list[str]:
    if not latest_run:
        return []
    return _unique(
        report
        for report in (str(item) for item in latest_run.get("report_artifacts") or [])
        if report and "/workflow-action-runs/" not in report.replace("\\", "/")
    )


def _stage_for_report_source(source: str) -> str:
    return {
        "build_verification": "build-verification",
        "firmware": "firmware",
        "cisco": "cisco",
        "ilo": "ilo",
        "raid": "raid",
        "esxi": "esxi",
        "netapp": "netapp",
        "serial": "cisco",
        "toolchain": "build-verification",
        "lab_profile": "lab-profile",
    }.get(source, source)


def _issue_link(action: dict[str, Any]) -> dict[str, str | None]:
    return {
        "source_stage_id": str(action["stage"]),
        "source_stage_label": str(action["stage_label"]),
        "source_action_id": str(action["action_id"]),
        "source_action_label": str(action["label"]),
        "source_action_link": f"/control-center?section=action-catalog&action={action['action_id']}",
    }


def _issue_report_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, dict):
        values = []
    elif isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = [value]
    return [text for item in values if item is not None and (text := str(item).strip())]


def _unique(values: Any) -> list[Any]:
    return unique_preserving_order(values, skip_falsey=True)
