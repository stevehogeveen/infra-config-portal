from __future__ import annotations

from typing import Any

from app.providers.ilo_redfish import IloRedfishConfig
from app.schemas import HpeVsanReadinessRead
from app.services.hpe_raid import get_hpe_storage_discovery


MODE_MEANINGS = {
    "mixed": "Mixed: drives outside RAID volumes pass through raw",
    "hba": "HBA: all drives raw",
    "raid": "RAID: no passthrough",
}


def get_hpe_vsan_readiness(
    config: IloRedfishConfig | None = None,
) -> HpeVsanReadinessRead:
    discovery = (
        get_hpe_storage_discovery(config=config)
        if config is not None
        else get_hpe_storage_discovery()
    )
    if not discovery.storage_inventory_available or not discovery.physical_drives:
        return HpeVsanReadinessRead(
            provider_id=discovery.provider_id,
            source=discovery.source,
            last_probe_time=discovery.last_probe_time,
            blockers=["No cached iLO storage inventory is available."],
            next_safe_action="Run iLO Inventory Read first.",
        )

    # The discovery lists both Redfish views; the bare DMTF "Storage View"
    # stub carries no model or operating mode. Pick the entry that actually
    # reports a mode, then one with a model, before falling back to first.
    controller_raw = next(
        (c for c in discovery.controllers if c.get("CurrentOperatingMode") or c.get("current_operating_mode")),
        next(
            (c for c in discovery.controllers if c.get("Model") or c.get("model")),
            discovery.controllers[0] if discovery.controllers else {},
        ),
    )
    mode = str(controller_raw.get("CurrentOperatingMode") or controller_raw.get("current_operating_mode") or "Unknown")
    memberships, membership_pairing_complete = _volume_memberships(discovery.logical_drives)
    drives = [
        _drive_readiness(drive, memberships, mode, membership_pairing_complete)
        for drive in discovery.physical_drives
    ]
    ready = [drive for drive in drives if drive["vsan_status"] == "passthrough_ready"]
    ready_bytes = sum(int(drive.get("capacity_bytes") or 0) for drive in ready)
    return HpeVsanReadinessRead(
        provider_id=discovery.provider_id,
        source=discovery.source,
        last_probe_time=discovery.last_probe_time,
        storage_inventory_available=True,
        controller={
            "model": controller_raw.get("Model") or controller_raw.get("model") or controller_raw.get("display_label"),
            "firmware": controller_raw.get("FirmwareVersion") or controller_raw.get("firmware"),
            "current_operating_mode": mode,
            "mode_meaning": MODE_MEANINGS.get(mode.lower(), f"{mode}: passthrough behavior is not known"),
            "apply_enabled": False,
        },
        drives=drives,
        summary={
            "physical_drive_count": len(drives),
            "passthrough_ready_count": len(ready),
            "passthrough_ready_capacity_bytes": ready_bytes,
        },
        options=_options(),
        apply_enabled=False,
        next_safe_action="Review architecture readiness and verify the exact ESXi build, driver, and firmware in the VMware Compatibility Guide.",
    )


def _volume_memberships(volumes: list[dict[str, Any]]) -> tuple[dict[str, str], bool]:
    memberships: dict[str, str] = {}
    pairing_complete = True
    for volume in volumes:
        name = str(volume.get("display_label") or volume.get("Name") or volume.get("Id") or "RAID volume")
        members = (volume.get("Links") or {}).get("Drives") or []
        if not members:
            # A volume whose members we cannot enumerate (e.g. the
            # SmartStorage view only carries a DataDrives collection
            # reference, as on the Uplands DL380) proves nothing about any
            # drive. Marking the rest "ready" would falsely clear the
            # drives that are actually inside this volume.
            pairing_complete = False
            continue
        for member in members:
            fingerprint = member.get("hardware_identity_fingerprint_sha256")
            if fingerprint:
                memberships[str(fingerprint).lower()] = name
            else:
                pairing_complete = False
    return memberships, pairing_complete


def _drive_readiness(
    drive: dict[str, Any],
    memberships: dict[str, str],
    mode: str,
    membership_pairing_complete: bool,
) -> dict[str, Any]:
    fingerprint = str(drive.get("hardware_identity_fingerprint_sha256") or "").lower()
    volume = memberships.get(fingerprint) if fingerprint else None
    paired = bool(fingerprint)
    if not paired:
        status = "unknown"
    elif volume:
        status = "in_raid_volume"
    elif not membership_pairing_complete:
        status = "unknown"
    elif mode.lower() in {"mixed", "hba"}:
        status = "passthrough_ready"
    else:
        status = "unknown"
    return {
        "bay_id": drive.get("bay_id"),
        "capacity_bytes": drive.get("capacity_bytes"),
        "capacity_label": drive.get("capacity_label"),
        "media_type": drive.get("media_type"),
        "health": drive.get("health"),
        "vsan_status": status,
        "volume_name": volume,
        "apply_enabled": False,
    }


def _options() -> list[dict[str, Any]]:
    return [
        {"id": "stay_mixed", "title": "Stay in Mixed mode", "detail": "Keep candidate drives outside logical volumes so they pass through raw. Blocked drives would require guarded, destructive volume deletion; that action is not available.", "apply_enabled": False},
        {"id": "switch_hba", "title": "Switch the controller to HBA mode", "detail": "Controller-wide and destructive to existing volumes; requires a guarded configuration write and reboot. That action is not available.", "apply_enabled": False},
        {"id": "vmware_compatibility", "title": "Verify VMware compatibility", "detail": "Architecture readiness is not vSAN certification. Compatibility depends on the exact ESXi build, driver, controller firmware, and VMware Compatibility Guide entry; the app cannot verify it.", "apply_enabled": False},
    ]
