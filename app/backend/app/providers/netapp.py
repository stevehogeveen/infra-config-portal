from __future__ import annotations

from app.core.config import settings
from app.providers.base import ProviderAction, ProviderStatus
from app.services.netapp_console_readiness import get_netapp_console_readiness
from app.services.netapp_disabled_actions import disabled_netapp_actions
from app.services.firmware_compliance import firmware_gate_blockers
from app.services.netapp_readiness_comparison import get_netapp_readiness_comparison
from app.services.netapp_upgrade_readiness import get_netapp_upgrade_readiness


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
                "readiness-comparison-preview",
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
        console_readiness = get_netapp_console_readiness()
        readiness_comparison = get_netapp_readiness_comparison()
        upgrade_readiness = get_netapp_upgrade_readiness()
        readiness_buckets = discovery["readiness"]
        intent_preview = discovery["intent_preview"]
        planned_targets = {
            "sp_ips": configuration["planned_sp_ips"],
            "management_ips": configuration["planned_management_ips"],
            "iscsi_lif_range": configuration["planned_iscsi_lif_range"],
            "target_addressing": configuration["target_addressing"],
            "api_access_flags": {
                "endpoint_configured": configuration["api_configured_flags"]["endpoint_configured"],
                "endpoint_planned": configuration["api_configured_flags"]["endpoint_planned"],
                "endpoint_reachable": configuration["api_configured_flags"]["endpoint_reachable"],
                "username_configured": configuration["api_configured_flags"]["username_configured"],
                "access_configured": configuration["api_configured_flags"]["credential_configured"],
                "tls_verify": configuration["api_configured_flags"]["tls_verify"],
            },
        }
        current_discovered_targets = configuration["current_discovered_targets"]
        setup_readiness = _setup_readiness_summary(readiness_buckets)
        upgrade_readiness_summary = _upgrade_readiness_summary(upgrade_readiness)
        not_ready_count = sum(
            1 for bucket in readiness_buckets.values() if bucket.get("ready") is False
        )
        return {
            "provider_id": PROVIDER_ID,
            "mode": self.provider_mode,
            "apply_enabled": False,
            "netapp_configured": settings.netapp_configured,
            "planned_targets": planned_targets,
            "current_discovered_targets": current_discovered_targets,
            "readiness_summary": {
                "status": status.status,
                "ready": False,
                "setup_ready": setup_readiness["ready"],
                "upgrade_ready": upgrade_readiness_summary["ready"],
                "bucket_count": len(readiness_buckets),
                "not_ready_count": not_ready_count,
                "message": "Plan preview only. No ONTAP discovery, configuration, upgrade, reboot, wipe, or apply call is made.",
            },
            "setup_readiness": setup_readiness,
            "upgrade_readiness": upgrade_readiness_summary,
            "readiness_buckets": readiness_buckets,
            "cluster_intent_preview": intent_preview["cluster"],
            "svm_intent_preview": intent_preview["svm"],
            "lif_intent_preview": {"iscsi_lifs": intent_preview["iscsi_lifs"]},
            "storage_iscsi_plan_preview": discovery["storage_iscsi_plan_preview"],
            "console_bootstrap_preview": {
                "endpoint": "/api/v1/providers/netapp-ontap/console-readiness",
                "bootstrap_enabled": console_readiness["bootstrap_enabled"],
                "console_probe_enabled": console_readiness["console_probe_enabled"],
                "apply_enabled": console_readiness["apply_enabled"],
                "prerequisite_count": len(console_readiness["prerequisites"]),
                "readiness_bucket_count": len(console_readiness["readiness_buckets"]),
                "status": "manual_offline_preview",
                "details": [
                    "Manual console/bootstrap readiness preview only.",
                    "No serial ports are opened and no console commands are sent.",
                ],
            },
            "readiness_comparison_preview": {
                "endpoint": "/api/v1/providers/netapp-ontap/readiness-comparison",
                "comparison_enabled": readiness_comparison["comparison_enabled"],
                "apply_enabled": readiness_comparison["apply_enabled"],
                "discovery_enabled": readiness_comparison["discovery_enabled"],
                "matched_count": len(readiness_comparison["matched_items"]),
                "unknown_count": len(readiness_comparison["unknown_items"]),
                "warning_count": len(readiness_comparison["warning_items"]),
                "blocker_count": len(readiness_comparison["blocker_items"]),
                "comparison_item_count": len(readiness_comparison["comparison_items"]),
                "status": "manual_observations_only",
                "details": [
                    "Planned targets are compared with operator observations only.",
                    "No live NetApp discovery, probe, or apply action is run.",
                ],
            },
            "upgrade_readiness_preview": {
                "endpoint": "/api/v1/providers/netapp-ontap/upgrade-readiness",
                "apply_enabled": upgrade_readiness["apply_enabled"],
                "upgrade_enabled": upgrade_readiness["upgrade_enabled"],
                "current_version_source": upgrade_readiness["current_version_source"],
                "current_version": upgrade_readiness["current_version"],
                "media_inventory_mode": upgrade_readiness["media_inventory_mode"],
                "candidate_count": len(upgrade_readiness["candidates"]),
                "recommended_target": upgrade_readiness["recommended_target"],
                "status": "preview_only",
                "details": [
                    "Offline ONTAP media readiness preview only.",
                    "Use the upgrade-readiness endpoint for full sanitized candidate details.",
                ],
            },
            "blockers": [*status.blockers, *firmware_gate_blockers("NetApp setup workflow")],
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
            "current_discovered_targets": _current_discovered_targets(),
            "api_configured_flags": {
                "endpoint_configured": bool(
                    settings.netapp_configured and settings.netapp_cluster_mgmt_ip
                ),
                "endpoint_planned": bool(settings.netapp_cluster_mgmt_ip),
                "endpoint_reachable": False,
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
        credentials_present = bool(settings.netapp_api_username and settings.netapp_api_password)
        readonly_ack = settings.lab_readonly_ack == "YES"
        return {
            "safe_next_action": (
                "Preview only. Capture console/API discovery requirements before enabling any "
                "future read-only NetApp probe."
            ),
            "readiness": {
                "sp_readiness": {
                    "status": "planned_not_live",
                    "ready": False,
                    "planned": {
                        "controller_a": settings.netapp_controller_a_sp,
                        "controller_b": settings.netapp_controller_b_sp,
                    },
                    "current": {"controller_a": None, "controller_b": None},
                    "details": [
                        "Controller A and B SP addresses are planned.",
                        "Service Processor reachability is not probed and is not treated as live.",
                        "SP reachable/missing remains a setup blocker until an explicit safe probe exists.",
                    ],
                },
                "cluster_management_readiness": {
                    "status": "not_configured",
                    "ready": False,
                    "planned": settings.netapp_cluster_mgmt_ip,
                    "current": None,
                    "reachable": False,
                    "details": [
                        "Cluster management address is planned only.",
                        "NETAPP_CONFIGURED=false means cluster management is not treated as reachable.",
                        "Cluster management not configured blocks setup and upgrade readiness.",
                    ],
                },
                "node_management_readiness": {
                    "status": "not_configured",
                    "ready": False,
                    "planned": {
                        "node_a": settings.netapp_node_a_mgmt_ip,
                        "node_b": settings.netapp_node_b_mgmt_ip,
                    },
                    "current": {"node_a": None, "node_b": None},
                    "details": [
                        "Node A and Node B management addresses are planned.",
                        "Node management addresses are not discovered or treated as configured.",
                    ],
                },
                "svm_readiness": {
                    "status": "planned_not_live",
                    "ready": False,
                    "planned": settings.netapp_svm_mgmt_ip,
                    "current": None,
                    "details": [
                        "SVM management address is planned.",
                        "SVM management is planned but not live.",
                        "SVM creation and management configuration are disabled.",
                    ],
                },
                "iscsi_lif_readiness": {
                    "status": "planned_not_live",
                    "ready": False,
                    "planned": list(settings.netapp_iscsi_lifs),
                    "current": [],
                    "details": [
                        "iSCSI LIF range is planned but not live.",
                        "LIF creation and storage provisioning are disabled.",
                    ],
                },
                "ontap_api_readiness": {
                    "status": "blocked_until_configured",
                    "ready": False,
                    "configured": settings.netapp_configured,
                    "api_access_present": credentials_present,
                    "local_readonly_ack": readonly_ack,
                    "provider_mode": self.provider_mode,
                    "details": [
                        "NETAPP_CONFIGURED=false blocks ONTAP API readiness.",
                        "Cluster management is planned but not treated as reachable.",
                        "Credentials are missing." if not credentials_present else "Credentials are present but not returned.",
                        "LAB_READONLY_ACK=YES is missing." if not readonly_ack else "LAB_READONLY_ACK=YES is present.",
                        "PROVIDER_MODE=local-readonly is required for any future safe probe.",
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
                    "status": "blocked_until_setup_ready",
                    "ready": False,
                    "current_version": "unknown",
                    "recommended_path": [],
                    "details": [
                        "Upgrade readiness is separate from setup readiness.",
                        "Cluster and node management are not configured, so upgrade readiness is blocked.",
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
    return disabled_netapp_actions(
        "probe-ontap-api-unconfigured",
        "create-cluster",
        "change-ips",
        "create-svm",
        "create-lifs",
        "create-volumes",
        "upgrade-ontap",
        "reboot-controllers",
        "wipe-disks",
        "apply-configuration-preview",
    )


def _current_discovered_targets() -> dict:
    return {
        "discovery_enabled": False,
        "source": "not_discovered",
        "sp_ips": {"controller_a": None, "controller_b": None},
        "management_ips": {
            "cluster": None,
            "node_a": None,
            "node_b": None,
            "svm": None,
        },
        "iscsi_lif_range": {"start": None, "end": None, "addresses": []},
        "notes": [
            "No live NetApp discovery has been run.",
            "Planned addresses are not treated as reachable current state.",
        ],
    }


def _setup_readiness_summary(readiness_buckets: dict) -> dict:
    setup_bucket_keys = [
        "sp_readiness",
        "cluster_management_readiness",
        "node_management_readiness",
        "svm_readiness",
        "iscsi_lif_readiness",
        "ontap_api_readiness",
        "console_bootstrap_readiness",
        "storage_iscsi_plan_preview",
    ]
    blocker_details = [
        detail
        for key in setup_bucket_keys
        for detail in readiness_buckets.get(key, {}).get("details", [])
    ]
    return {
        "ready": False,
        "status": "blocked_preview_only",
        "bucket_keys": setup_bucket_keys,
        "blockers": blocker_details,
        "next_safe_action": (
            "Complete manual physical/console checks and keep NetApp setup as preview-only "
            "until an approved read-only discovery task exists."
        ),
    }


def _upgrade_readiness_summary(upgrade_readiness: dict) -> dict:
    return {
        "ready": False,
        "status": "blocked_until_setup_ready",
        "upgrade_enabled": upgrade_readiness["upgrade_enabled"],
        "current_version_source": upgrade_readiness["current_version_source"],
        "recommended_target": upgrade_readiness["recommended_target"],
        "blockers": [
            "Setup readiness is not complete.",
            *upgrade_readiness["blockers"],
        ],
        "next_safe_action": upgrade_readiness["next_safe_action"],
    }
