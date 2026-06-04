from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.providers.base import ProviderAction
from app.schemas import MediaInventoryItemRead
from app.services.media_inventory import get_media_inventory
from app.services.netapp_disabled_actions import disabled_netapp_actions


PROVIDER_ID = "netapp-ontap"
UPGRADE_READINESS_ENDPOINT = "/api/v1/providers/netapp-ontap/upgrade-readiness"


def get_netapp_upgrade_readiness() -> dict[str, Any]:
    media_inventory = get_media_inventory()
    current_version = settings.netapp_current_ontap_version
    credentials_present = bool(settings.netapp_api_username and settings.netapp_api_password)
    readonly_ack = settings.lab_readonly_ack == "YES"
    candidates = [_candidate_from_media(item) for item in media_inventory.items if _is_ontap_media(item)]
    candidates = [_match_candidate(candidate, current_version) for candidate in candidates]
    versioned_candidates = [
        candidate for candidate in candidates if _version_key(candidate.get("version")) is not None
    ]
    recommended = _recommended_target(current_version, versioned_candidates)
    upgrade_chain = [
        candidate
        for candidate in versioned_candidates
        if recommended is not None and candidate.get("version") == recommended
    ]
    blockers = [
        "Upgrade readiness is separate from setup readiness; setup is not ready.",
        "NETAPP_CONFIGURED=false; cluster management is planned but not reachable.",
        "Node management is planned but not configured.",
        "SVM management and iSCSI LIFs are planned but not live.",
        "Current ONTAP version is not discovered; live controller queries are disabled.",
        "NetApp API credentials are missing." if not credentials_present else "NetApp API credentials are present but not returned.",
        "LAB_READONLY_ACK=YES is missing for future safe probes."
        if not readonly_ack
        else "LAB_READONLY_ACK=YES is present.",
        "ONTAP upgrade actions are disabled; preview only.",
    ]
    removable_warnings = list(media_inventory.warnings)
    if not candidates:
        removable_warnings.append(
            "Add ONTAP image media to the configured media inventory directory."
        )
    if media_inventory.mode == "sample":
        removable_warnings.append(
            "MEDIA_INVENTORY_DIRS is not configured; ONTAP media matching uses sample metadata only."
        )
    warnings = [
        "Offline media preview only. No ONTAP API, SSH, Service Processor, upload, upgrade, or reboot call is made.",
    ]
    if current_version:
        blockers = [
            "Upgrade readiness is separate from setup readiness; setup is not ready.",
            "NETAPP_CONFIGURED=false; cluster management is planned but not reachable.",
            "Node management is planned but not configured.",
            "Current ONTAP version is configured as a local placeholder, not discovered from a controller.",
            "NetApp API credentials are missing." if not credentials_present else "NetApp API credentials are present but not returned.",
            "LAB_READONLY_ACK=YES is missing for future safe probes."
            if not readonly_ack
            else "LAB_READONLY_ACK=YES is present.",
            "ONTAP upgrade actions are disabled; preview only.",
        ]

    return {
        "provider_id": PROVIDER_ID,
        "mode": settings.provider_mode,
        "apply_enabled": False,
        "upgrade_enabled": False,
        "setup_ready": False,
        "readiness_scope": "upgrade",
        "current_version_source": "configured" if current_version else "unknown",
        "current_version": current_version,
        "current_version_confidence": "placeholder" if current_version else "unknown",
        "media_inventory_mode": media_inventory.mode,
        "candidates": candidates,
        "recommended_target": recommended,
        "required_intermediate_versions": [],
        "upgrade_chain": upgrade_chain,
        "blockers": blockers,
        "warnings": warnings,
        "removable_warnings": _unique(removable_warnings),
        "next_safe_action": (
            "Add sanitized ONTAP image media metadata and keep upgrade disabled until a future "
            "approved read-only ONTAP discovery task confirms the running version."
        ),
        "disabled_actions": _disabled_upgrade_actions(),
    }


def _is_ontap_media(item: MediaInventoryItemRead) -> bool:
    hints = {hint.lower() for hint in item.product_hints}
    if "netapp-ontap" in hints:
        return True
    return item.category in {"firmware", "other"} and item.version_hint is not None and (
        item.extension in {".tgz", ".zip", ".tar", ".gz", ".iso"}
    )


def _candidate_from_media(item: MediaInventoryItemRead) -> dict[str, Any]:
    return {
        "id": item.placeholder_name,
        "category": item.category,
        "product_hint": "netapp-ontap" if "netapp-ontap" in item.product_hints else None,
        "version": item.version_hint,
        "source": item.source,
        "redacted_label": item.placeholder_name,
        "match_confidence": "unknown",
        "warnings": [],
    }


def _match_candidate(candidate: dict[str, Any], current_version: str | None) -> dict[str, Any]:
    warnings = list(candidate["warnings"])
    confidence = "likely" if candidate["product_hint"] == "netapp-ontap" else "weak"
    if not candidate["version"]:
        warnings.append("Candidate version could not be parsed from sanitized media metadata.")
        confidence = "weak"
    if current_version is None:
        warnings.append("Current ONTAP version is unknown; target comparison is not available.")
    return {**candidate, "match_confidence": confidence, "warnings": _unique(warnings)}


def _recommended_target(
    current_version: str | None,
    candidates: list[dict[str, Any]],
) -> str | None:
    if not candidates:
        return None
    sorted_candidates = sorted(
        candidates,
        key=lambda candidate: _version_key(candidate.get("version")) or (),
        reverse=True,
    )
    if current_version is None:
        return sorted_candidates[0].get("version")
    current_key = _version_key(current_version)
    if current_key is None:
        return sorted_candidates[0].get("version")
    newer = [
        candidate
        for candidate in sorted_candidates
        if (_version_key(candidate.get("version")) or ()) > current_key
    ]
    return (newer[0] if newer else sorted_candidates[0]).get("version")


def _version_key(version: str | None) -> tuple[int, ...] | None:
    if not version:
        return None
    parts: list[int] = []
    for raw in version.split("."):
        if not raw.isdigit():
            return None
        parts.append(int(raw))
    return tuple(parts) if parts else None


def _disabled_upgrade_actions() -> list[ProviderAction]:
    return disabled_netapp_actions(
        "upload-ontap-image",
        "stage-upgrade",
        "start-upgrade",
        "reboot-controller",
        "apply-upgrade",
    )


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
