"""Physical-drive erase planning and conservative, attempt-bound verification."""
import os
import re
import math
from datetime import UTC, datetime
from sqlalchemy import select
from app.models import AuditEvent

from app.providers.action_policy import ActionCategory, current_lab_action_policy
from app.services.hardware_health import digest
from app.services.hardware_values import firmware_version
from app.services.hpe_raid import REPO_ROOT
from app.services.json_file_store import read_json_object

METHODS = ("SanitizeRestrictedOverwrite", "SanitizeRestrictedBlockErase", "OnePass")
MEDIA_METHODS = {"HDD": "SanitizeRestrictedOverwrite", "SSD": "SanitizeRestrictedBlockErase"}
CAPABILITIES = REPO_ROOT / ".local" / "sanitization-capabilities.json"
RAW_WORKFLOW_REFERENCE = "https://github.com/HewlettPackard/python-redfish-utility/blob/master/ilorest/extensions/SMART_ARRAY_COMMANDS/DriveSanitizeCommand.py"


def enrollment(session, device_id):
    if session is None:
        return {}
    event = session.scalar(select(AuditEvent).where(
        AuditEvent.event_type == "kit.raid_rebuild.sanitize_enrollment",
        AuditEvent.data_json["device_id"].as_string() == device_id
    ).order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()))
    if not event:
        return {}
    data = event.data_json
    try:
        if datetime.fromisoformat(data["expires_at"]) > datetime.now(UTC):
            return data
    except (KeyError, ValueError, TypeError):
        pass
    return {}


def policy_blockers(device_id, session=None):
    approved = enrollment(session, device_id)
    if approved:
        # In-app enrollment grants only this action on this device, not global write access.
        return current_lab_action_policy().action_blockers("ilo-redfish.disk-sanitize", ActionCategory.APP_STATE_WRITE)
    result = current_lab_action_policy().action_blockers("ilo-redfish.disk-sanitize", ActionCategory.STORAGE_CONFIG)
    enrolled = {v.strip() for v in os.getenv("HPE_SANITIZE_DEVICE_IDS", "").split(",") if v.strip()}
    if device_id not in enrolled:
        result.append("Physical-disk erasure is not enabled for this server. Complete Erase authorization below.")
    return result


def drive_rows(snapshot):
    rows = []
    for d in snapshot["probe"].get("storage", {}).get("physical_drives", []):
        rows.append({"path": d.get("@odata.id", ""), "bay": d.get("Location", "Unknown"),
                     "identity": d.get("hardware_identity_fingerprint_sha256", ""),
                     "model": d.get("Model", ""), "firmware": firmware_version(d),
                     "capacity_bytes": d.get("CapacityBytes", 0), "media": d.get("MediaType", "Unknown"),
                     "role": d.get("DiskDriveUse", "Unknown"), "health": (d.get("Status") or {}).get("Health", "Unknown"),
                     "pattern": d.get("ErasePattern"), "reasons": d.get("DiskDriveStatusReasons") or [],
                     "percent": d.get("EraseCompletionPercentage")})
    return sorted(rows, key=lambda d: (d["bay"], d["path"]))


def scope(rows):
    return [{k: r[k] for k in ("path", "bay", "identity", "model", "firmware", "capacity_bytes", "media")} for r in rows]


