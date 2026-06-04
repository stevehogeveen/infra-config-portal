from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

PROVIDER_ID = "netapp-ontap"
OBSERVED_CONSOLE_STATES = {
    "unknown",
    "loader_prompt",
    "boot_menu",
    "cluster_setup_prompt",
    "existing_cluster_login",
    "other",
}
FORBIDDEN_OPERATOR_NOTE_FRAGMENTS = (
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
)

_OBSERVATION_STORE: dict[str, Any] | None = None


def default_netapp_observations() -> dict[str, Any]:
    return {
        "provider_id": PROVIDER_ID,
        "observed_console_state": "unknown",
        "controller_a_console_seen": False,
        "controller_b_console_seen": False,
        "controller_a_sp_cabled": False,
        "controller_b_sp_cabled": False,
        "management_network_reviewed": False,
        "planned_targets_reviewed": False,
        "existing_data_risk_acknowledged": False,
        "operator_notes": "",
        "updated_at": datetime.now(UTC),
        "updated_by": "system",
        "mock_only": True,
        "sent_to_netapp": False,
    }


def get_netapp_observations() -> dict[str, Any]:
    if _OBSERVATION_STORE is None:
        return default_netapp_observations()
    return dict(_OBSERVATION_STORE)


def save_netapp_observations(payload: dict[str, Any], updated_by: str) -> dict[str, Any]:
    global _OBSERVATION_STORE
    observed_state = payload.get("observed_console_state", "unknown")
    if observed_state not in OBSERVED_CONSOLE_STATES:
        raise ValueError("observed_console_state is not valid")
    operator_notes = validate_netapp_operator_notes(payload.get("operator_notes", ""))

    _OBSERVATION_STORE = {
        "provider_id": PROVIDER_ID,
        "observed_console_state": observed_state,
        "controller_a_console_seen": bool(payload.get("controller_a_console_seen", False)),
        "controller_b_console_seen": bool(payload.get("controller_b_console_seen", False)),
        "controller_a_sp_cabled": bool(payload.get("controller_a_sp_cabled", False)),
        "controller_b_sp_cabled": bool(payload.get("controller_b_sp_cabled", False)),
        "management_network_reviewed": bool(payload.get("management_network_reviewed", False)),
        "planned_targets_reviewed": bool(payload.get("planned_targets_reviewed", False)),
        "existing_data_risk_acknowledged": bool(payload.get("existing_data_risk_acknowledged", False)),
        "operator_notes": operator_notes,
        "updated_at": datetime.now(UTC),
        "updated_by": updated_by,
        "mock_only": True,
        "sent_to_netapp": False,
    }
    return dict(_OBSERVATION_STORE)


def validate_netapp_operator_notes(value: str | None) -> str:
    notes = str(value or "").strip()
    lower_notes = notes.lower()
    if any(fragment in lower_notes for fragment in FORBIDDEN_OPERATOR_NOTE_FRAGMENTS):
        raise ValueError(
            "operator_notes must not include password, secret, token, credential, "
            "authorization, or cookie values"
        )
    return notes


def summarize_netapp_observations(observations: dict[str, Any]) -> dict[str, Any]:
    required_checks = [
        "controller_a_console_seen",
        "controller_a_sp_cabled",
        "controller_b_sp_cabled",
        "management_network_reviewed",
        "planned_targets_reviewed",
        "existing_data_risk_acknowledged",
    ]
    optional_checks = ["controller_b_console_seen"]
    completed_checks = [check for check in required_checks if observations.get(check) is True]
    missing_checks = [check for check in required_checks if observations.get(check) is not True]
    completed_optional_checks = [
        check for check in optional_checks if observations.get(check) is True
    ]
    missing_optional_checks = [
        check for check in optional_checks if observations.get(check) is not True
    ]
    return {
        "status": "recorded" if completed_checks else "not_recorded",
        "observed_console_state": observations.get("observed_console_state", "unknown"),
        "required_check_count": len(required_checks),
        "completed_check_count": len(completed_checks),
        "missing_checks": missing_checks,
        "optional_check_count": len(optional_checks),
        "completed_optional_check_count": len(completed_optional_checks),
        "missing_optional_checks": missing_optional_checks,
        "notes_recorded": bool(observations.get("operator_notes")),
        "mock_only": True,
        "sent_to_netapp": False,
    }


def netapp_observation_blockers(observations: dict[str, Any]) -> list[str]:
    summary = summarize_netapp_observations(observations)
    blockers: list[str] = []
    if summary["observed_console_state"] == "unknown":
        blockers.append("Observed console state has not been recorded.")
    missing_labels = {
        "controller_a_console_seen": "Controller A console has not been marked as seen.",
        "controller_a_sp_cabled": "Controller A SP cabling has not been marked reviewed.",
        "controller_b_sp_cabled": "Controller B SP cabling has not been marked reviewed.",
        "management_network_reviewed": "Management network review has not been marked complete.",
        "planned_targets_reviewed": "Planned NetApp target addresses have not been marked reviewed.",
        "existing_data_risk_acknowledged": "Existing data risk has not been acknowledged.",
    }
    blockers.extend(missing_labels[check] for check in summary["missing_checks"])
    return blockers


def reset_netapp_observations() -> None:
    global _OBSERVATION_STORE
    _OBSERVATION_STORE = None
