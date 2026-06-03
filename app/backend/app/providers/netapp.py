from __future__ import annotations

from app.core.config import settings
from app.providers.base import ProviderAction, ProviderStatus


PROVIDER_ID = "netapp-ontap"


class NetAppOntapAdapter:
    def __init__(self, provider_mode: str | None = None) -> None:
        self.provider_mode = provider_mode or settings.provider_mode

    def health(self) -> ProviderStatus:
        configured = settings.netapp_configured
        return ProviderStatus(
            id=PROVIDER_ID,
            name="NetApp ONTAP",
            kind="storage",
            mode=self.provider_mode,
            status="ok" if configured else "blocked",
            capabilities=[
                "health",
                "plan-preview",
                "readiness-preview",
                "upgrade-readiness-preview",
            ],
            message=(
                "Plan-only NetApp ONTAP preview. No ONTAP API, Service Processor, "
                "console, SSH, storage, LIF, volume, reboot, wipe, upgrade, or apply call is made."
            ),
            configuration=self._configuration(),
            discovery=self._discovery(),
            blockers=[
                "NETAPP_CONFIGURED=false; live ONTAP readiness and discovery are blocked.",
                "No live ONTAP apply operation is permitted from this portal.",
            ]
            if not configured
            else ["No live ONTAP apply operation is permitted from this portal."],
            warnings=[
                "Planned NetApp targets have not been discovered or compared to live hardware.",
                "Console/bootstrap readiness is a manual placeholder.",
                "Upgrade path is a preview placeholder until read-only discovery and media inventory are added.",
            ],
            safe_actions=[],
            disabled_actions=_disabled_actions(),
        )

    def plan_preview(self) -> dict:
        status = self.health()
        configuration = self._configuration()
        discovery = self._discovery()
        readiness_buckets = discovery["readiness"]
        intent_preview = discovery["intent_preview"]
        planned_targets = {
            "sp_ips": configuration["planned_sp_ips"],
            "management_ips": configuration["planned_management_ips"],
            "iscsi_lif_range": configuration["planned_iscsi_lif_range"],
            "target_addressing": configuration["target_addressing"],
            "api_access_flags": {
                "endpoint_configured": configuration["api_configured_flags"]["endpoint_configured"],
                "username_configured": configuration["api_configured_flags"]["username_configured"],
                "access_configured": configuration["api_configured_flags"]["credential_configured"],
                "tls_verify": configuration["api_configured_flags"]["tls_verify"],
            },
        }
        not_ready_count = sum(
            1 for bucket in readiness_buckets.values() if bucket.get("ready") is False
        )
        return {
            "provider_id": PROVIDER_ID,
            "mode": self.provider_mode,
            "apply_enabled": False,
            "netapp_configured": settings.netapp_configured,
            "planned_targets": planned_targets,
            "readiness_summary": {
                "status": status.status,
                "ready": False,
                "bucket_count": len(readiness_buckets),
                "not_ready_count": not_ready_count,
                "message": "Plan preview only. No ONTAP discovery, configuration, upgrade, reboot, wipe, or apply call is made.",
            },
            "readiness_buckets": readiness_buckets,
            "cluster_intent_preview": intent_preview["cluster"],
            "svm_intent_preview": intent_preview["svm"],
            "lif_intent_preview": {"iscsi_lifs": intent_preview["iscsi_lifs"]},
            "storage_iscsi_plan_preview": discovery["storage_iscsi_plan_preview"],
            "upgrade_readiness_preview": readiness_buckets["upgrade_readiness_path"],
            "blockers": status.blockers,
            "warnings": [
                "No ONTAP API, Service Processor, console, SSH, storage, or upgrade endpoint is contacted.",
                "Preview output is not a validated execution plan.",
            ],
            "removable_warnings": status.warnings,
            "disabled_actions": status.disabled_actions,
            "artifact_placeholders": configuration["artifact_placeholders"],
            "next_safe_action": configuration["safe_next_action"],
        }

    def _configuration(self) -> dict:
        iscsi_lifs = list(settings.netapp_iscsi_lifs)
        return {
            "netapp_configured": settings.netapp_configured,
            "planned_sp_ips": {
                "controller_a": settings.netapp_controller_a_sp,
                "controller_b": settings.netapp_controller_b_sp,
            },
            "planned_management_ips": {
                "cluster": settings.netapp_cluster_mgmt_ip,
                "node_a": settings.netapp_node_a_mgmt_ip,
                "node_b": settings.netapp_node_b_mgmt_ip,
                "svm": settings.netapp_svm_mgmt_ip,
            },
            "planned_iscsi_lif_range": {
                "start": iscsi_lifs[0] if iscsi_lifs else None,
                "end": iscsi_lifs[-1] if iscsi_lifs else None,
                "addresses": iscsi_lifs,
            },
            "api_configured_flags": {
                "endpoint_configured": bool(settings.netapp_cluster_mgmt_ip),
                "username_configured": settings.netapp_api_username is not None,
                "credential_configured": settings.netapp_api_password is not None,
                "tls_verify": settings.netapp_api_verify_tls,
            },
            "safe_next_action": (
                "Review planned targets and readiness placeholders; keep NetApp apply paths "
                "disabled until a future explicit read-only discovery task is approved."
            ),
            "target_addressing": [
                {"label": "Controller A SP", "address": settings.netapp_controller_a_sp},
                {"label": "Controller B SP", "address": settings.netapp_controller_b_sp},
                {"label": "Cluster management", "address": settings.netapp_cluster_mgmt_ip},
                {"label": "Node A management / e0M", "address": settings.netapp_node_a_mgmt_ip},
                {"label": "Node B management / e0M", "address": settings.netapp_node_b_mgmt_ip},
                {"label": "SVM management", "address": settings.netapp_svm_mgmt_ip},
                {"label": "iSCSI LIFs", "address": ", ".join(settings.netapp_iscsi_lifs)},
            ],
            "artifact_placeholders": [
                "setup-plan.json",
                "readiness-report.md",
                "upgrade-path-preview.md",
                "storage-iscsi-plan-preview.json",
                "cluster-svm-lif-intent.json",
                "post-run-report.md",
            ],
        }

    def _discovery(self) -> dict:
        return {
            "safe_next_action": (
                "Preview only. Capture console/API discovery requirements before enabling any "
                "future read-only NetApp probe."
            ),
            "readiness": {
                "sp_readiness": {
                    "status": "planned",
                    "ready": False,
                    "details": [
                        "Controller A and B SP addresses are planned.",
                        "Service Processor reachability is not probed.",
                    ],
                },
                "cluster_management_readiness": {
                    "status": "planned",
                    "ready": False,
                    "target": settings.netapp_cluster_mgmt_ip,
                    "details": [
                        "Cluster management address is planned.",
                        "Cluster management reachability is not probed.",
                    ],
                },
                "node_management_readiness": {
                    "status": "planned",
                    "ready": False,
                    "details": [
                        "Node A and Node B management addresses are planned.",
                        "Node management reachability is not probed.",
                    ],
                },
                "svm_readiness": {
                    "status": "planned",
                    "ready": False,
                    "details": [
                        "SVM management address is planned.",
                        "SVM is not created by this portal.",
                    ],
                },
                "ontap_api_readiness": {
                    "status": "blocked_until_configured",
                    "ready": False,
                    "configured": settings.netapp_configured,
                    "details": [
                        "NETAPP_CONFIGURED=false blocks ONTAP API readiness.",
                        "Only API configured flags are exposed; secrets are never returned.",
                    ],
                },
                "console_bootstrap_readiness": {
                    "status": "manual_placeholder",
                    "ready": False,
                    "details": [
                        "Console/bootstrap readiness is a manual operator placeholder.",
                        "No cluster create or controller IP change is run.",
                    ],
                },
                "upgrade_readiness_path": {
                    "status": "preview_only",
                    "ready": False,
                    "current_version": "unknown",
                    "recommended_path": [],
                    "details": [
                        "Read-only ONTAP discovery and local image inventory are required first.",
                        "Upgrade, upload, reboot, and takeover/giveback actions are disabled.",
                    ],
                },
                "storage_iscsi_plan_preview": {
                    "status": "preview_only",
                    "ready": False,
                    "details": [
                        "Storage and iSCSI plan preview is a placeholder.",
                        "No volumes, igroups, LUNs, or LIFs are created.",
                    ],
                },
                "reports_artifacts": {
                    "status": "placeholder",
                    "ready": False,
                    "details": [
                        "Report and artifact names are placeholders only.",
                        "No NetApp export bundle is generated yet.",
                    ],
                },
            },
            "intent_preview": {
                "cluster": {
                    "management_ip": settings.netapp_cluster_mgmt_ip,
                    "nodes": [
                        {"name": "node-a", "management_ip": settings.netapp_node_a_mgmt_ip},
                        {"name": "node-b", "management_ip": settings.netapp_node_b_mgmt_ip},
                    ],
                },
                "svm": {"management_ip": settings.netapp_svm_mgmt_ip},
                "iscsi_lifs": [
                    {"name": f"iscsi-lif-{index}", "address": address}
                    for index, address in enumerate(settings.netapp_iscsi_lifs, start=1)
                ],
            },
            "storage_iscsi_plan_preview": {
                "status": "placeholder",
                "notes": [
                    "Preview storage/iSCSI intent only.",
                    "Volume, LUN, igroup, and LIF details will be added after read-only discovery.",
                ],
            },
            "reports_artifacts": self._configuration()["artifact_placeholders"],
        }