def raw_drive_preparation(snapshot, rows, controller):
    """SR mixed-mode Raw is an assignment state, not a request to convert modes.

    HPE's iLO 5 drivesanitize implementation checks physical membership and absence
    from logical drives. Restrict this path to observed Gen10 SR mixed mode; do
    not transfer MR/JBOD conversion rules or infer method support from that state.
    """
    if not any(r["role"] == "Raw" for r in rows):
        return None
    storage = snapshot["probe"].get("storage") or {}
    current = snapshot["current"]
    pending = snapshot["pending"]
    problems = []
    model = controller.get("Model") or ""
    mode = controller.get("CurrentOperatingMode")
    if not re.fullmatch(r"HPE Smart Array [A-Za-z0-9-]+ SR Gen10", model) or mode != "Mixed":
        problems.append("Raw-drive preparation requires an identified HPE SR Gen10 controller reporting Mixed mode. This controller/mode has not been validated for this path.")
    if not str(current.get("@odata.type", "")).startswith("#SmartStorageConfig.v2_"):
        problems.append("The supported SmartStorageConfig v2 interface was not confirmed.")
    if current.get("LogicalDrives") != [] or storage.get("logical_drives") != []:
        problems.append("Delete existing arrays and refresh inventory. Both controller configuration and drive inventory must confirm no logical volumes.")
    physical = current.get("PhysicalDrives")
    config_bays = [d.get("Location") for d in physical if isinstance(d, dict)] if isinstance(physical, list) else []
    expected = [r["bay"] for r in rows]
    if (not config_bays or not all(isinstance(b, str) and b for b in config_bays)
            or len(config_bays) != len(physical) or len(set(config_bays)) != len(config_bays)
            or sorted(config_bays) != sorted(expected)):
        problems.append("Physical-disk membership differs between controller configuration and inventory. Refresh disk readiness; no drive will be omitted or guessed.")

    def mixed_ports(value):
        if not isinstance(value, list) or not value:
            return None
        if any(not isinstance(p, dict) or type(p.get("PortIndex")) is not int
               or p.get("OperatingModeAfterReboot") != "Mixed" for p in value):
            return None
        indexes = sorted(p["PortIndex"] for p in value)
        return indexes if len(set(indexes)) == len(indexes) else None

    current_ports = mixed_ports(current.get("Ports"))
    pending_ports = mixed_ports(pending["Ports"]) if "Ports" in pending else current_ports
    if (current_ports is None or pending_ports != current_ports
            or controller.get("OperatingModeAfterReboot") not in {None, "Mixed"}):
        problems.append("Mixed-mode port settings are missing or changing. Resolve the controller settings before a Raw-drive wipe.")
    evidence = {"controller_model": model, "controller_mode": mode,
                "schema": current.get("@odata.type"),
                "configuration_bays": sorted(config_bays) if all(isinstance(b, str) for b in config_bays) else None,
                "configuration_empty": current.get("LogicalDrives") == [],
                "inventory_empty": storage.get("logical_drives") == [],
                "ports": current_ports, "pending_ports": pending_ports,
                "roles": [{"bay": r["bay"], "role": r["role"]} for r in rows]}
    return {"assignment_verified": not problems, "controller_mode": mode,
            "blockers": problems, "evidence": evidence, "reference": RAW_WORKFLOW_REFERENCE}


