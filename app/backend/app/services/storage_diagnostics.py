"""Read-only storage diagnosis: separate current facts from log evidence."""
import re
from datetime import UTC, datetime

import httpx

from app.providers.hpe_storage_rebuild import client_for
from app.providers.ilo_redfish import _base_url


def read_diagnostic_log(snapshot):
    system = re.split(r"/smartstorageconfig/", snapshot["path"], flags=re.I)[0]
    path = system + "/LogServices/IML/Entries/"
    entries = []
    try:
        with client_for(snapshot["config"]) as client:
            response = client.get(_base_url(snapshot["config"].host) + path)
            response.raise_for_status()
            data = response.json()
            members = data.get("Members")
            if not isinstance(members, list):
                raise ValueError("No entries collection")
            refs = 0
            for member in members[:200]:
                if not isinstance(member, dict):
                    continue
                event = member
                if "Message" not in event:
                    ref = event.get("@odata.id", "")
                    if refs >= 16 or not isinstance(ref, str) or not ref.lower().startswith(path.lower()) or ".." in ref:
                        continue
                    refs += 1
                    response = client.get(_base_url(snapshot["config"].host) + ref)
                    response.raise_for_status()
                    event = response.json()
                hpe = (event.get("Oem") or {}).get("Hpe") or {}
                entries.append({"id": str(event.get("Id", "")), "message": str(event.get("Message", ""))[:2048],
                    "severity": event.get("Severity", "Unknown"), "created": event.get("Created"),
                    "updated": hpe.get("Updated"), "repaired": hpe.get("Repaired")})
            complete = not data.get("Members@odata.nextLink") and len(entries) == len(members) and data.get("Members@odata.count", len(members)) == len(entries)
            return {"entries": entries, "complete": complete,
                    "message": "Log entries are historical evidence, not proof that a fault is active." if complete else
                    "Partial log read (up to 200 embedded entries and 16 linked entries). Other events may be missing."}
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        return {"entries": entries, "complete": False, "message": "The complete hardware log could not be read. Check iLO log permissions or inspect the IML in iLO."}