def _disabled_actions() -> list[ProviderAction]:
    return [
        _disabled_action("netapp-probe-api", "Probe ONTAP API", "Disabled while NETAPP_CONFIGURED=false."),
        _disabled_action("netapp-create-cluster", "Create Cluster", "Cluster creation is not exposed."),
        _disabled_action("netapp-change-ips", "Change IPs", "Controller, node, SVM, and LIF IP changes are disabled."),
        _disabled_action("netapp-create-svm", "Create SVM", "SVM creation is plan-only."),
        _disabled_action("netapp-create-lifs", "Create LIFs", "iSCSI LIF creation is plan-only."),
        _disabled_action("netapp-create-volumes", "Create Volumes", "Volume provisioning is disabled."),
        _disabled_action("netapp-upgrade-ontap", "Upgrade ONTAP", "ONTAP upgrade actions are disabled."),
        _disabled_action("netapp-reboot", "Reboot Controllers", "Controller reboot actions are disabled."),
        _disabled_action("netapp-wipe-disks", "Wipe Disks", "Disk wipe actions are disabled."),
        _disabled_action("netapp-apply-configuration", "Apply Configuration", "NetApp apply is disabled; preview only."),
    ]


def _disabled_action(id_: str, label: str, reason: str) -> ProviderAction:
    return ProviderAction(
        id=id_,
        label=label,
        enabled=False,
        read_only=False,
        reason=reason,
    )
