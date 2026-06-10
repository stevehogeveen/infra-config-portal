from __future__ import annotations

from app.core.config import settings
from app.providers.base import ProviderAction, ProviderStatus
from app.providers.action_policy import REAL_CONTACT_MODES, current_lab_action_policy
from app.services.netapp_console_readiness import get_netapp_console_readiness
from app.services.netapp_disabled_actions import disabled_netapp_actions
from app.services.firmware_compliance import firmware_gate_blockers
from app.services.netapp_readiness_comparison import get_netapp_readiness_comparison
from app.services.netapp_real_lab import (
    get_latest_netapp_console_discovery,
    get_latest_netapp_console_state,
    get_netapp_nfs_vcenter_readiness,
)
from app.services.netapp_state import get_netapp_runtime_state
from app.services.netapp_upgrade_readiness import get_netapp_upgrade_readiness


PROVIDER_ID = "netapp-ontap"


class NetAppOntapAdapter:
    def __init__(self, provider_mode: str | None = None) -> None:
        self.provider_mode = provider_mode or settings.provider_mode

    def health(self) -> ProviderStatus:
        runtime_state = get_netapp_runtime_state()
        configured = bool(runtime_state.get("configured"))
        policy = current_lab_action_policy(self.provider_mode)
        readonly_enabled = self.provider_mode in REAL_CONTACT_MODES and policy.readonly_allowed
        latest_console_discovery = get_latest_netapp_console_discovery()
        latest_console_state = get_latest_netapp_console_state()
        nfs_vcenter_readiness = get_netapp_nfs_vcenter_readiness(check_ports=False, write_report=False)
        return ProviderStatus(
            id=PROVIDER_ID,
            name="NetApp ONTAP",
            kind="storage",
            mode=self.provider_mode,
            status="ok" if configured else "blocked",
            capabilities=[
                "health",
                "plan-preview",
                "setup-preview",
                "setup-apply-guarded",
                "readiness-preview",
                "readiness-comparison-preview",
                "ontap-upgrade-inventory",
                "ontap-upgrade-plan",
                "ontap-upgrade-validate",
                "ontap-upgrade-apply-guarded",
                "upgrade-readiness-preview",
                "console-discovery-readonly",
                "console-read-state-readonly",
                "nfs-vcenter-readiness-preview",
            ],
            message=(
                "NetApp ONTAP preview with explicit read-only console discovery available in real-lab modes. "
                "Storage/NFS/vCenter apply remains disabled."
            ),
            configuration=self._configuration(),
            discovery={
                **self._discovery(),
                "latest_console_discovery": latest_console_discovery,
                "latest_console_state": latest_console_state,
                "nfs_vcenter_readiness": nfs_vcenter_readiness,
                "runtime_state": runtime_state,
            },
            blockers=[
                "NetApp configured state is not verified by live check yet.",
                "No live ONTAP storage/NFS/vCenter apply operation is permitted from this portal.",
            ]
            if not configured
            else ["No live ONTAP storage/NFS/vCenter apply operation is permitted from this portal."],
            warnings=[
                "Planned NetApp targets have not been discovered or compared to live hardware.",
                "Console discovery is newline-only and does not send credentials, setup commands, or boot interrupts.",
                settings.netapp_management_topology_note,
                "ONTAP Upgrade Center stays disabled until setup, image selection, pre-upgrade validation, and exact flags are ready.",
            ],
            safe_actions=[
                ProviderAction(
                    id="netapp-console-discovery",
                    label="Discover NetApp Console",
                    enabled=readonly_enabled,
                    read_only=True,
                    reason=(
                        "Open ranked serial candidates and send newline/enter only."
                        if readonly_enabled
                        else "Requires local-readonly/local-lab-readwrite mode with real-lab acknowledgements."
                    ),
                    method="POST",
                    endpoint="/api/v1/providers/netapp-ontap/console-discovery",
                ),
                ProviderAction(
                    id="netapp-live-state",
                    label="Read NetApp State",
                    enabled=readonly_enabled,
                    read_only=True,
                    reason=(
                        "Run read-only NetApp state checks and persist the result."
                        if readonly_enabled
                        else "Requires local-readonly/local-lab-readwrite mode with real-lab acknowledgements."
                    ),
                    method="POST",
                    endpoint="/api/v1/providers/netapp-ontap/live-state",
                ),
                ProviderAction(
                    id="netapp-validate-setup",
                    label="Validate NetApp Setup",
                    enabled=readonly_enabled,
                    read_only=True,
                    reason=(
                        "Mark configured only after live verification succeeds."
                        if readonly_enabled
                        else "Requires local-readonly/local-lab-readwrite mode with real-lab acknowledgements."
                    ),
                    method="POST",
                    endpoint="/api/v1/providers/netapp-ontap/validate-setup",
                ),
                ProviderAction(
                    id="netapp-console-read-state",
                    label="Read Console State",
                    enabled=readonly_enabled,
                    read_only=True,
                    reason=(
                        "Read current NetApp console prompt/state without credentials or commands."
                        if readonly_enabled
                        else "Requires local-readonly/local-lab-readwrite mode with real-lab acknowledgements."
                    ),
                    method="POST",
                    endpoint="/api/v1/providers/netapp-ontap/console-read-state",
                ),
            ],
            disabled_actions=_disabled_actions(),
        )

    def plan_preview(self) -> dict:
        status = self.health()
        configuration = self._configuration()
        runtime_state = configuration["runtime_state"]
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
        nfs_vcenter_readiness = get_netapp_nfs_vcenter_readiness(check_ports=False, write_report=False)
        not_ready_count = sum(
            1 for bucket in readiness_buckets.values() if bucket.get("ready") is False
        )
        return {
            "provider_id": PROVIDER_ID,
            "mode": self.provider_mode,
            "apply_enabled": False,
            "netapp_configured": bool(runtime_state.get("configured")),
            "netapp_configured_source": runtime_state.get("source"),
            "manual_env_flag_required": False,
            "runtime_state": runtime_state,
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
            "storage_nfs_vcenter_preview": {
                "endpoint": "/api/v1/providers/netapp-ontap/nfs-vcenter-readiness",
                "apply_enabled": nfs_vcenter_readiness["apply_enabled"],
                "status": nfs_vcenter_readiness["status"],
                "single_management_port_mode": nfs_vcenter_readiness["single_management_port_mode"],
                "planned_nfs": nfs_vcenter_readiness["planned_nfs"],
                "target_summary": nfs_vcenter_readiness["targets"],
                "blocker_count": len(nfs_vcenter_readiness["blockers"]),
                "details": [
                    "NFS/vCenter workflow is readiness preview only.",
                    settings.netapp_management_topology_note,
                ],
            },
            "console_bootstrap_preview": {
                "endpoint": "/api/v1/providers/netapp-ontap/console-readiness",
                "bootstrap_enabled": console_readiness["bootstrap_enabled"],
                "console_probe_enabled": console_readiness["console_probe_enabled"],
                "apply_enabled": console_readiness["apply_enabled"],
                "prerequisite_count": len(console_readiness["prerequisites"]),
                "readiness_bucket_count": len(console_readiness["readiness_buckets"]),
                "status": "manual_offline_preview",
                "details": [
                    "Manual readiness plus explicit read-only console discovery endpoints.",
                    "Console discovery sends newline/enter only and does not send credentials or commands.",
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
        nfs_lifs = list(settings.netapp_nfs_lifs)
        runtime_state = get_netapp_runtime_state()
        console_state = runtime_state.get("console") if isinstance(runtime_state.get("console"), dict) else {}
        live_configured = bool(runtime_state.get("configured"))
        configured_state = str(runtime_state.get("configured_state") or "")
        return {
            "netapp_configured": live_configured,
            "netapp_configured_source": runtime_state.get("source"),
            "legacy_netapp_configured_env": settings.netapp_configured,
            "manual_env_flag_required": False,
            "runtime_state": runtime_state,
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
                    live_configured and settings.netapp_cluster_mgmt_ip
                ),
                "endpoint_planned": bool(settings.netapp_cluster_mgmt_ip),
                "endpoint_reachable": bool(
                    (runtime_state.get("management") or {}).get("rest_443_reachable")
                    if isinstance(runtime_state.get("management"), dict)
                    else False
                ),
                "username_configured": settings.netapp_api_username is not None,
                "credential_configured": settings.netapp_api_password is not None,
                "tls_verify": settings.netapp_api_verify_tls,
            },
            "console": {
                "configured_port_hint": settings.netapp_console_port,
                "configured_port_hint_role": "optional_hint_only",
                "manual_env_update_required": False,
                "discovered_port": console_state.get("discovered_port"),
                "discovered_baud": console_state.get("baud"),
                "confidence": console_state.get("confidence"),
                "last_seen": console_state.get("last_seen"),
                "source": console_state.get("source"),
                "baud": settings.netapp_console_baud,
                "timeout_seconds": settings.netapp_console_timeout_seconds,
                "autodiscovery_enabled": not settings.netapp_console_autodiscovery_disabled,
                "connected_management_ports": list(settings.netapp_connected_management_ports),
                "management_topology_note": settings.netapp_management_topology_note,
            },
            "planned_nfs": {
                "storage_protocol": settings.netapp_storage_protocol,
                "nfs_lifs": list(settings.netapp_nfs_lifs),
                "volume": settings.netapp_nfs_volume,
                "export_policy": settings.netapp_nfs_export_policy,
                "mount_path": settings.netapp_nfs_mount_path,
                "datastore_name": settings.netapp_nfs_datastore_name,
                "client_match": settings.netapp_nfs_client_match,
            },
            "vcenter": {
                "configured": settings.vcenter_configured,
                "host_configured": bool(settings.vcenter_host),
                "username_configured": bool(settings.vcenter_username),
                "credential_configured": bool(settings.vcenter_password),
                "tls_verify": settings.vcenter_verify_tls,
            },
            "safe_next_action": (
                "Review the setup plan for the detected cluster setup wizard; keep apply paths disabled until explicit setup gates exist."
                if configured_state == "setup_wizard"
                else "Run NetApp console discovery/read-state, then review NFS/vCenter readiness; keep apply paths disabled."
            ),
            "target_addressing": [
                {"label": "Controller A SP", "address": settings.netapp_controller_a_sp},
                {"label": "Controller B SP", "address": settings.netapp_controller_b_sp},
                {"label": "Cluster management", "address": settings.netapp_cluster_mgmt_ip},
                {"label": "Node A management / e0M", "address": settings.netapp_node_a_mgmt_ip},
                {"label": "Node B management / e0M", "address": settings.netapp_node_b_mgmt_ip},
                {"label": "SVM management", "address": settings.netapp_svm_mgmt_ip},
                {"label": "NFS LIFs", "address": ", ".join(nfs_lifs)},
                {"label": "iSCSI LIFs", "address": ", ".join(settings.netapp_iscsi_lifs)},
            ],
            "artifact_placeholders": [
                "netapp-setup-plan-report.md",
                "netapp-setup-preview-report.md",
                "netapp-cluster-setup-apply-report.md",
                "netapp-post-setup-validation-report.md",
                "netapp-management-network-scan-report.md",
                "netapp-upgrade-inventory-report.md",
                "netapp-ontap-upgrade-plan-report.md",
                "netapp-ontap-upgrade-validation-report.md",
                "netapp-ontap-upgrade-apply-report.md",
                "storage-iscsi-plan-preview.json",
                "netapp-console-autodiscovery-report.md",
                "netapp-console-state-report.md",
                "netapp-console-login-state-report.md",
                "netapp-console-current-report.md",
                "netapp-nfs-vcenter-readiness-report.md",
                "netapp-bringup-build-verification-report.md",
                "cluster-svm-lif-intent.json",
                "post-run-report.md",
            ],
        }

    def _discovery(self) -> dict:
        credentials_present = bool(settings.netapp_api_username and settings.netapp_api_password)
        readonly_ack = settings.lab_readonly_ack == "YES"
        runtime_state = get_netapp_runtime_state()
        live_configured = bool(runtime_state.get("configured"))
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
                    "status": "verified_by_live_check" if live_configured else "not_configured",
                    "ready": live_configured,
                    "planned": settings.netapp_cluster_mgmt_ip,
                    "current": settings.netapp_cluster_mgmt_ip if live_configured else None,
                    "reachable": bool(
                        (runtime_state.get("management") or {}).get("rest_443_reachable")
                        if isinstance(runtime_state.get("management"), dict)
                        else live_configured
                    ),
                    "details": [
                        "Cluster management address comes from the bootstrap profile.",
                        "Configured state is derived from live verification, not manual env tracking.",
                        "Manual env flag not required.",
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
                    "status": "verified_by_live_check" if live_configured else "blocked_until_live_validation",
                    "ready": live_configured,
                    "configured": live_configured,
                    "configured_state": runtime_state.get("configured_state"),
                    "configured_source": runtime_state.get("source"),
                    "api_access_present": credentials_present,
                    "local_readonly_ack": readonly_ack,
                    "provider_mode": self.provider_mode,
                    "details": [
                        "Build Verification prefers live verified state over NETAPP_CONFIGURED.",
                        "NETAPP_CONFIGURED is legacy/desired context only.",
                        "Credentials are missing." if not credentials_present else "Credentials are present but not returned.",
                        "LAB_READONLY_ACK=YES is missing." if not readonly_ack else "LAB_READONLY_ACK=YES is present.",
                        "PROVIDER_MODE=local-readonly is required for any future safe probe.",
                        "Only API configured flags are exposed; secrets are never returned.",
                    ],
                },
                "console_bootstrap_readiness": {
                    "status": "readonly_probe_available"
                    if self.provider_mode in REAL_CONTACT_MODES
                    else "manual_placeholder",
                    "ready": False,
                    "details": [
                        "Console discovery can open ranked local serial candidates in real-lab modes.",
                        "Only newline/enter wake bytes are sent.",
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
    runtime_state = get_netapp_runtime_state()
    if runtime_state.get("configured"):
        detected = (
            runtime_state.get("detected_management_ips")
            if isinstance(runtime_state.get("detected_management_ips"), dict)
            else {}
        )
        return {
            "discovery_enabled": True,
            "source": runtime_state.get("source") or "live_verification",
            "controller_sp": {"controller_a": None, "controller_b": None},
            "management_ips": {
                "cluster": detected.get("cluster") or settings.netapp_cluster_mgmt_ip,
                "node_a": settings.netapp_node_a_mgmt_ip,
                "node_b": settings.netapp_node_b_mgmt_ip,
                "svm": settings.netapp_svm_mgmt_ip,
            },
            "iscsi_lif_range": {
                "start": settings.netapp_iscsi_lifs[0] if settings.netapp_iscsi_lifs else None,
                "end": settings.netapp_iscsi_lifs[-1] if settings.netapp_iscsi_lifs else None,
                "addresses": list(settings.netapp_iscsi_lifs),
            },
        }
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