def plan(snapshot, method, device_id, session=None):
    rows = drive_rows(snapshot)
    controllers = [c for c in snapshot["probe"].get("storage", {}).get("controllers", []) if c.get("Model")]
    controller = controllers[0] if len(controllers) == 1 else {}
    blockers = policy_blockers(device_id, session)
    raw_preparation = raw_drive_preparation(snapshot, rows, controller)
    if raw_preparation:
        blockers.extend(raw_preparation["blockers"])
    if method not in (*METHODS, "auto"):
        raise ValueError("Unsupported erase method")
    if snapshot["power"] != "Off":
        blockers.append("Shut down the server before staging physical-disk erasure.")
    if snapshot["current"].get("LogicalDrives"):
        blockers.append("Delete the existing RAID arrays and verify the empty controller first. Erasure includes former data disks and hot spares; it does not silently delete arrays.")
    if snapshot["pending_differs"]:
        blockers.append("Resolve pending controller settings before erasure.")
    if not rows or len(rows) > 24 or len({d["bay"] for d in rows}) != len(rows) or len({d["identity"] for d in rows}) != len(rows):
        blockers.append("A complete, unique physical-drive inventory (1 to 24 drives) is required.")
    if snapshot["probe"].get("storage", {}).get("warnings"):
        blockers.append("Storage discovery is incomplete. No drive may be silently omitted from full-controller erasure.")
    if (controller.get("Status") or {}).get("Health") != "OK":
        blockers.append("The identified storage controller must report healthy.")
    approvals = read_json_object(CAPABILITIES).get("approvals", [])
    if not isinstance(approvals, list):
        approvals = []
    approved = enrollment(session, device_id)
    approvals = approved.get("approvals", []) + approvals
    if approved and approved.get("identity") != snapshot["identity"]:
        blockers.append("Server identity changed. Complete a new erase authorization for this hardware.")
    evidence = []
    prefix = str(controller.get("@odata.id", "")).rstrip("/") + "/"
    for row in rows:
        reasons = []
        selected = MEDIA_METHODS.get(row["media"]) if method == "auto" else method
        row["erase_pattern"] = selected
        if row["media"] not in MEDIA_METHODS:
            reasons.append("Drive media type is unknown or unsupported. Refresh inventory; no erase method will be guessed.")
        elif selected != MEDIA_METHODS[row["media"]] and not (row["media"] == "HDD" and selected == "OnePass"):
            reasons.append("Erase method does not match this drive: HDDs require overwrite; SSDs require block erase.")
        if (not row["identity"] or not row["model"] or not row["firmware"] or row["capacity_bytes"] <= 0
                or not row["path"].startswith(prefix) or not row["bay"] or row["bay"] == "Unknown"):
            reasons.append("Exact drive identity, firmware, capacity and controller membership are required.")
        if row["health"] != "OK":
            reasons.append("Drive health must be OK before starting erasure.")
        if any(r in row["reasons"] for r in ("EraseInProgress", "QueuedForErase")):
            reasons.append("An erase operation is already active on this drive. Do not resubmit.")
        if row["role"] == "Raw":
            if not raw_preparation["assignment_verified"]:
                reasons.append("Raw drive has not passed the mixed-mode preparation checks.")
        elif row["role"] != "Unconfigured":
            reasons.append("Drive must be unconfigured before erasure; it is still assigned or its use is unknown.")
        if method == "OnePass" and row["media"] != "HDD":
            reasons.append("Controller overwrite is limited to HDDs; it is not a flash sanitization method.")
        approved = None
        for entry in approvals:
            if not isinstance(entry, dict):
                continue
            try:
                expiry = datetime.fromisoformat(entry.get("expires_at", "").replace("Z", "+00:00"))
                valid = expiry.tzinfo is not None and expiry > datetime.now(UTC)
            except (ValueError, TypeError):
                valid = False
            if (valid and entry.get("server_identity") == snapshot["identity"]
                    and entry.get("controller_model") == controller.get("Model")
                    and entry.get("controller_firmware") == firmware_version(controller)
                    and entry.get("drive_identity") == row["identity"]
                    and entry.get("drive_model") == row["model"] and entry.get("drive_firmware") == row["firmware"]
                    and entry.get("method") == selected and entry.get("source") and entry.get("reviewed_by")):
                approved = entry
                break
        if approved is None:
            reasons.append("Method support has not been reviewed for this drive/controller firmware. Add supporting vendor evidence in Erase authorization below.")
        else:
            evidence.append(approved)
        row["method_approved"] = approved is not None
        row["blockers"] = reasons
        blockers.extend(f"Bay {row['bay']}: {reason}" for reason in reasons)
    assignments = {r["identity"]: r["erase_pattern"] for r in rows}
    payload = {"DataGuard": "Disabled", "LogicalDrives": [], "Actions": [
        {"Action": "PhysicalDriveErase", "ErasePattern": pattern,
         "PhysicalDriveList": [r["bay"] for r in rows if r["erase_pattern"] == pattern]}
        for pattern in METHODS if any(r["erase_pattern"] == pattern for r in rows)]}
    return {"drives": rows, "drive_scope": scope(rows), "erase_pattern": method, "payload": payload,
            "raw_preparation": raw_preparation,
            "preparation": {
                "raw_bays": [r["bay"] for r in rows if r["role"] == "Raw"],
                "assigned_bays": [r["bay"] for r in rows if r["role"] in {"Data", "Spare"}],
                "support_review_bays": [r["bay"] for r in rows if not r["method_approved"]],
            },
            "drive_methods": assignments,
            "capability_context": {"server_identity": snapshot["identity"], "controller_model": controller.get("Model"),
                                   "controller_firmware": firmware_version(controller)},
            "capability_digest": digest(evidence), "capability_evidence": evidence, "blockers": blockers,
            "scope_note": "All physical drives reported on this controller, including former spares. Other controllers, USB and NVMe boot devices are not included.",
            "assurance": "Controller overwrite; not a purge or compliance certificate." if method == "OnePass" else
                         "Device sanitize command; completion requires per-drive evidence. Not an independent compliance certificate."}


