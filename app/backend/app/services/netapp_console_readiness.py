from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.providers.action_policy import REAL_CONTACT_MODES, current_lab_action_policy
from app.providers.base import ProviderAction
from app.services.netapp_disabled_actions import disabled_netapp_actions
from app.services.netapp_observations import (
    get_netapp_observations,
    netapp_observation_blockers,
    summarize_netapp_observations,
)
from app.services.netapp_state import get_netapp_runtime_state


PROVIDER_ID = "netapp-ontap"
CONSOLE_READINESS_ENDPOINT = "/api/v1/providers/netapp-ontap/console-readiness"


def get_netapp_console_readiness() -> dict[str, Any]:
    planned_targets = _planned_targets()
    prerequisites = _prerequisites()
    readiness_buckets = _readiness_buckets()
    observations = get_netapp_observations()
    runtime_state = _runtime_state_for_mode()
    live_configured = bool(runtime_state.get("configured"))
    observation_summary = summarize_netapp_observations(observations)
    observation_blockers = netapp_observation_blockers(observations)
    credentials_present = bool(settings.netapp_api_username and settings.netapp_api_password)
    readonly_ack = settings.lab_readonly_ack == "YES"
    policy = current_lab_action_policy(settings.provider_mode)
    real_lab_probe_available = settings.provider_mode in REAL_CONTACT_MODES and policy.readonly_allowed
    policy_blockers = policy.readonly_blockers() if settings.provider_mode in REAL_CONTACT_MODES else []
    return {
        "provider_id": PROVIDER_ID,
        "mode": settings.provider_mode,
        "bootstrap_enabled": False,
        "console_probe_enabled": real_lab_probe_available,
        "apply_enabled": False,
        "netapp_configured": live_configured,
        "netapp_configured_source": runtime_state.get("source"),
        "legacy_netapp_configured_env": settings.netapp_configured,
        "manual_env_flag_required": False,
        "runtime_state": runtime_state,
        "planned_targets": planned_targets,
        "current_discovered_targets": _current_discovered_targets(),
        "prerequisites": prerequisites,
        "manual_steps": [
            "Connect serial console access to controller A using an operator-managed terminal.",
            "Watch the boot process without sending commands from this portal.",
            "Interrupt boot only if a future approved workflow explicitly requires it.",
            "Confirm whether LOADER, boot menu, cluster setup, existing login, or an unknown state is visible.",
            "Record the observed state manually in notes or a future approved readiness record.",
            "Do not run cluster setup or network configuration from this app yet.",
        ],
        "expected_prompts_or_states": [
            {"id": "loader", "label": "LOADER prompt", "safe_meaning": "Controller is at low-level boot prompt."},
            {"id": "boot-menu", "label": "Boot menu", "safe_meaning": "Boot menu is visible for manual inspection."},
            {"id": "cluster-setup", "label": "Cluster setup prompt", "safe_meaning": "Initial setup prompt may be visible."},
            {"id": "existing-login", "label": "Existing cluster login prompt", "safe_meaning": "System may already be configured."},
            {"id": "unknown", "label": "Unknown / unverified", "safe_meaning": "Operator has not verified console state."},
        ],
        "readiness_buckets": readiness_buckets,
        "observations": observations,
        "observation_summary": observation_summary,
        "observation_blockers": observation_blockers,
        "blockers": [
            *policy_blockers,
            "Bootstrap and configuration actions are disabled.",
            *([] if live_configured else ["NetApp configured state has not been verified by live check yet."]),
            "Cluster management is planned until live state verifies reachability.",
            "Node management is planned but not configured.",
            "SVM management and iSCSI LIFs are planned but not live.",
            *([] if credentials_present else ["NetApp API credentials are missing."]),
            *([] if readonly_ack else ["LAB_READONLY_ACK=YES is missing for future safe probes."]),
        ],
        "warnings": [
            "This preview does not verify physical cabling, power state, SP reachability, or existing data.",
            "Explicit real-lab console discovery sends newline/enter only and never sends credentials or setup commands.",
            settings.netapp_management_topology_note,
            "Operator must confirm whether the system is new/factory or already configured before any future workflow.",
        ],
        "removable_warnings": [
            "Review planned SP, cluster, node, SVM, and iSCSI LIF addresses before future discovery.",
            "Store any future access values only in the local real-lab environment file; do not paste them into the UI.",
            *observation_blockers,
        ],
        "disabled_actions": _disabled_console_actions(),
        "next_safe_action": (
            "Run NetApp console discovery/read-state for newline-only evidence, then keep all NetApp "
            "bootstrap actions disabled until a future approved setup workflow exists."
        ),
    }


def _planned_targets() -> dict[str, Any]:
    iscsi_lifs = list(settings.netapp_iscsi_lifs)
    return {
        "controller_sp": {
            "controller_a": settings.netapp_controller_a_sp,
            "controller_b": settings.netapp_controller_b_sp,
        },
        "management_ips": {
            "cluster": settings.netapp_cluster_mgmt_ip,
            "node_a": settings.netapp_node_a_mgmt_ip,
            "node_b": settings.netapp_node_b_mgmt_ip,
            "svm": settings.netapp_svm_mgmt_ip,
        },
        "iscsi_lif_range": {
            "start": iscsi_lifs[0] if iscsi_lifs else None,
            "end": iscsi_lifs[-1] if iscsi_lifs else None,
            "addresses": iscsi_lifs,
        },
    }


