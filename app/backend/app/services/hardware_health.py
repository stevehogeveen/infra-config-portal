"""Explain current hardware evidence; acknowledging an alert never clears it."""
import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select

from app.models import AuditEvent
from app.providers.probe_cache import get_probe_result
from app.services.hardware_values import health
from app.services.ilo_access_settings import read_ilo_access_settings


DRIVE_REASONS = {
    "CommunicationFailure": "The controller cannot communicate with this drive.",
    "Failed": "The controller reports that this drive has failed.",
    "PredictiveFail": "The controller predicts a drive failure.",
    "Rebuilding": "A RAID rebuild is running on this drive.",
    "CarrierCommunicationFailure": "Communication with the drive carrier has failed.",
    "NotSupported": "The controller does not support this drive.",
    "SizeNotValid": "The drive capacity is not suitable for its current array.",
    "Unrecoverable": "The controller reports an unrecoverable drive condition.",
    "EraseInProgress": "A drive erase is in progress.",
    "QueuedForErase": "The drive is queued for erasure.",
    "EraseFailed": "A drive erase failed.",
    "EraseCompleted": "The controller reports that the drive erase completed. This status alone does not establish current drive health or readiness for a new array.",
    "NonAuthenticDrive": "The controller could not validate the drive as an authentic HPE drive.",
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def reported_reasons(resource):
    values = resource.get("DiskDriveStatusReasons") or resource.get("LogicalDriveStatusReasons") or []
    return sorted({v for v in values if isinstance(v, str) and v not in {"None", "Unknown"}}) if isinstance(values, list) else []


def drive_condition(resource):
    """Separate occupancy/identification warnings from known-drive failures."""
    reported = health(resource)
    absent = (resource.get("Status") or {}).get("State") == "Absent"
    unidentified = (not resource.get("Model") and not resource.get("SerialNumber")
                    and not resource.get("serial_number_present") and not resource.get("CapacityBytes"))
    if absent or unidentified:
        return {"health": "Warning", "reported_health": reported,
                "presence": "absent" if absent else "unidentified",
                "label": "Empty bay" if absent else "Missing or unidentified",
                "explanation": "iLO reports this bay as empty." if absent else
                "No drive identity or capacity was returned. This can be an empty bay or an old RAID/spare record; it is not a confirmed physical-drive failure. Confirm the bay in HPE SSA."}
    return {"health": reported, "reported_health": reported, "presence": "identified", "label": reported, "explanation": None}


def health_issues(probe):
    storage = probe.get("storage") or {}
    power = probe.get("power") or []
    supplies = [d for p in power if isinstance(p, dict) for d in (p.get("PowerSupplies") or []) if isinstance(d, dict)]
    redundancy = [d for p in power if isinstance(p, dict) for d in (p.get("Redundancy") or []) if isinstance(d, dict)]
    input_present = any(isinstance(d.get("LineInputVoltage"), (int, float)) and d["LineInputVoltage"] > 0 for d in supplies)
    groups = [("Drive", storage.get("physical_drives") or []),
              ("Controller", [r for r in storage.get("controllers") or [] if r.get("Model")]),
              ("Logical volume", storage.get("logical_drives") or []),
              ("Power supply", supplies), ("Power redundancy", redundancy),
              ("Server", probe.get("systems") or []), ("Chassis", probe.get("chassis") or [])]
    issues = []
    for group, resources in groups:
        for resource in resources:
            severity = health(resource)
            condition = drive_condition(resource) if group == "Drive" else None
            if condition:
                severity = condition["health"]
            no_input = (group == "Power supply" and resource.get("PowerSupplyType") == "AC"
                        and resource.get("LineInputVoltage") == 0 and input_present
                        and (resource.get("Status") or {}).get("State") != "Absent")
            absent_supply = group == "Power supply" and (resource.get("Status") or {}).get("State") == "Absent"
            if (no_input or absent_supply) and severity != "Critical":
                severity = "Warning"
            reasons = reported_reasons(resource)
            actionable = [r for r in reasons if r in DRIVE_REASONS and r != "EraseCompleted"]
            if severity in {"OK", "Unknown"} and not actionable:
                continue
            location = str(resource.get("Location") or resource.get("Bay") or resource.get("Id") or "Not reported")
            model = resource.get("Model") or "Not identified"
            if group == "Chassis":
                aggregate = next((i for i in issues if i["group"] == "Server" and i["health"] == severity and i["facts"].get("Model") == model), None)
                if aggregate:
                    aggregate["facts"]["Chassis health"] = severity
                    aggregate["details"].append("The chassis reports the same health state. Overall health can reflect component alerts; this is not a separate diagnosed fault.")
                    continue
            title = f"Drive at {location}" if group == "Drive" else f"{group}: {model if model != 'Not identified' else location}"
            details = [DRIVE_REASONS.get(r, f"Controller status code: {r}.") for r in reasons]
            diagnostic_facts = {}
            if group == "Power supply":
                title = f"Power supply {location}: " + ("no input power" if no_input else "not installed" if absent_supply else severity.lower())
                diagnostic_facts["Reported supply health"] = health(resource)
                if "LineInputVoltage" in resource:
                    diagnostic_facts["Input voltage"] = str(resource["LineInputVoltage"]) + " V"
                if no_input:
                    details.append("This installed supply reports 0 V input while another supply has input power. Check its power cable and PDU/outlet. This does not by itself prove the supply has failed.")
                elif absent_supply:
                    details.append("iLO reports this power-supply bay as empty, not a failed installed supply.")
            if group == "Power redundancy":
                title = "Power redundancy unavailable" if (resource.get("Status") or {}).get("State") == "Disabled" else "Power redundancy warning"
                details.append("iLO reports a power-redundancy problem. A single working power feed may keep the server running, but a second independent feed is not currently confirmed.")
                diagnostic_facts["Mode"] = resource.get("Mode", "Not reported")
                diagnostic_facts["Supplies required"] = resource.get("MinNumNeeded", "Not reported")
            if group == "Controller":
                for label, status in (("Cache module", resource.get("CacheModuleStatus")),
                                      ("Controller board", (resource.get("ControllerBoard") or {}).get("Status"))):
                    if isinstance(status, dict):
                        value = status.get("Health") or status.get("HealthRollup") or "Not reported"
                        diagnostic_facts[label + " health"] = value
                        if value not in {"OK", "Unknown", "Not reported"}:
                            details.append(f"{label} reports {value}. This identifies an affected component, but not the underlying cause.")
                    else:
                        diagnostic_facts[label + " health"] = "Not reported in this reading"
                backup = resource.get("BackupPowerSourceStatus")
                if backup == "Present":
                    diagnostic_facts["Backup power charge"] = "Unknown (presence only)"
                elif backup in {"PresentAndCharging", "NotPresent"}:
                    details.append("Cache backup power is charging; this does not by itself prove a battery failure." if backup == "PresentAndCharging" else "The controller reports no cache backup power source. Verify the battery/capacitor connection and status.")
            if condition and condition["explanation"]:
                title = f"{condition['label']} at {location}"
                details = [condition["explanation"]]
                if reasons:
                    details.append(f"Controller record: {', '.join(reasons)}. Original iLO health: {condition['reported_health']}. The warning does not clear this record or make the bay usable for RAID.")
            if not details:
                details = [f"Cause not established. The saved inventory reports {severity.lower()}, but contains no specific fault explanation for this component."]
                if group == "Controller":
                    details.append("An overall controller warning does not establish that a drive or battery has failed. Cache, controller-board and IML details are needed to narrow it down.")
            if group in {"Server", "Chassis"}:
                component_alerts = [i["title"] for i in issues if i["group"] not in {"Server", "Chassis"}]
                if component_alerts:
                    details.append("Component alerts in this reading: " + "; ".join(component_alerts) + ". These may contribute to the overall warning; that link is not confirmed.")
            if group == "Drive" and condition["presence"] == "identified" and not resource.get("CapacityBytes"):
                details.append("No model or capacity was returned for this failed record. Confirm its bay and spare/data assignment in HPE SSA before removing or replacing anything." if "Failed" in reasons else "The drive model or capacity was not returned. This reading alone cannot distinguish a missing drive from a failed drive or an inventory problem.")
            if group == "Drive":
                next_step = "Identify this bay in iLO Storage and HPE SSA; check the drive status and Integrated Management Log before replacement, RAID changes or firmware installation."
            else:
                next_step = "Review this component in iLO and the Integrated Management Log. Use HPE diagnostics to identify the cause before approving changes."
            if group == "Controller":
                next_step = "Run a new hardware check to collect cache, controller-board and IML details. In iLO, open Information > Integrated Management Log; in HPE SSA, select this controller and review its status messages. Do not wipe RAID or replace a battery based on the summary warning alone."
            if group in {"Power supply", "Power redundancy"}:
                next_step = "Check the indicated supply, its cable, and PDU/outlet feed, then refresh hardware health. Maintain stable power during firmware updates and disk erasure."
            if "Rebuilding" in reasons:
                next_step = "Wait for the rebuild to finish and reread storage health before making further storage or firmware changes."
            if group == "Drive" and reasons == ["EraseCompleted"]:
                next_step = "Check the recorded erasure report, then refresh drive and controller health. If the warning remains, inspect the post-erase drive state in HPE SSA. Do not repeat the wipe or replace the drive based on EraseCompleted alone."
            state = (resource.get("Status") or {}).get("State")
            facts = {"Model": model, "Location": location}
            facts.update(diagnostic_facts)
            if condition:
                facts["Original iLO health"] = condition["reported_health"]
            for key in ("DiskDriveUse", "BackupPowerSourceStatus", "CapacityBytes"):
                if key in resource:
                    facts[key] = resource[key]
            if state:
                facts["State"] = state
            issue = {"title": title, "group": group, "health": severity, "location": location,
                     "details": details, "next_step": next_step, "facts": facts, "reasons": reasons}
            issue["id"] = digest({**issue, "resource": resource.get("@odata.id"),
                                  "identity": resource.get("identity_fingerprint_sha256")})
            issues.append(issue)
    return issues


def read_health_review(session, profile_id, device_id):
    access = read_ilo_access_settings(session, device_id)
    probe, checked_at = get_probe_result("ilo-redfish", scope=device_id)
    usable = bool(probe and probe.get("status") == "ok" and access["last_probe_target_matches_access_host"]
                  and probe.get("mode") != "mock" and probe.get("source_type") not in {"mock", "test_fixture"})
    current = False
    if usable and access["last_probe_is_current"]:
        try:
            age = (datetime.now(UTC) - datetime.fromisoformat(checked_at)).total_seconds()
            current = -30 <= age <= 900
        except (TypeError, ValueError):
            pass
    issues = health_issues(probe) if usable else []
    token = digest({"profile": profile_id, "device": device_id, "target": probe.get("target_fingerprint") if usable else None,
                    "checked_at": checked_at, "issues": issues})
    rows = session.scalars(select(AuditEvent).where(
        AuditEvent.event_type == "kit.health_issue_acknowledged",
        AuditEvent.data_json["profile_id"].as_string() == profile_id,
        AuditEvent.data_json["device_id"].as_string() == device_id,
        AuditEvent.data_json["review_token"].as_string() == token,
    ).order_by(AuditEvent.created_at.desc()))
    acknowledgements = {}
    for row in rows:
        acknowledgements.setdefault(row.data_json.get("issue_id"), row.created_at.isoformat())
    for issue in issues:
        issue["acknowledged_at"] = acknowledgements.get(issue["id"])
    return {"current": current, "checked_at": checked_at if usable else None, "review_token": token,
            "diagnostic_log": probe.get("diagnostic_log", {"entries": [], "message": "IML was not collected with this saved reading. Run a new hardware check to read available diagnostic entries.", "complete": False}) if usable else None,
            "issues": issues, "unacknowledged": sum(not i["acknowledged_at"] for i in issues),
            "message": "Acknowledgement records review only. Alerts remain unresolved until new hardware evidence clears them.",
            "refresh_required": None if current else "Run Check firmware against SPP or Refresh drive inventory for a current health review (within 15 minutes)."}
