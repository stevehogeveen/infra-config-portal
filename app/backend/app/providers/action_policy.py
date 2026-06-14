from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.core.config import settings

LOCAL_READONLY_MODE = "local-readonly"
LOCAL_LAB_READWRITE_MODE = "local-lab-readwrite"
LOCAL_LAB_MODE = LOCAL_LAB_READWRITE_MODE
MOCK_MODE = "mock"
REAL_CONTACT_MODES = {LOCAL_READONLY_MODE, LOCAL_LAB_READWRITE_MODE}

LOCAL_LAB_ENVIRONMENT = "isolated-real-lab"


class ActionCategory(str, Enum):
    READONLY = "readonly"
    APP_STATE_WRITE = "app_state_write"
    NETWORK_CONFIG = "network_config"
    STORAGE_CONFIG = "storage_config"
    BIOS_CONFIG = "bios_config"
    BOOT_CONFIG = "boot_config"
    VIRTUAL_MEDIA = "virtual_media"
    OS_INSTALL = "os_install"
    VM_DEPLOY = "vm_deploy"
    POWER_ACTION = "power_action"
    FIRMWARE_UPDATE = "firmware_update"
    FACTORY_RESET = "factory_reset"


BASE_LOCAL_LAB_READWRITE_CATEGORIES = frozenset(
    {
        ActionCategory.READONLY,
        ActionCategory.APP_STATE_WRITE,
        ActionCategory.NETWORK_CONFIG,
        ActionCategory.STORAGE_CONFIG,
        ActionCategory.BIOS_CONFIG,
        ActionCategory.BOOT_CONFIG,
        ActionCategory.VIRTUAL_MEDIA,
        ActionCategory.OS_INSTALL,
        ActionCategory.VM_DEPLOY,
    }
)
FLAGGED_LOCAL_LAB_READWRITE_CATEGORIES = {
    ActionCategory.POWER_ACTION: "LAB_ALLOW_POWER_ACTIONS",
    ActionCategory.FIRMWARE_UPDATE: "LAB_ALLOW_FIRMWARE_UPDATES",
    ActionCategory.FACTORY_RESET: "LAB_ALLOW_FACTORY_RESET",
}
ALLOWLISTED_WORKFLOW_ACTIONS = frozenset(
    {
        "ilo-redfish.record-readonly-inventory",
        "ilo-redfish.manager-network-protocol-hostname",
        "ilo-redfish.inventory",
        "ilo-redfish.readiness",
        "ilo-redfish.hpe-raid-apply",
        "ilo-redfish.hpe-raid-reset",
        "ilo-redfish.hpe-raid-validate-after-reset",
        "cisco-console.bootstrap",
        "cisco-console.vlan-management-ssh-scp",
        "ilo.connection-setup",
        "ilo.bios-settings",
        "ilo.boot-settings",
        "ilo.virtual-media",
        "esxi.install-config",
        "esxi.datastore-vswitch-vmkernel",
        "vm.deploy-ovf",
        "vcenter.vcsa-deploy",
        "netapp.initial-setup",
        "netapp.address-remediation",
        "netapp.factory-reset",
        "netapp.nfs-setup",
        "netapp.svm-lif-iscsi",
        "netapp.ontap-upgrade",
        "netapp.component-firmware",
        "ilo.power-action",
        "ilo.firmware-update",
        "lab.factory-reset",
    }
)

DANGEROUS_ACTION_FLAGS = {
    "ilo-power-action": "LAB_ALLOW_POWER_ACTIONS",
    "ilo-firmware-update": "LAB_ALLOW_FIRMWARE_UPDATES",
    "ilo-factory-reset": "LAB_ALLOW_FACTORY_RESET",
}


