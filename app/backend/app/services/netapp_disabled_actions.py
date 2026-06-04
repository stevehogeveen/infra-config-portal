from __future__ import annotations

from app.providers.base import ProviderAction


def disabled_netapp_action(id_: str, label: str, reason: str) -> ProviderAction:
    return ProviderAction(
        id=id_,
        label=label,
        enabled=False,
        read_only=False,
        reason=reason,
    )


def disabled_netapp_actions(*ids: str) -> list[ProviderAction]:
    return [disabled_netapp_action(*_DISABLED_ACTIONS[id_]) for id_ in ids]


_DISABLED_ACTIONS: dict[str, tuple[str, str, str]] = {
    "discover-live-state": (
        "netapp-discover-live-state",
        "Discover Live State",
        "Live NetApp discovery is disabled.",
    ),
    "probe-ontap-api": (
        "netapp-probe-ontap-api",
        "Probe ONTAP API",
        "ONTAP API calls are disabled.",
    ),
    "probe-ontap-api-unconfigured": (
        "netapp-probe-api",
        "Probe ONTAP API",
        "Disabled while NETAPP_CONFIGURED=false.",
    ),
    "probe-sp": (
        "netapp-probe-sp",
        "Probe Service Processor",
        "SP API calls are disabled.",
    ),
    "open-console": (
        "netapp-open-console",
        "Open Console",
        "Opening serial console ports is disabled.",
    ),
    "send-console-commands": (
        "netapp-send-console-commands",
        "Send Console Commands",
        "Console command sending is disabled.",
    ),
    "interrupt-boot": (
        "netapp-interrupt-boot",
        "Interrupt Boot",
        "Boot interruption is disabled.",
    ),
    "configure-sp-ip": (
        "netapp-configure-sp-ip",
        "Configure SP IP",
        "SP IP configuration is disabled.",
    ),
    "create-cluster": (
        "netapp-create-cluster",
        "Create Cluster",
        "Cluster creation is disabled.",
    ),
    "join-controller": (
        "netapp-join-controller",
        "Join Controller",
        "Controller join is disabled.",
    ),
    "change-ips": (
        "netapp-change-ips",
        "Change IPs",
        "IP changes are disabled.",
    ),
    "configure-cluster-management": (
        "netapp-configure-cluster-management",
        "Configure Cluster Management",
        "Cluster management configuration is disabled.",
    ),
    "configure-node-management": (
        "netapp-configure-node-management",
        "Configure Node Management",
        "Node management configuration is disabled.",
    ),
    "create-svm": (
        "netapp-create-svm",
        "Create SVM",
        "SVM creation is disabled.",
    ),
    "configure-svm": (
        "netapp-configure-svm",
        "Configure SVM",
        "SVM configuration is disabled.",
    ),
    "create-lifs": (
        "netapp-create-lifs",
        "Create LIFs",
        "LIF creation is disabled.",
    ),
    "configure-lifs": (
        "netapp-configure-lifs",
        "Configure LIFs",
        "LIF configuration is disabled.",
    ),
    "create-volumes": (
        "netapp-create-volumes",
        "Create Volumes",
        "Volume creation is disabled.",
    ),
    "upgrade-ontap": (
        "netapp-upgrade-ontap",
        "Upgrade ONTAP",
        "ONTAP upgrade is disabled.",
    ),
    "upload-ontap-image": (
        "netapp-upload-ontap-image",
        "Upload ONTAP Image",
        "Image upload is disabled.",
    ),
    "stage-upgrade": (
        "netapp-stage-upgrade",
        "Stage Upgrade",
        "Upgrade staging is disabled.",
    ),
    "start-upgrade": (
        "netapp-start-upgrade",
        "Start Upgrade",
        "Upgrade start is disabled.",
    ),
    "apply-upgrade": (
        "netapp-apply-upgrade",
        "Apply Upgrade",
        "Upgrade apply is disabled.",
    ),
    "reboot-controller": (
        "netapp-reboot-controller",
        "Reboot Controller",
        "Controller reboot is disabled.",
    ),
    "reboot-controllers": (
        "netapp-reboot",
        "Reboot Controllers",
        "Controller reboot actions are disabled.",
    ),
    "wipe-disks": (
        "netapp-wipe-disks",
        "Wipe Disks",
        "Disk wipe actions are disabled.",
    ),
    "apply-configuration": (
        "netapp-apply-configuration",
        "Apply Configuration",
        "Apply is disabled.",
    ),
    "apply-configuration-preview": (
        "netapp-apply-configuration",
        "Apply Configuration",
        "NetApp apply is disabled; preview only.",
    ),
}