def rejected_method(snapshot, attempt, previous, boot_started_at):
    """Recognize a single rejected erase action, never a partial/uncertain erase."""
    rows = drive_rows(snapshot)
    storage = snapshot["probe"].get("storage", {})
    actions = attempt.get("payload", {}).get("Actions", [])
    controllers = [c for c in storage.get("controllers", []) if c.get("Model")]
    context = attempt.get("capability_context") or {}
    if (attempt.get("operation") != "sanitize" or len(actions) != 1
            or len(controllers) != 1 or controllers[0].get("Model") != context.get("controller_model")
            or firmware_version(controllers[0]) != context.get("controller_firmware")
            or actions[0].get("Action") != "PhysicalDriveErase"
            or actions[0].get("ErasePattern") not in METHODS
            or snapshot["identity"] != attempt.get("identity")
            or not rows or scope(rows) != attempt.get("drive_scope")
            or snapshot["pending_differs"] or snapshot["pending"].get("Actions")
            or snapshot["current"].get("Actions")
            or snapshot["current"].get("LogicalDrives") != []
            or storage.get("logical_drives") != [] or storage.get("warnings")
            or any(d.get("observed_active") for d in (previous or {}).get("drives", []))):
        return None
    method = actions[0]["ErasePattern"]
    if (sorted(actions[0].get("PhysicalDriveList", [])) != sorted(d["bay"] for d in rows)
            or any(d["health"] != "OK" or d["role"] not in {"Raw", "Unconfigured"}
                   or d["pattern"] is not None or d["percent"] is not None
                   or d["reasons"] != ["None"] for d in rows)):
        return None
    settings = snapshot["current"].get("@Redfish.Settings") or {}
    try:
        applied = datetime.fromisoformat(settings.get("Time", "").replace("Z", "+00:00"))
        boot = boot_started_at.replace(tzinfo=UTC) if boot_started_at and boot_started_at.tzinfo is None else boot_started_at
        if not boot or not applied.tzinfo or not boot < applied <= datetime.now(UTC):
            return None
    except (TypeError, ValueError):
        return None
    messages = settings.get("Messages") or []
    errors = [m for m in messages if not isinstance(m, dict) or not str(m.get("MessageId", "")).endswith(".Success")]
    if not errors or any(not isinstance(m, dict)
            or m.get("MessageId") != "SmartStorageMessages.2.0.1.PropertyValueEnumNotInList"
            or m.get("MessageArgs") != ["ErasePattern", method]
            or m.get("RelatedProperties") != ["#/Actions/0/ErasePattern"] for m in errors):
        return None
    return {"reason": "erase_method_rejected", "rejected_method": method,
            "settings_time": applied.isoformat(), "codes": [m["MessageId"] for m in errors],
            "drive_scope": attempt["drive_scope"], "capability_context": attempt.get("capability_context"),
            "message": f"The controller rejected {method}. All reviewed disks report idle, with no pending erase. No disk erasure was verified. Choose a different method and confirm a new attempt."}