@dataclass(frozen=True)
class LabActionPolicy:
    provider_mode: str
    lab_environment: str | None
    acknowledge_real_hardware: bool
    acknowledge_device_reconfiguration: bool
    acknowledge_data_loss_risk: bool
    acknowledge_lab_only: bool
    allow_power_actions: bool
    allow_firmware_updates: bool
    allow_factory_reset: bool
    legacy_closed_loop_ack: bool
    legacy_readonly_ack: bool
    legacy_destructive_ack: bool

    @property
    def local_lab_acknowledged(self) -> bool:
        return (
            self.lab_environment == LOCAL_LAB_ENVIRONMENT
            and self.acknowledge_real_hardware
            and self.acknowledge_device_reconfiguration
            and self.acknowledge_data_loss_risk
            and self.acknowledge_lab_only
        )

    @property
    def local_readonly_acknowledged(self) -> bool:
        return self.legacy_closed_loop_ack and self.legacy_readonly_ack

    @property
    def readonly_allowed(self) -> bool:
        if self.provider_mode == LOCAL_READONLY_MODE:
            return self.local_readonly_acknowledged
        if self.provider_mode == LOCAL_LAB_READWRITE_MODE:
            return self.local_lab_acknowledged
        return False

    def readonly_blockers(self) -> list[str]:
        if self.provider_mode == MOCK_MODE:
            return [
                "PROVIDER_MODE=local-readonly or PROVIDER_MODE=local-lab-readwrite is required for real iLO probes."
            ]
        if self.provider_mode == LOCAL_READONLY_MODE:
            blockers: list[str] = []
            if not self.legacy_closed_loop_ack:
                blockers.append("LAB_CLOSED_LOOP_ACK=YES is required for local-readonly probes.")
            if not self.legacy_readonly_ack:
                blockers.append("LAB_READONLY_ACK=YES is required for local-readonly probes.")
            return blockers
        if self.provider_mode == LOCAL_LAB_READWRITE_MODE:
            blockers = []
            if self.lab_environment != LOCAL_LAB_ENVIRONMENT:
                blockers.append(
                    "LAB_ENVIRONMENT=isolated-real-lab is required for local-lab-readwrite probes."
                )
            if not self.acknowledge_real_hardware:
                blockers.append(
                    "LAB_ACKNOWLEDGE_REAL_HARDWARE=true is required before contacting real lab hardware."
                )
            if not self.acknowledge_device_reconfiguration:
                blockers.append(
                    "LAB_ACKNOWLEDGE_DEVICE_RECONFIGURATION=true is required before changing lab hardware."
                )
            if not self.acknowledge_data_loss_risk:
                blockers.append("LAB_ACKNOWLEDGE_DATA_LOSS_RISK=true is required for rebuild workflows.")
            if not self.acknowledge_lab_only:
                blockers.append("LAB_ACKNOWLEDGE_LAB_ONLY=true is required for local-lab-readwrite.")
            return blockers
        return [
            f"PROVIDER_MODE={self.provider_mode!r} is not supported for real iLO probes."
        ]

    def action_blockers(self, action_id: str, category: ActionCategory | str) -> list[str]:
        category = ActionCategory(category)
        if self.provider_mode == MOCK_MODE:
            return [f"PROVIDER_MODE=mock cannot contact or modify real devices for {action_id}."]
        if self.provider_mode == LOCAL_READONLY_MODE:
            if category == ActionCategory.READONLY:
                return self.readonly_blockers()
            return [f"PROVIDER_MODE=local-readonly is read-only; {category.value} is blocked."]
        if self.provider_mode != LOCAL_LAB_READWRITE_MODE:
            return [
                f"PROVIDER_MODE=local-lab-readwrite is required for allowlisted lab action {action_id}."
            ]

        blockers = self.readonly_blockers()
        if action_id not in ALLOWLISTED_WORKFLOW_ACTIONS:
            blockers.append(f"{action_id} is not represented in an explicit allowlisted workflow step.")
        if category in BASE_LOCAL_LAB_READWRITE_CATEGORIES:
            return blockers

        flag_name = FLAGGED_LOCAL_LAB_READWRITE_CATEGORIES.get(category)
        if flag_name is None:
            blockers.append(f"{category.value} is not allowlisted in local-lab-readwrite.")
            return blockers

        flag_enabled = {
            "LAB_ALLOW_POWER_ACTIONS": self.allow_power_actions,
            "LAB_ALLOW_FIRMWARE_UPDATES": self.allow_firmware_updates,
            "LAB_ALLOW_FACTORY_RESET": self.allow_factory_reset,
        }[flag_name]
        if not flag_enabled:
            blockers.append(f"{flag_name}=true is required for {category.value}.")
        return blockers

    def action_allowed(self, action_id: str, category: ActionCategory | str) -> bool:
        return not self.action_blockers(action_id, category)

    def dangerous_action_reason(self, action_id: str) -> str:
        flag_name = DANGEROUS_ACTION_FLAGS.get(action_id)
        if flag_name is None:
            return (
                "Blocked unless represented in an explicit local-lab-readwrite workflow step."
            )
        flag_enabled = {
            "LAB_ALLOW_POWER_ACTIONS": self.allow_power_actions,
            "LAB_ALLOW_FIRMWARE_UPDATES": self.allow_firmware_updates,
            "LAB_ALLOW_FACTORY_RESET": self.allow_factory_reset,
        }[flag_name]
        if flag_enabled:
            return (
                "Blocked until an explicit local-lab-readwrite workflow step invokes this action safely."
            )
        return f"Blocked in local-lab-readwrite: {flag_name}=true and an explicit workflow step are required."

    def as_flags(self) -> dict[str, bool | str | None]:
        return {
            "lab_environment": self.lab_environment,
            "lab_acknowledge_real_hardware": self.acknowledge_real_hardware,
            "lab_acknowledge_device_reconfiguration": self.acknowledge_device_reconfiguration,
            "lab_acknowledge_data_loss_risk": self.acknowledge_data_loss_risk,
            "lab_acknowledge_lab_only": self.acknowledge_lab_only,
            "lab_allow_power_actions": self.allow_power_actions,
            "lab_allow_firmware_updates": self.allow_firmware_updates,
            "lab_allow_factory_reset": self.allow_factory_reset,
            "local_lab_acknowledged": self.local_lab_acknowledged,
            "legacy_closed_loop_ack": self.legacy_closed_loop_ack,
            "legacy_readonly_ack": self.legacy_readonly_ack,
            "legacy_destructive_ack": self.legacy_destructive_ack,
            "local_readonly_acknowledged": self.local_readonly_acknowledged,
            "readonly_allowed": self.readonly_allowed,
        }

    def status_summary(self) -> dict[str, list[dict[str, str]]]:
        return {
            "required_flags": [
                {
                    "name": "LAB_ENVIRONMENT",
                    "status": "present" if self.lab_environment == LOCAL_LAB_ENVIRONMENT else "missing",
                },
                {
                    "name": "LAB_ACKNOWLEDGE_REAL_HARDWARE",
                    "status": "enabled" if self.acknowledge_real_hardware else "disabled",
                },
                {
                    "name": "LAB_ACKNOWLEDGE_DEVICE_RECONFIGURATION",
                    "status": "enabled" if self.acknowledge_device_reconfiguration else "disabled",
                },
                {
                    "name": "LAB_ACKNOWLEDGE_DATA_LOSS_RISK",
                    "status": "enabled" if self.acknowledge_data_loss_risk else "disabled",
                },
                {
                    "name": "LAB_ACKNOWLEDGE_LAB_ONLY",
                    "status": "enabled" if self.acknowledge_lab_only else "disabled",
                },
            ],
            "dangerous_flags": [
                {
                    "name": "LAB_ALLOW_POWER_ACTIONS",
                    "status": "enabled" if self.allow_power_actions else "disabled",
                },
                {
                    "name": "LAB_ALLOW_FIRMWARE_UPDATES",
                    "status": "enabled" if self.allow_firmware_updates else "disabled",
                },
                {
                    "name": "LAB_ALLOW_FACTORY_RESET",
                    "status": "enabled" if self.allow_factory_reset else "disabled",
                },
            ],
        }


def current_lab_action_policy(provider_mode: str | None = None) -> LabActionPolicy:
    return LabActionPolicy(
        provider_mode=provider_mode or settings.provider_mode,
        lab_environment=settings.lab_environment,
        acknowledge_real_hardware=settings.lab_acknowledge_real_hardware,
        acknowledge_device_reconfiguration=settings.lab_acknowledge_device_reconfiguration,
        acknowledge_data_loss_risk=settings.lab_acknowledge_data_loss_risk,
        acknowledge_lab_only=settings.lab_acknowledge_lab_only,
        allow_power_actions=settings.lab_allow_power_actions,
        allow_firmware_updates=settings.lab_allow_firmware_updates,
        allow_factory_reset=settings.lab_allow_factory_reset,
        legacy_closed_loop_ack=settings.lab_closed_loop_ack == "YES",
        legacy_readonly_ack=settings.lab_readonly_ack == "YES",
        legacy_destructive_ack=settings.lab_destructive_ack == "REBUILD_LAB",
    )