def diagnose_storage(snapshot, log):
    storage = snapshot["probe"].get("storage") or {}
    controllers = [c for c in storage.get("controllers") or [] if c.get("Model")]
    controller = controllers[0] if controllers else {}
    health = (controller.get("Status") or {}).get("Health", "Unknown")
    drives = storage.get("physical_drives") or []
    identified = [d for d in drives if d.get("Model") and (d.get("CapacityBytes") or d.get("CapacityGB"))]
    present = {d.get("Location") for d in identified}
    volumes = snapshot["current"].get("LogicalDrives") or []
    missing = sorted({bay for v in volumes for bay in v.get("DataDrives", []) if bay not in present})
    messages = [str(m.get("MessageId", "")) for m in snapshot["current"].get("@Redfish.Settings", {}).get("Messages", [])]
    errors = [m for m in messages if not m.endswith(".Success")]
    events = sorted(log["entries"], key=lambda e: e.get("updated") or e.get("created") or "", reverse=True)
    cache = next((e for e in events if "1795" in e["message"] or "obsolete data" in e["message"].lower()), None)
    findings = []
    systems = snapshot["probe"].get("systems") or []
    battery = systems[0].get("smart_storage_battery_health") if len(systems) == 1 else None
    if battery in {"Warning", "Critical"}:
        findings.append({"id": "storage-battery", "title": "Smart Storage battery needs attention",
            "source": "Current iLO system health", "detail": "iLO reports battery health: " + battery + ".",
            "evidence": ["HPE AggregateHealthStatus.SmartStorageBattery"],
            "action": "Investigate the battery and power connections before rebuilding. Removing arrays does not repair battery faults."})
    if errors:
        findings.append({"id": "controller-response", "title": "The controller did not approve the RAID operation",
            "source": "Current controller response", "detail": "The controller reports that its status is not OK and cannot create an editable configuration." if any("CanCreateEditableConfigControllerStatusNotOK" in e for e in errors) else "The controller returned non-success configuration messages. Review their exact codes below.",
            "evidence": errors, "action": "Resolve the controller warnings in HPE SSA before attempting another RAID change."})
    if missing:
        findings.append({"id": "missing-members", "title": "The old RAID references an unavailable member",
            "source": "Current RAID membership", "detail": "At least one configured member was not identified in the current physical-drive inventory. This is not proof that an installed drive is defective.",
            "evidence": missing, "action": "In HPE SSA, inspect the old array and its spare assignments. Do not substitute a drive or assume the spare is already a normal mirror member."})
    if cache:
        findings.append({"id": "cache", "title": "Cached data may belong to the previous array",
            "source": "Historical IML evidence", "detail": "An IML event reports obsolete or mismatched cached data. Confirm the current cache condition in SSA; a log entry alone cannot prove this is still active.",
            "evidence": [cache["message"], "Event time: " + str(cache.get("updated") or cache.get("created") or "Not reported"), "Marked repaired: " + str(cache.get("repaired"))],
            "action": "SSA must confirm whether obsolete cache data needs to be discarded. Discarding it is destructive; this app does not perform that action."})
    if health != "OK" and not errors:
        findings.append({"id": "controller-health", "title": "Controller health needs investigation", "source": "Current controller health",
            "detail": "Reported health: " + health + ". This summary does not identify a failed battery or drive.", "evidence": [],
            "action": "Inspect this controller's detailed status in HPE SSA."})
    known_failed = [d.get("Location", "Unknown") for d in identified if (d.get("Status") or {}).get("Health") in {"Critical", "Failed"}]
    if known_failed:
        findings.append({"id": "physical-health", "title": "Identified drives report critical health", "source": "Current physical-drive inventory",
            "detail": "Do not use these drives in a new array until diagnosed.", "evidence": known_failed, "action": "Inspect these exact drive bays and SSA diagnostics; RAID deletion cannot repair a physical failure."})
    outstanding = health != "OK" or bool(errors or missing or known_failed) or snapshot["pending_differs"] or battery in {"Warning", "Critical"}
    return {"checked_at": datetime.now(UTC).isoformat(), "status": "needs_attention" if outstanding else "no_current_storage_blocker",
        "summary": "Storage recovery needs attention before the build can continue." if outstanding else
        "No current storage blocker was found in the collected fields. This is not approval to erase or reconfigure disks.",
        "controller": controller.get("Model", "Not reported"), "controller_health": health,
        "backup_power": controller.get("BackupPowerSourceStatus", "Not reported"),
        "battery_health": (battery + " (reported by iLO system health)") if battery else "Not determined from backup-power presence",
        "detected_drives": len(identified), "healthy_drives": sum((d.get("Status") or {}).get("Health") == "OK" for d in identified),
        "volume_count": len(volumes), "pending_changes": snapshot["pending_differs"], "findings": findings,
        "volumes": [{"raid": v.get("Raid"), "members": v.get("DataDrives", []), "spares": v.get("SpareDrives", [])} for v in volumes],
        "log_complete": log["complete"], "log_note": log["message"], "repair_available": False,
        "recovery_steps": [
            "Open iLO and launch the remote console. Review the Integrated Management Log and confirm the target server.",
            "Open HPE Smart Storage Administrator (SSA) in an available maintenance environment. If it requires booting maintenance media or restarting, plan that separately; this diagnosis does neither.",
            "Select the reported Smart Array controller. Inspect cache status, array members, active spares and any failed-drive records.",
            "If SSA confirms obsolete cached data and the old data is not needed, review its destructive discard option. Stop if SSA reports a physical fault or an unexpected warning. Do not clear the IML to hide a fault.",
            "For a clean rebuild, separately confirm removal of the old logical volumes in SSA. Leave the controller empty; do not create replacement arrays yet.",
            "Return here and choose Verify recovery. The app rereads the controller and RAID; it does not trust a checkbox or clear an alert manually.",
        ]}
