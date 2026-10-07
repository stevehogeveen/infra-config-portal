"""Device-scoped, plan-only local storage preparation. Never sends hardware writes."""
import hashlib
import json
from datetime import datetime, UTC
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.rack_plans import get_plan, kit_profile
from app.auth import get_current_actor
from app.core.database import get_session
from app.providers.probe_cache import get_probe_result
from app.services.ilo_access_settings import read_ilo_access_settings
from app.services.hardware_values import firmware_version, health
from app.services.hardware_health import read_health_review, drive_condition
from app.services.hpe_raid import save_hpe_raid_intent, get_hpe_raid_intent
from app.schemas import HpeRaidIntentWrite, HpeRaidVolumeIntent
from app.services.audit import record_audit_event

router = APIRouter(prefix="/api/v1/rack-plans", tags=["disk preparation"])


class DiskPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inventory_token: str = Field(min_length=64, max_length=64)
    boot_drive_ids: list[str] = Field(min_length=2, max_length=2)
    remove_existing_volumes: bool = False
    data_loss_reviewed: bool = False
    data_drive_ids: list[str] = Field(default_factory=list, max_length=24)
    data_raid: Literal["RAID1", "RAID5", "RAID6", "RAID10"] = "RAID5"
    spare_drive_ids: list[str] = Field(default_factory=list, max_length=1)
    spare_for: Literal["boot", "data"] = "data"


