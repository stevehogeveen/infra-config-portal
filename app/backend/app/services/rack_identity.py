"""Resolve planned server generations from a successful device-scoped iLO check."""
import re
from copy import deepcopy

from sqlalchemy import select, update

from app.models import RackLayoutPlan
from app.services.audit import record_audit_event
from app.services.ilo_access_settings import read_ilo_access_settings


def save_detected_generation(session, device_id, probe):
    if probe.get("status") != "ok" or probe.get("mode") == "mock" or probe.get("source_type") in {"mock", "test_fixture"}:
        return
    access = read_ilo_access_settings(session, device_id)
    if not (access["last_probe_is_current"] and access["last_probe_target_matches_access_host"]):
        return
    systems = probe.get("systems") or []
    if len(systems) != 1 or not isinstance(systems[0], dict):
        return
    match = re.fullmatch(r"(?:HPE?\s+)?(?:ProLiant\s+)?(DL360|DL380)\s+Gen(\d+)(\s+Plus)?(?:\s+Server)?", str(systems[0].get("Model", "")), re.I)
    if not match:
        return
    family = match.group(1).upper()
    model = f"HPE {family} Gen{match.group(2)}" + (" Plus" if match.group(3) else "")
    for row in session.scalars(select(RackLayoutPlan)):
        layout = deepcopy(row.layout_json)
        changes = []
        for item in layout.get("equipment", []):
            if item.get("device_id") != device_id or item.get("kind") != "server":
                continue
            planned_family = re.search(r"\b(DL360|DL380)\b", item.get("model", ""), re.I)
            if not planned_family or planned_family.group(1).upper() != family:
                continue
            if item["model"] != model:
                changes.append({"previous_model": item["model"], "detected_model": model})
                item["model"] = model
        if not changes:
            continue
        result = session.execute(update(RackLayoutPlan).where(
            RackLayoutPlan.profile_id == row.profile_id, RackLayoutPlan.revision == row.revision
        ).values(layout_json=layout, revision=row.revision + 1))
        if result.rowcount == 1:
            record_audit_event(session, actor="ilo-discovery", event_type="rack_plan.identity_detected",
                               message="Resolved server generation from read-only iLO identity.",
                               data={"profile_id": row.profile_id, "device_id": device_id,
                                     "checked_at": probe.get("checked_at"), "changes": changes})
    session.commit()