def _current_discovered_targets() -> dict[str, Any]:
    runtime_state = _runtime_state_for_mode()
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
        "controller_sp": {"controller_a": None, "controller_b": None},
        "management_ips": {"cluster": None, "node_a": None, "node_b": None, "svm": None},
        "iscsi_lif_range": {"start": None, "end": None, "addresses": []},
    }


def _runtime_state_for_mode() -> dict[str, Any]:
    if settings.provider_mode in REAL_CONTACT_MODES:
        return get_netapp_runtime_state()
    return {
        "provider_id": PROVIDER_ID,
        "device_role": "storage-controller",
        "checked_at": None,
        "configured": False,
        "configured_state": "not_detected",
        "source": "none",
        "manual_env_flag_required": False,
        "console": {},
        "management": {},
        "api": {},
        "storage": {},
        "detected_management_ips": {},
        "detected_storage_protocol_readiness": {},
        "last_successful_probe_at": None,
        "last_report_path": None,
        "confidence": "low",
        "blockers": ["NetApp live runtime state is not read in mock mode."],
    }


def _prerequisites() -> list[dict[str, str]]:
    return [
        {
            "id": "power-cabling",
            "label": "Both controllers powered and cabled",
            "status": "manual_check_required",
        },
        {
            "id": "controller-a-console",
            "label": "Serial/console access available to controller A",
            "status": "read_only_probe_available"
            if settings.provider_mode in REAL_CONTACT_MODES
            else "manual_check_required",
        },
        {
            "id": "sp-network",
            "label": "Controller A and B SP network cables connected",
            "status": "manual_check_required",
        },
        {
            "id": "management-network",
            "label": "Management network reachable from the app host",
            "status": "manual_check_required",
        },
        {
            "id": "planned-address-review",
            "label": "Planned SP and management IPs reviewed",
            "status": "planned",
        },
        {
            "id": "local-env-values",
            "label": "Future access values stored only in local environment file if needed later",
            "status": "manual_check_required",
        },
        {
            "id": "system-state",
            "label": "Operator confirmed whether system is new/factory or existing",
            "status": "manual_check_required",
        },
        {
            "id": "no-data-change",
            "label": "No existing data should be modified by this preview",
            "status": "enforced",
        },
    ]


def _readiness_buckets() -> dict[str, dict[str, Any]]:
    credentials_present = bool(settings.netapp_api_username and settings.netapp_api_password)
    readonly_ack = settings.lab_readonly_ack == "YES"
    return {
        "physical_access_readiness": {
            "status": "manual_check_required",
            "ready": False,
            "details": ["Power, cabling, rack access, and controller identity are not verified by this app."],
        },
        "console_access_readiness": {
            "status": "read_only_probe_available"
            if settings.provider_mode in REAL_CONTACT_MODES
            else "manual_check_required",
            "ready": False,
            "details": [
                "Serial console access can be checked with newline-only discovery in real-lab modes.",
                "No credentials, boot interrupts, or setup commands are sent.",
            ],
        },
        "sp_network_readiness": {
            "status": "planned_not_probed",
            "ready": False,
            "details": [
                "Controller SP addresses are planned but not probed.",
                "SP reachable/missing remains a setup blocker.",
            ],
        },
        "management_ip_plan_readiness": {
            "status": "planned_not_live",
            "ready": False,
            "details": [
                "Cluster, node, SVM, and iSCSI management targets are planned only.",
                "Cluster management is not configured until live verification marks it ready.",
                "Node management is not configured.",
                "SVM management and iSCSI LIF range are planned but not live.",
            ],
        },
        "api_access_readiness": {
            "status": "configured" if credentials_present else "missing",
            "ready": False,
            "details": [
                "Credentials are required only for a future approved local-readonly probe.",
                "Credentials are missing." if not credentials_present else "Credentials are present but not returned.",
            ],
        },
        "local_readonly_ack_readiness": {
            "status": "acknowledged" if readonly_ack else "missing",
            "ready": False,
            "details": [
                "LAB_READONLY_ACK=YES is required before future safe probes.",
                "Provider mode must be local-readonly for explicit probes; mock mode does not probe NetApp.",
            ],
        },
        "bootstrap_intent_readiness": {
            "status": "blocked_preview_only",
            "ready": False,
            "details": ["Cluster create, controller join, and network configuration are disabled."],
        },
        "future_discovery_readiness": {
            "status": "blocked_until_approved",
            "ready": False,
            "details": ["Future read-only discovery requires explicit approval and configuration."],
        },
    }


def _disabled_console_actions() -> list[ProviderAction]:
    return disabled_netapp_actions(
        "open-console",
        "send-console-commands",
        "interrupt-boot",
        "configure-sp-ip",
        "create-cluster",
        "join-controller",
        "configure-cluster-management",
        "configure-node-management",
        "configure-svm",
        "configure-lifs",
        "reboot-controller",
        "wipe-disks",
    )