def verify(snapshot, attempt, previous, boot_started_at):
    current = drive_rows(snapshot)
    prior = {d["identity"]: d for d in (previous or {}).get("drives", [])}
    baseline = {d["identity"]: d for d in attempt.get("drives", [])}
    by_id = {d["identity"]: d for d in current}
    same_target = snapshot["identity"] == attempt["identity"]
    same_scope = scope(current) == attempt["drive_scope"]
    settings = snapshot["current"].get("@Redfish.Settings") or {}
    try:
        applied = datetime.fromisoformat(settings.get("Time", "").replace("Z", "+00:00"))
        boot = boot_started_at.replace(tzinfo=UTC) if boot_started_at and boot_started_at.tzinfo is None else boot_started_at
        fresh = bool(boot and applied.tzinfo and boot < applied <= datetime.now(UTC))
    except (TypeError, ValueError):
        fresh = False
    messages = settings.get("Messages") or []
    accepted = fresh and bool(messages) and all(isinstance(m, dict) and str(m.get("MessageId", "")).endswith(".Success") for m in messages)
    errors = [str(m.get("MessageId", "Unknown controller response")) for m in messages
              if isinstance(m, dict) and not str(m.get("MessageId", "")).endswith(".Success")] if fresh else []
    results = []
    for expected in attempt["drive_scope"]:
        row = by_id.get(expected["identity"])
        method = (attempt["drive_methods"].get(expected["identity"]) if "drive_methods" in attempt
                  else attempt.get("erase_pattern"))
        seen = bool(prior.get(expected["identity"], {}).get("observed_active"))
        state = "unverified"
        percent = None
        if row and same_target and same_scope and boot_started_at:
            reasons = row["reasons"]
            pattern_matches = method in METHODS and row["pattern"] == method
            before = baseline.get(expected["identity"], {})
            actions = [a for a in attempt.get("payload", {}).get("Actions", [])
                       if expected["bay"] in a.get("PhysicalDriveList", [])]
            # Older iLO reports status reasons but omits ErasePattern. Bind that
            # transition to the exact accepted request, not just an idle array.
            accepted_method = (row["pattern"] is None and accepted and method in METHODS
                and str(snapshot["current"].get("@odata.type", "")).startswith("#SmartStorageConfig.v2_")
                and not snapshot["pending_differs"] and snapshot["current"].get("LogicalDrives") == []
                and before.get("pattern") is None and before.get("reasons") == ["None"]
                and len(actions) == 1 and actions[0].get("Action") == "PhysicalDriveErase"
                and actions[0].get("ErasePattern") == method)
            pattern_matches = pattern_matches or accepted_method
            if pattern_matches and any(r in reasons for r in ("EraseInProgress", "QueuedForErase")):
                seen = True
                state = "erasing" if "EraseInProgress" in reasons else "queued"
                percent = row["percent"] if type(row["percent"]) in (int, float) and math.isfinite(row["percent"]) and 0 <= row["percent"] <= 100 else None
            if any(r in reasons for r in ("EraseFailed", "EraseAborted", "Failed")):
                state = "failed"
            elif (seen and pattern_matches and accepted and not snapshot["pending_differs"]
                  and not snapshot["current"].get("LogicalDrives") and "EraseCompleted" in reasons):
                state, percent = "completed", 100
        if not same_target or not same_scope:
            note = "Hardware no longer matches the reviewed disks. Progress cannot be attributed to this wipe."
        elif not boot_started_at:
            note = "Power-on has not been recorded for this wipe."
        elif state == "completed":
            note = "Erase completion verified for this disk and method."
        elif state == "failed":
            note = "The drive reported an erase failure or abort. Do not retry automatically."
        elif state == "erasing":
            note = "Erasing; percentage reported by controller." if percent is not None else "Erasing; controller does not report a percentage."
        elif state == "queued":
            note = "Controller reports this disk is queued for erasure."
        elif row and "EraseCompleted" in row["reasons"]:
            note = "A completion flag was reported, but completion of this wipe has not been verified."
        elif errors:
            note = "Controller rejected an erase setting; this disk has no confirmed erase progress."
        else:
            note = "No erase activity confirmed for this disk and method."
        if row and row["pattern"] is None and state in {"erasing", "queued", "completed"}:
            note += " iLO omits the method; this reading is linked to the accepted wipe request."
        results.append({**expected, "erase_pattern": method, "status": state, "observed_active": seen, "percent": percent,
                        "progress_note": note,
                        "reported_pattern": row["pattern"] if row else None,
                        "reported_reasons": row["reasons"] if row else ["Drive missing or replaced"]})
    complete = bool(results) and all(d["status"] == "completed" for d in results)
    return {"status": "verified" if complete else "needs_attention" if errors or not same_scope or not same_target or any(d["status"] == "failed" for d in results) else "unverified",
            "verified": complete, "checked_at": datetime.now(UTC).isoformat(), "drives": results,
            "power": snapshot.get("power", "Unknown"), "pending_changes": snapshot["pending_differs"],
            "controller_errors": errors, "scope_matches": same_scope, "target_matches": same_target,
            "message": "All reviewed physical drives reported erase completion for this operation. Recreate arrays separately." if complete else
                       "The controller returned erase errors: " + ", ".join(errors) + ". Erasure is not verified; do not retry blindly." if errors else
                       "Erasure is not verified for every drive. Missing, replaced, failed or unreported drives are not erased proof. Do not rebuild arrays yet.",
            "assurance": attempt.get("assurance"), "scope_note": attempt.get("scope_note")}
