import re
from copy import deepcopy
from uuid import uuid4
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator, ValidationError
from sqlalchemy import update, select, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_actor
from app.core.database import get_session
from app.models import RackLayoutPlan, DeviceInventory, AuditEvent
from datetime import UTC, datetime
from app.services.ilo_access_settings import read_ilo_access_settings, is_ilo_device_type
from app.providers.probe_cache import get_probe_result
from app.services.audit import record_audit_event
from app.services.lab_profiles import (list_lab_profiles, create_lab_profile, rename_kit,
                                      discard_unfinished_kit, LabProfileNotFoundError)
from app.schemas import LabProfileWrite
from app.services.firmware_packages import browse_packages, inspect_package, package_unchanged, FirmwarePackageError
from app.services.media_upload import receive_iso
from app.services.spp_assessment import assess, load_catalog
from app.services.hardware_health import read_health_review


class RackEquipment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["server", "switch", "ups", "pdu", "storage"]
    device_id: str | None = Field(default=None, max_length=36)
    model: str = Field(default="", max_length=120)
    position: int = Field(ge=1, le=60)
    height: int = Field(ge=1, le=12)
    mount: Literal["rack", "left", "right"] = "rack"
    ports: Literal[0, 24, 48] = 0
    uplink_ports: Literal[0, 4] = 0
    bay_count: int = Field(default=0, ge=0, le=24)
    occupied_bays: list[int] = Field(default_factory=list, max_length=24)

    @model_validator(mode="after")
    def validate_equipment(self):
        if not self.name.strip():
            raise ValueError("Equipment name is required.")
        if self.mount != "rack" and self.kind != "pdu":
            raise ValueError("Only a PDU can use a side mount.")
        if self.kind not in ("server", "storage") and (self.bay_count or self.occupied_bays):
            raise ValueError("Drive bays belong to servers or storage.")
        if self.kind == "switch" and self.ports not in (24, 48):
            raise ValueError("Choose 24 or 48 switch ports.")
        if self.kind != "switch" and (self.ports or self.uplink_ports):
            raise ValueError("Port count belongs to a switch.")
        if len(set(self.occupied_bays)) != len(self.occupied_bays) or any(
            bay < 1 or bay > self.bay_count for bay in self.occupied_bays
        ):
            raise ValueError("Installed drives must occupy distinct existing bays.")
        return self


class RackPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(default=0, ge=0)
    rack_units: int = Field(default=12, ge=4, le=60)
    equipment: list[RackEquipment] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_layout(self):
        ids = set()
        device_ids = set()
        occupied = set()
        for item in self.equipment:
            if item.id in ids:
                raise ValueError("Equipment identifiers must be unique.")
            ids.add(item.id)
            if item.device_id:
                if item.device_id in device_ids:
                    raise ValueError("A hardware device can only occupy one rack position.")
                device_ids.add(item.device_id)
            if item.position + item.height - 1 > self.rack_units:
                raise ValueError(f"{item.name} extends beyond the rack.")
            for unit in range(item.position, item.position + item.height):
                key = (item.mount, unit)
                if key in occupied:
                    raise ValueError(f"{item.name} overlaps another item at U{unit}.")
                occupied.add(key)
        return self


router = APIRouter(prefix="/api/v1/rack-plans", tags=["rack plans"])


class KitName(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=2, max_length=120)


class FirmwarePackageSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=1000)


@router.post("/{profile_id}/media-upload", status_code=201)
async def upload_media(profile_id: str, request: Request, name: str = Query(min_length=1, max_length=240),
                       size: int = Query(gt=0, le=128 * 1024**3), folder: str = "",
                       kind: Literal["iso", "vm"] = "iso", actor: str = Depends(get_current_actor)):
    kit_profile(profile_id)
    return await receive_iso(request.stream(), name, size, folder, kind)


