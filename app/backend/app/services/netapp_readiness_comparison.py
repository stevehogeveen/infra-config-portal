from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.providers.base import ProviderAction
from app.services.netapp_disabled_actions import disabled_netapp_actions
from app.services.netapp_observations import get_netapp_observations


PROVIDER_ID = "netapp-ontap"
READINESS_COMPARISON_ENDPOINT = "/api/v1/providers/netapp-ontap/readiness-comparison"


def get_netapp_readiness_comparison() -> dict[str, Any]:
    planned_targets = _planned_targets()
    observations = get_netapp_observations()
    comparison_items = _comparison_items(planned_targets, observations)
    matched_items = [item for item in comparison_items if item["status"] == "matched"]
    unknown_items = [item for item in comparison_items if item["status"] == "unknown"]
    warning_items = [item for item in comparison_items if item["status"] == "warning"]
    blocker_items = [item for item in comparison_items if item["status"] == "blocker"]
    dynamic_blockers = [item["next_action"] for item in blocker_items if item["next_action"]]

    return {
        "provider_id": PROVIDER_ID,
        "mode": settings.provider_mode,
        "comparison_enabled": True,
        "apply_enabled": False,
        "discovery_enabled": False,
        "planned_targets": planned_targets,
        "current_discovered_targets": _current_discovered_targets(),
        "observations": observations,
        "comparison_items": comparison_items,
        "matched_items": matched_items,
        "unknown_items": unknown_items,
        "warning_items": warning_items,
        "blocker_items": blocker_items,
        "blockers": [
            "Live NetApp discovery is disabled; comparison uses planned targets and manual observations only.",
            "Apply, probe, console, bootstrap, and configuration actions are disabled.",
            "NETAPP_CONFIGURED=false; cluster management is not treated as reachable.",
            "Credentials are missing." if not _credentials_present() else "Credentials are present but not returned.",
            "LAB_READONLY_ACK=YES is missing for future safe probes."
            if settings.lab_readonly_ack != "YES"
            else "LAB_READONLY_ACK=YES is present.",
            *dynamic_blockers,
        ],
        "warnings": [
            "Matched items mean the operator recorded the expected manual observation; they are not device-discovered facts.",
            *[item["next_action"] for item in warning_items if item["next_action"]],
        ],
        "removable_warnings": [
            item["next_action"]
            for item in [*unknown_items, *warning_items]
            if item["next_action"]
        ],
        "next_safe_action": (
            "Review unknown, warning, or blocker comparison rows, update operator observations manually, "
            "and keep NetApp discovery/apply disabled until a future approved read-only task exists."
        ),
        "disabled_actions": _disabled_comparison_actions(),
    }