@router.get("/{profile_id}/disk-preparation")
def disk_preparation(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    kit_profile(profile_id)
    item = next((i for i in get_plan(profile_id, session).equipment if i.device_id == device_id and i.kind == "server"), None)
    if not item:
        raise HTTPException(404, "Server is not in this kit.")
    access = read_ilo_access_settings(session, device_id)
    probe, checked_at = get_probe_result("ilo-redfish", scope=device_id)
    current = bool(probe and probe.get("status") == "ok" and access["last_probe_is_current"]
                   and access["last_probe_target_matches_access_host"]
                   and probe.get("mode") != "mock" and probe.get("source_type") not in {"mock", "test_fixture"})
    # Destructive preparation plans are tied to recent readings, not yesterday's layout.
    if current:
        try:
            age = (datetime.now(UTC) - datetime.fromisoformat(checked_at)).total_seconds()
            current = -30 <= age <= 300
        except (ValueError, TypeError):
            current = False
    storage = probe.get("storage", {}) if current else {}
    controllers = [r for r in storage.get("controllers", []) if r.get("Model")]
    drives, volumes = _drive_rows(storage), _volume_rows(storage)
    blockers = [] if current else ["Refresh drive inventory. A successful read of this exact server within the last five minutes is required."]
    if current and len(controllers) != 1:
        blockers.append("This guided planner requires one identified storage controller. Multiple controllers need an attended storage review.")
    if current and not drives:
        blockers.append("No physical drives reported by iLO.")
    if current and storage.get("warnings"):
        blockers.append("Storage inventory is incomplete. Resolve the reported discovery errors before planning a rebuild.")
    health_issues = [f"{d['location']}: {d['health']}" for d in drives if d["health"] != "OK"]
    health_issues += [f"{c['Model']}: {health(c)}" for c in controllers if health(c) != "OK"]
    basis = {"device": device_id, "target": probe.get("target_fingerprint") if current else None,
             "checked_at": checked_at, "controllers": controllers, "drives": drives, "volumes": volumes}
    token = hashlib.sha256(json.dumps(basis, sort_keys=True).encode()).hexdigest()
    intent = get_hpe_raid_intent(session, device_id)
    boot_intents = [v for v in intent.volumes if v.bootable and v.raid_level.upper() == "RAID1"]
    planned_bays = set(boot_intents[0].drive_bays) if len(boot_intents) == 1 else set()
    expected_paths = {d["id"].rstrip("/") for d in drives if d["location"] in planned_bays and d["eligible"]}
    mirror_matches = bool(current and not blockers and len(planned_bays) == len(expected_paths) == 2 and any(
        str(v.get("RAIDType") or "RAID" + str(v.get("Raid", ""))).upper() == "RAID1"
        and health(v) == "OK" and {path.rstrip("/") for path in v.get("physical_drive_paths", [])} == expected_paths
        for v in storage.get("logical_drives", [])))
    return {"name": item.name, "model": item.model, "host": access["host"], "current": current,
            "checked_at": checked_at, "inventory_token": token, "controllers": [{"id": c.get("@odata.id"), "model": c["Model"], "health": health(c), "firmware": firmware_version(c)} for c in controllers],
            "drives": drives, "volumes": volumes, "blockers": blockers, "health_issues": health_issues,
            "saved_intent": intent, "apply_enabled": False, "boot_mirror_matches": mirror_matches,
            "health_review": read_health_review(session, profile_id, device_id),
            # The last read, kept for display only when it is too old to plan from. Nothing may be
            # saved or applied from it; the fields above stay empty until a fresh read.
            "last_read": None if current or not probe or probe.get("status") != "ok" or probe.get("mode") == "mock"
            or probe.get("source_type") in {"mock", "test_fixture"} or not access["last_probe_target_matches_access_host"] else {
                "checked_at": checked_at, "drives": _drive_rows(probe.get("storage") or {}),
                "volumes": _volume_rows(probe.get("storage") or {})},
            "cleanup_method": "Attended HPE Smart Storage Administrator (SSA). Remove only the reviewed logical volumes, then refresh inventory here. This is not physical-drive secure erase."}


@router.post("/{profile_id}/disk-preparation")
def save_disk_preparation(profile_id: str, device_id: str, payload: DiskPlan,
                          session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    view = disk_preparation(profile_id, device_id, session)
    if view["blockers"]:
        raise HTTPException(409, " ".join(view["blockers"]))
    if view["inventory_token"] != payload.inventory_token:
        raise HTTPException(409, "Hardware readings changed. Refresh and review the plan again.")
    selected = [d for d in view["drives"] if d["id"] in payload.boot_drive_ids]
    if len(set(payload.boot_drive_ids)) != 2 or len(selected) != 2 or not all(d["eligible"] for d in selected):
        raise HTTPException(422, "Select exactly two healthy, identified drives for the ESXi mirror.")
    controller = view["controllers"][0]
    if not all(d["id"].startswith(controller["id"].rstrip("/") + "/") for d in selected):
        raise HTTPException(422, "Boot drives must belong to the selected controller.")
    if len({(d["capacity_bytes"], d["media"]) for d in selected}) != 1:
        raise HTTPException(422, "Select two drives with matching capacity and media type.")
    if view["volumes"] and not (payload.remove_existing_volumes and payload.data_loss_reviewed):
        raise HTTPException(422, "Review existing logical volumes and acknowledge their data loss before saving replacement intent.")
    volumes = [HpeRaidVolumeIntent(name="ESXi boot", purpose="esxi_boot", raid_level="RAID1", drive_bays=[d["location"] for d in selected], bootable=True)]
    if payload.data_drive_ids:
        data = [d for d in view["drives"] if d["id"] in payload.data_drive_ids]
        count = len(data)
        valid_count = count == 2 if payload.data_raid == "RAID1" else count >= 3 if payload.data_raid == "RAID5" else count >= 4 and (payload.data_raid != "RAID10" or count % 2 == 0)
        if (len(set(payload.data_drive_ids)) != len(payload.data_drive_ids) or count != len(payload.data_drive_ids)
                or set(payload.boot_drive_ids) & set(payload.data_drive_ids) or not valid_count
                or not all(d["eligible"] and d["id"].startswith(controller["id"].rstrip("/") + "/") for d in data)
                or len({(d["capacity_bytes"], d["media"]) for d in data}) != 1):
            raise HTTPException(422, "Choose healthy matching data drives on this controller, separate from the boot pair. RAID1 needs 2, RAID5 at least 3, RAID6 at least 4, and RAID10 an even number of at least 4.")
        volumes.append(HpeRaidVolumeIntent(name="VM data", purpose="local_datastore", raid_level=payload.data_raid, drive_bays=[d["location"] for d in data], bootable=False))
    if payload.spare_drive_ids:
        protected = selected if payload.spare_for == "boot" else [d for d in view["drives"] if d["id"] in payload.data_drive_ids]
        spares = [d for d in view["drives"] if d["id"] in payload.spare_drive_ids]
        if (not protected or len(spares) != 1
                or set(payload.spare_drive_ids) & set(payload.boot_drive_ids + payload.data_drive_ids)
                or not all(d["eligible"] and d["id"].startswith(controller["id"].rstrip("/") + "/")
                           and d["media"] == protected[0]["media"]
                           and d["capacity_bytes"] >= max(p["capacity_bytes"] for p in protected) for d in spares)):
            raise HTTPException(422, "Choose one healthy, unused hot spare on this controller, with matching media and at least the capacity of each drive in the protected array.")
        volume = volumes[0] if payload.spare_for == "boot" else volumes[1]
        volume.spare_bays = [d["location"] for d in spares]
        volume.spare_rebuild_mode = "Dedicated"
    intent = HpeRaidIntentWrite(controller_ref=controller["id"], wipe_existing_logical_drives=bool(view["volumes"] and payload.remove_existing_volumes),
                               volumes=volumes, notes="Reviewed guided storage plan. Unselected drives remain unassigned. No hardware change executed.")
    saved = save_hpe_raid_intent(session, device_id, intent)
    record_audit_event(session, actor=actor, event_type="kit.disk_preparation_planned", message="Saved reviewed storage intent, no disk operations executed.",
                       data={"profile_id": profile_id, "device_id": device_id, "inventory_token": view["inventory_token"],
                             "boot_drive_ids": payload.boot_drive_ids, "data_drive_ids": payload.data_drive_ids,
                             "spare_drive_ids": payload.spare_drive_ids, "spare_for": payload.spare_for,
                             "reviewed_volumes": view["volumes"] if view["volumes"] else [], "health_issues": view["health_issues"]})
    session.commit()
    return {"status": "Plan saved", "intent": saved, "apply_enabled": False,
            "message": "No disks changed. Review RAID rebuild to clear the old layout and create the saved arrays, or use attended HPE SSA."}


def _drive_rows(storage: dict) -> list[dict]:
    drives = []
    for drive in storage.get("physical_drives", []):
        condition = drive_condition(drive)
        drives.append({"id": drive.get("@odata.id", ""), "location": str(drive.get("Location") or drive.get("Bay") or "Unknown bay"),
                       "model": drive.get("Model") or "Not identified", "capacity_bytes": drive.get("CapacityBytes", 0),
                       **condition, "firmware": firmware_version(drive), "media": drive.get("MediaType", ""),
                       "identity": drive.get("hardware_identity_fingerprint_sha256"),
                       "eligible": bool(condition["presence"] == "identified" and drive.get("@odata.id") and drive.get("Model") and drive.get("Location") and drive.get("CapacityBytes", 0) > 0 and health(drive) == "OK")})
    return drives


def _volume_rows(storage: dict) -> list[dict]:
    """Logical drives with the bays they use, matched through the member drive paths."""
    bay_by_path = {str(d.get("@odata.id") or "").rstrip("/"): str(d.get("Location") or d.get("Bay") or "")
                   for d in storage.get("physical_drives", [])}
    return [{"id": r.get("@odata.id", ""), "name": f"Logical drive {r.get('Id', '?')}", "raid": r.get("RAIDType") or r.get("Raid") or "Unknown",
             "capacity_bytes": r.get("CapacityBytes", 0),
             "bays": [bay for bay in (bay_by_path.get(str(p).rstrip("/")) for p in r.get("physical_drive_paths") or []) if bay]}
            for r in storage.get("logical_drives", [])]