@router.get("/{profile_id}/firmware-package")
def firmware_package_source(profile_id: str, folder: str = "", session: Session = Depends(get_session)):
    kit_profile(profile_id)
    try:
        source = browse_packages(folder)
    except FirmwarePackageError as exc:
        raise HTTPException(422, str(exc)) from exc
    row = session.scalar(select(AuditEvent).where(
        AuditEvent.event_type == "kit.firmware_package_selected",
        AuditEvent.data_json["profile_id"].as_string() == profile_id,
    ).order_by(AuditEvent.created_at.desc()).limit(1))
    package = row.data_json["package"] if row else None
    return {**source, "selected": package, "selection_current": package_unchanged(package) if package else False}


@router.post("/{profile_id}/firmware-package")
def select_firmware_package(profile_id: str, payload: FirmwarePackageSelection,
                            session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    kit_profile(profile_id)
    try:
        package = inspect_package(payload.path)
    except (FirmwarePackageError, OSError) as exc:
        raise HTTPException(422, str(exc) if isinstance(exc, FirmwarePackageError) else "Package could not be read.") from None
    if not package["baseline_found"]:
        raise HTTPException(422, "ISO is readable but no HPE baseline XML was found. Select an SPP ISO; filename alone is not enough.")
    record_audit_event(session, actor=actor, event_type="kit.firmware_package_selected",
                       message="Selected inspected ISO metadata; no hardware changes or upgrade approval.",
                       data={"profile_id": profile_id, "package": package})
    session.commit()
    return package


@router.get("/{profile_id}/firmware-assessment")
def firmware_assessment(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    kit_profile(profile_id)
    plan = get_plan(profile_id, session)
    item = next((item for item in plan.equipment if item.device_id == device_id and item.kind == "server"), None)
    device = session.get(DeviceInventory, device_id)
    if item is None or device is None or not is_ilo_device_type(device.device_type):
        raise HTTPException(404, "Server is not part of this kit.")
    health_review = read_health_review(session, profile_id, device_id)
    unknown = {"status": "Cannot determine", "rows": [], "apply_enabled": False, "health_review": health_review}
    row = session.scalar(select(AuditEvent).where(
        AuditEvent.event_type == "kit.firmware_package_selected",
        AuditEvent.data_json["profile_id"].as_string() == profile_id,
    ).order_by(AuditEvent.created_at.desc()).limit(1))
    if not row:
        return {**unknown, "reason": "Select an SPP above to compare installed firmware."}
    access = read_ilo_access_settings(session, device_id)
    probe, checked_at = get_probe_result("ilo-redfish", scope=device_id)
    if not (access["last_probe_is_current"] and access["last_probe_target_matches_access_host"]
            and access["last_probe_status"] == "ok" and probe and probe.get("status") == "ok"
            and probe.get("source_type") not in {"mock", "test_fixture"}
            and probe.get("mode") != "mock"):
        return {**unknown, "reason": "Run a successful connection check for this server. Existing readings are missing, stale, or belong to different connection settings."}
    try:
        result = assess(load_catalog(row.data_json["package"]), {**probe, "checked_at": checked_at}, item.model)
    except FirmwarePackageError as exc:
        return {**unknown, "reason": str(exc)}
    return {**result, "package_file": row.data_json["package"]["file_name"], "health_review": health_review}


def kit_profile(profile_id: str):
    state = list_lab_profiles()
    for profile in [*state["profiles"], state["runtime_profile"]]:
        if profile["id"] == profile_id:
            return profile
    raise HTTPException(404, "Kit not found")


@router.patch("/{profile_id}/name")
def name_kit(profile_id: str, payload: KitName, actor: str = Depends(get_current_actor)):
    # Validate names with the same secret-value rules as ordinary profiles.
    try:
        LabProfileWrite(name=payload.name)
    except ValidationError:
        raise HTTPException(422, "Kit name is invalid; do not include secrets.") from None
    try:
        return rename_kit(profile_id, payload.name)
    except LabProfileNotFoundError:
        raise HTTPException(404, "Save the runtime kit as a named kit first") from None


@router.post("/{profile_id}/save-as", status_code=201)
def copy_kit(profile_id: str, payload: KitName, session: Session = Depends(get_session),
             actor: str = Depends(get_current_actor)):
    source = kit_profile(profile_id)
    row = session.get(RackLayoutPlan, profile_id)
    layout = RackPlan(**row.layout_json) if row else RackPlan()
    # Reuse only shared network design, never targets, credentials or evidence.
    fields = {key: deepcopy(source.get(key)) for key in
              ("subnet_cidr", "gateway", "dns", "ntp", "vlan_id", "mtu", "features", "global_settings")
              if source.get(key) is not None}
    try:
        profile_data = LabProfileWrite(name=payload.name, profile_topology="custom", **fields)
    except ValidationError:
        raise HTTPException(422, "Kit name or shared network settings are invalid; do not include secrets.") from None
    copied = create_lab_profile(profile_data.model_dump(), activate=False)
    try:
        for item in layout.equipment:
            item.id = str(uuid4())
            item.device_id = None
            if item.kind == "server":
                family = re.search(r"\b(DL360|DL380)\b", item.model, re.I)
                if family:
                    item.model = "HPE " + family.group(1).upper()
        save_plan(layout, copied["id"], session, actor)
    except Exception:
        session.rollback()
        discard_unfinished_kit(copied["id"])
        raise
    return copied


@router.get("/{profile_id}/reports")
def kit_reports(profile_id: str, session: Session = Depends(get_session)):
    kit_profile(profile_id)
    rows = session.scalars(select(AuditEvent).where(
        AuditEvent.event_type == "kit.report_saved",
        AuditEvent.data_json["profile_id"].as_string() == profile_id,
    ).order_by(AuditEvent.created_at.desc()))
    return [{"id": row.id, **row.data_json["report"]} for row in rows]


@router.post("/{profile_id}/reports", status_code=201)
def save_kit_report(profile_id: str, session: Session = Depends(get_session),
                    actor: str = Depends(get_current_actor)):
    profile = kit_profile(profile_id)
    plan = get_plan(profile_id, session)
    devices = []
    device_ids = [item.device_id for item in plan.equipment if item.device_id]
    for item in plan.equipment:
        device = session.get(DeviceInventory, item.device_id) if item.device_id else None
        entry = {"name": item.name, "device_id": item.device_id, "model": item.model,
                 "position": item.position, "host": device.host if device else None,
                 "connection": "Not checked", "checked_at": None, "versions": []}
        if device and is_ilo_device_type(device.device_type):
            access = read_ilo_access_settings(session, device.id)
            entry["host"] = access["host"]
            entry["checked_at"] = access["last_probe_time"]
            current = access["last_probe_is_current"] and access["last_probe_target_matches_access_host"]
            entry["connection"] = access["last_probe_status"] if current else "Not verified / recheck needed"
            probe, _ = get_probe_result("ilo-redfish", scope=device.id)
            if current and access["last_probe_status"] == "ok" and probe:
                for group in ("managers", "systems", "firmware"):
                    for resource in probe.get(group) or []:
                        if not isinstance(resource, dict):
                            continue
                        version = next((resource[key] for key in
                                        ("Version", "FirmwareVersion", "BiosVersion", "BIOSVersion")
                                        if isinstance(resource.get(key), str)), None)
                        if version:
                            entry["versions"].append({"component": str(resource.get("Name") or group), "version": version})
        devices.append(entry)
        if device and is_ilo_device_type(device.device_type) and item.kind == "server":
            entry["firmware_assessment"] = firmware_assessment(profile_id, device.id, session)
    events = session.scalars(select(AuditEvent).where(
        AuditEvent.event_type != "kit.report_saved",
        or_(AuditEvent.data_json["profile_id"].as_string() == profile_id,
            AuditEvent.data_json["device_id"].as_string().in_(device_ids)),
    ).order_by(AuditEvent.created_at.asc()))
    # Whitelist metadata: never export arbitrary action payloads, logs or credentials.
    activity = [{"id": event.id, "at": event.created_at.isoformat(), "action": event.event_type,
                 "from_status": event.from_status, "to_status": event.to_status} for event in events]
    firmware_source = firmware_package_source(profile_id, "", session)
    report = {"name": profile["name"], "profile_id": profile_id,
              "captured_at": datetime.now(UTC).isoformat(), "rack_revision": plan.revision,
              "equipment": devices, "activity": activity,
              "firmware_package": firmware_source["selected"],
              "firmware_package_current": firmware_source["selection_current"],
              "limitations": "Snapshot, not build completion proof. Only activity explicitly linked to this kit or its equipment is included. Firmware readings do not prove an upgrade occurred. Unlinked legacy runs, before/after upgrade evidence and Windows verification are not yet included."}
    event = record_audit_event(session, actor=actor, event_type="kit.report_saved",
                               message="Saved a kit report snapshot; no hardware contact.",
                               data={"profile_id": profile_id, "report": report})
    session.commit()
    return {"id": event.id, **report}


@router.get("/{profile_id}", response_model=RackPlan)
def get_plan(profile_id: str = Path(min_length=1, max_length=120), session: Session = Depends(get_session)):
    row = session.get(RackLayoutPlan, profile_id)
    return RackPlan(**row.layout_json, revision=row.revision) if row else RackPlan()


@router.put("/{profile_id}", response_model=RackPlan)
def save_plan(payload: RackPlan, profile_id: str = Path(min_length=1, max_length=120),
              session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    # Validate newly saved model plans without making legacy layouts unreadable.
    for item in payload.equipment:
        family = re.search(r"\b(DL360|DL380)\b", item.model, re.IGNORECASE) if item.kind == "server" else None
        if family:
            name = family.group(1).upper()
            height, max_bays = (1, 10) if name == "DL360" else (2, 24)
            if item.height != height or item.bay_count > max_bays:
                raise HTTPException(422, f"{name} requires {height}U and supports up to {max_bays} front drive bays.")
    layout = payload.model_dump(exclude={"revision"})
    for item in payload.equipment:
        if item.device_id and session.get(DeviceInventory, item.device_id) is None:
            raise HTTPException(409, "Linked equipment no longer exists. Reload the rack.")
    try:
        if payload.revision == 0:
            session.add(RackLayoutPlan(profile_id=profile_id, revision=1, layout_json=layout))
            session.flush()
        else:
            result = session.execute(update(RackLayoutPlan).where(
                RackLayoutPlan.profile_id == profile_id,
                RackLayoutPlan.revision == payload.revision,
            ).values(revision=payload.revision + 1, layout_json=layout))
            if result.rowcount != 1:
                raise HTTPException(409, "Rack plan changed elsewhere. Reload before saving.")
        # Hardware metadata and layout are saved in one transaction. Existing
        # device identities and credentials are never replaced by a rack edit.
        for item in layout["equipment"]:
            if not item.get("device_id"):
                device = DeviceInventory(
                    device_type={"server": "ilo", "switch": "cisco_switch", "storage": "netapp"}.get(item["kind"], item["kind"]),
                    display_name=item["name"],
                    notes="Added from the rack workspace. Hardware has not been verified.",
                )
                session.add(device)
                session.flush()
                item["device_id"] = device.id
        session.execute(update(RackLayoutPlan).where(RackLayoutPlan.profile_id == profile_id).values(layout_json=layout))
        record_audit_event(session, actor=actor, event_type="rack_plan.saved",
                           message="Saved planned rack layout; no hardware changes.",
                           data={"profile_id": profile_id, "revision": payload.revision + 1})
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "Rack plan changed elsewhere. Reload before saving.") from None
    return RackPlan(**layout, revision=payload.revision + 1)