def _planned_targets() -> dict[str, Any]:
    iscsi_lifs = list(settings.netapp_iscsi_lifs)
    return {
        "sp_ips": {
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
    return {
        "discovery_enabled": False,
        "source": "not_discovered",
        "sp_ips": {"controller_a": None, "controller_b": None},
        "management_ips": {"cluster": None, "node_a": None, "node_b": None, "svm": None},
        "iscsi_lif_range": {"start": None, "end": None, "addresses": []},
    }


def _comparison_items(
    planned_targets: dict[str, Any],
    observations: dict[str, Any],
) -> list[dict[str, Any]]:
    sp_ips = planned_targets["sp_ips"]
    management_ips = planned_targets["management_ips"]
    lif_range = planned_targets["iscsi_lif_range"]
    console_state = observations.get("observed_console_state", "unknown")

    return [
        _planned_not_live_item(
            id_="cluster-management-not-configured",
            label="Cluster management",
            planned=f"Cluster management planned at {management_ips['cluster']}",
            observed="Not discovered; not treated as reachable while NETAPP_CONFIGURED=false",
            next_action="Configure cluster management outside this portal before any future read-only ONTAP probe.",
        ),
        _planned_not_live_item(
            id_="node-management-not-configured",
            label="Node management",
            planned=(
                f"Node A planned at {management_ips['node_a']}; "
                f"Node B planned at {management_ips['node_b']}"
            ),
            observed="Not discovered or configured",
            next_action="Complete node management configuration outside this portal before upgrade readiness.",
        ),
        _planned_not_live_item(
            id_="svm-management-planned-not-live",
            label="SVM management",
            planned=f"SVM management planned at {management_ips['svm']}",
            observed="Not live / not discovered",
            next_action="Create or verify SVM management outside this portal before storage workflows.",
        ),
        _planned_not_live_item(
            id_="iscsi-lif-range-planned-not-live",
            label="iSCSI LIF range",
            planned=f"iSCSI LIFs planned from {lif_range['start']} to {lif_range['end']}",
            observed="No live iSCSI LIFs discovered",
            next_action="Create or verify iSCSI LIFs outside this portal before storage workflows.",
        ),
        _boolean_item(
            id_="controller-a-sp-cabling",
            label="Controller A SP cabling",
            planned=f"Controller A SP planned at {sp_ips['controller_a']}",
            observed="Marked cabled" if observations.get("controller_a_sp_cabled") else "Not recorded",
            observed_flag=observations.get("controller_a_sp_cabled"),
            unknown_action="Manually confirm Controller A SP cabling and update observations.",
        ),
        _boolean_item(
            id_="controller-b-sp-cabling",
            label="Controller B SP cabling",
            planned=f"Controller B SP planned at {sp_ips['controller_b']}",
            observed="Marked cabled" if observations.get("controller_b_sp_cabled") else "Not recorded",
            observed_flag=observations.get("controller_b_sp_cabled"),
            unknown_action="Manually confirm Controller B SP cabling and update observations.",
        ),
        _boolean_item(
            id_="controller-a-console",
            label="Controller A console access",
            planned="Manual console access is expected for bootstrap readiness.",
            observed="Console seen" if observations.get("controller_a_console_seen") else "Not recorded",
            observed_flag=observations.get("controller_a_console_seen"),
            unknown_action="Connect operator-managed console to Controller A and record observed state.",
        ),
        _boolean_item(
            id_="controller-b-console",
            label="Controller B console access",
            planned="Controller B console observation is optional but useful before future discovery.",
            observed="Console seen" if observations.get("controller_b_console_seen") else "Not recorded",
            observed_flag=observations.get("controller_b_console_seen"),
            unknown_action="Record Controller B console state if available.",
            false_status="warning",
        ),
        _boolean_item(
            id_="management-network-review",
            label="Management network review",
            planned=(
                "Cluster, node, and SVM management IPs are planned: "
                f"{management_ips['cluster']}, {management_ips['node_a']}, "
                f"{management_ips['node_b']}, {management_ips['svm']}."
            ),
            observed="Reviewed" if observations.get("management_network_reviewed") else "Not recorded",
            observed_flag=observations.get("management_network_reviewed"),
            unknown_action="Manually review management network reachability from the app host.",
        ),
        _boolean_item(
            id_="planned-target-review",
            label="Planned target address review",
            planned=(
                "SP, cluster, node, SVM, and iSCSI targets are planned, including "
                f"iSCSI LIFs {lif_range['start']} to {lif_range['end']}."
            ),
            observed="Reviewed" if observations.get("planned_targets_reviewed") else "Not recorded",
            observed_flag=observations.get("planned_targets_reviewed"),
            unknown_action="Review all planned NetApp target addresses and update observations.",
        ),
        _boolean_item(
            id_="existing-data-risk",
            label="Existing data risk",
            planned="Operator must confirm no existing data should be modified by this preview.",
            observed=(
                "Risk acknowledged"
                if observations.get("existing_data_risk_acknowledged")
                else "Not acknowledged"
            ),
            observed_flag=observations.get("existing_data_risk_acknowledged"),
            unknown_action="Confirm whether the system is new/factory or existing before future discovery.",
            false_status="blocker",
        ),
        {
            "id": "console-state",
            "label": "Console state",
            "planned": "Expected safe states: LOADER prompt, boot menu, cluster setup prompt, existing cluster login, or other manually described state.",
            "observed": _console_state_label(console_state),
            "status": "unknown" if console_state == "unknown" else "matched",
            "next_action": (
                "Record the observed console prompt/state."
                if console_state == "unknown"
                else "Keep this as a manual observation; no console command is sent by the portal."
            ),
            "source": "operator_observation",
        },
    ]


def _planned_not_live_item(
    *,
    id_: str,
    label: str,
    planned: str,
    observed: str,
    next_action: str,
) -> dict[str, Any]:
    return {
        "id": id_,
        "label": label,
        "planned": planned,
        "observed": observed,
        "status": "blocker",
        "next_action": next_action,
        "source": "planned_target",
    }


def _credentials_present() -> bool:
    return bool(settings.netapp_api_username and settings.netapp_api_password)


def _boolean_item(
    *,
    id_: str,
    label: str,
    planned: str,
    observed: str,
    observed_flag: Any,
    unknown_action: str,
    false_status: str = "unknown",
) -> dict[str, Any]:
    matched = observed_flag is True
    return {
        "id": id_,
        "label": label,
        "planned": planned,
        "observed": observed,
        "status": "matched" if matched else false_status,
        "next_action": (
            "No action for this manual check; keep NetApp apply disabled."
            if matched
            else unknown_action
        ),
        "source": "operator_observation",
    }


def _console_state_label(value: str) -> str:
    labels = {
        "unknown": "Unknown / unverified",
        "loader_prompt": "LOADER prompt",
        "boot_menu": "Boot menu",
        "cluster_setup_prompt": "Cluster setup prompt",
        "existing_cluster_login": "Existing cluster login",
        "other": "Other manually observed state",
    }
    return labels.get(value, "Unknown / unverified")


def _disabled_comparison_actions() -> list[ProviderAction]:
    return disabled_netapp_actions(
        "discover-live-state",
        "open-console",
        "send-console-commands",
        "probe-sp",
        "probe-ontap-api",
        "create-cluster",
        "change-ips",
        "create-svm",
        "create-lifs",
        "create-volumes",
        "upgrade-ontap",
        "reboot-controller",
        "wipe-disks",
        "apply-configuration",
    )
