"""Firmware part by part through the iLO, in an order that is safe for HPE Gen10 servers.

Which parts: every FWPKG-v2 package in the selected SPP whose manifest Target matches an item in
the iLO's firmware inventory and is newer than what is installed (HPE's own matching rule).

How each installs (from the package manifest):
* "ilo"  - UpdatableBy Bmc with DirectFlashOk: the iLO flashes it straight away.
* "bios" - UpdatableBy Uefi: staged in the iLO Repository and queued; the BIOS applies it at the
           next start. An out-of-date BIOS must never do this (it can crash on newer images), so
           the System ROM is always updated, restarted into and read back first.
Anything else (drives, OS-agent packages) needs HPE's SPP boot disc and is listed, not installed.

Run: one GuardedOperation (resource "parts-update") holds the server. Phases are advanced one
bounded step per request. A send is claimed once; a send without a recorded reply is
"needs attention" and is never repeated. Waits read the iLO only.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AuditEvent, GuardedOperation, utcnow
from app.services.audit import record_audit_event

RESOURCE = "parts-update"
ACTION_INSTALL = "ilo.component-update"
ACTION_RESTART = "ilo-redfish.firmware-restart"
REVIEW_TTL = timedelta(minutes=30)
ILO_TIMEOUT = timedelta(minutes=60)
START_TIMEOUT = timedelta(minutes=120)
SEND_REPLY_LIMIT = timedelta(minutes=20)
MIN_ILO_WAIT = timedelta(seconds=60)
QUIET_ILO_WAIT = timedelta(minutes=5)  # longer than the 15-minute upload timeout
SHARED_BOARD_TARGET = "00000000-0000-0000-0000-000000000204"
VERSION = re.compile(r"\d+(?:\.\d+)+")


class PartsUpdateError(RuntimeError):
    pass


# ---------------------------------------------------------------- package manifests

_MANIFESTS: dict[tuple, list[dict[str, Any]]] = {}


def _iso(package: dict):
    from app.services.firmware_packages import media_path

    return media_path(package["path"])


def _open_iso(path):
    import pycdlib

    iso = pycdlib.PyCdlib()
    iso.open(str(path))
    facade = iso.get_rock_ridge_facade() if iso.has_rock_ridge() else iso.get_joliet_facade()
    return iso, facade


def _name(iso, child) -> str:
    if iso.has_rock_ridge() and getattr(child, "rock_ridge", None):
        return child.rock_ridge.name().decode()
    return child.file_identifier().decode().split(";")[0]


def manifests(package: dict) -> list[dict[str, Any]]:
    """Every FWPKG-v2 device entry in the SPP's /packages, read straight from the ISO."""
    path = _iso(package)
    stat = path.stat()
    key = (str(path), stat.st_size, stat.st_mtime_ns)
    if key in _MANIFESTS:
        return _MANIFESTS[key]
    iso, facade = _open_iso(path)
    entries = []
    try:
        for child in facade.list_children("/packages"):
            name = _name(iso, child)
            if not name.lower().endswith(".fwpkg"):
                continue
            try:
                with facade.open_file_from_iso("/packages/" + name) as handle:
                    payload = json.loads(zipfile.ZipFile(handle).read("payload.json"))
            except (KeyError, ValueError, zipfile.BadZipFile):
                continue
            if payload.get("PackageFormat") != "FWPKG-v2":
                continue
            by = payload.get("UpdatableBy") or []
            for device in (payload.get("Devices") or {}).get("Device") or []:
                images = device.get("FirmwareImages") or [{}]
                direct = any(bool(img.get("DirectFlashOk")) for img in images)
                uefi = any(bool(img.get("UefiFlashable", img.get("UEFIFlashable"))) for img in images)
                method = "ilo" if "Bmc" in by and direct else "bios" if "Uefi" in by and "RuntimeAgent" not in by and uefi else "disc"
                entries.append({
                    "file": name,
                    "device": str(device.get("DeviceName") or "").strip().rstrip("."),
                    "version": str(device.get("Version") or ""),
                    "target": str(device.get("Target") or "").lower(),
                    "method": method,
                    "reset": any(bool(img.get("ResetRequired")) for img in images),
                    "minutes": max(1, int(((payload.get("package") or {}).get("installation") or {}).get("per_device_install_time_seconds") or 300) // 60),
                })
    finally:
        iso.close()
    _MANIFESTS.clear()
    _MANIFESTS[key] = entries
    return entries


def package_bytes(package: dict, filename: str) -> bytes:
    iso, facade = _open_iso(_iso(package))
    try:
        with facade.open_file_from_iso("/packages/" + filename) as handle:
            return handle.read()
    finally:
        iso.close()


# ---------------------------------------------------------------- matching

def numbers(value: Any) -> tuple[int, ...] | None:
    match = VERSION.search(str(value or ""))
    return tuple(int(x) for x in match.group(0).split(".")) if match else None


def newer(candidate: Any, installed: Any) -> bool | None:
    a, b = numbers(candidate), numbers(installed)
    if a is None or b is None:
        return None
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) > b + (0,) * (width - len(b))


def at_least(installed: Any, target: Any) -> bool:
    a, b = numbers(installed), numbers(target)
    if a is None or b is None:
        return False
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)) >= b + (0,) * (width - len(b))


def _is_rom(entry: dict) -> bool:
    device = entry["device"].lower()
    return entry["target"] == SHARED_BOARD_TARGET and (
        "bios" in device or "system rom" in device or bool(re.match(r"^[A-Z]\d{2}_\d", entry["file"]))
    )


def _match_item(entry: dict, inventory: list[dict]) -> dict | None:
    holders = [item for item in inventory if entry["target"] in [t.lower() for t in item["targets"]]]
    if len(holders) <= 1:
        return holders[0] if holders else None
    if entry["target"] == SHARED_BOARD_TARGET:
        # The system board ID is on several items; the BIOS package belongs to "System ROM".
        if _is_rom(entry):
            return next((i for i in holders if i["name"].lower() == "system rom"), None)
        return None
    # A device-specific target shared by identical devices (e.g. drives): not handled here.
    return None


def inventory(config) -> list[dict[str, Any]]:
    from app.services import esxi_boot_workflow as boot

    get = lambda path: boot._body(boot._get_redfish_resource(path, config=config))  # noqa: E731
    items = []
    for member in (get("/redfish/v1/UpdateService/FirmwareInventory/").get("Members") or [])[:128]:
        body = get(member["@odata.id"])
        hpe = (body.get("Oem") or {}).get("Hpe") or {}
        items.append({
            "name": str(body.get("Name") or ""),
            "version": str(body.get("Version") or ""),
            "targets": [str(t) for t in hpe.get("Targets") or []],
            "where": str(hpe.get("DeviceContext") or ""),
            "updateable": body.get("Updateable") is not False,
        })
    return items


def compare(entries: list[dict], items: list[dict]) -> dict[str, list[dict]]:
    """Parts to install (best package per item) and parts this way cannot install."""
    best: dict[str, dict] = {}
    rom_matched = False
    for entry in entries:
        item = _match_item(entry, items)
        if item and item["name"].lower() == "system rom":
            rom_matched = True
        if not item or newer(entry["version"], item["version"]) is not True:
            continue
        key = item["name"] + "|" + item["where"]
        if key not in best or newer(entry["version"], best[key]["to"]):
            best[key] = {
                "id": hashlib.sha256(key.encode()).hexdigest()[:12],
                "component": item["name"] if not item["where"] or item["where"] == "System Board" else f"{item['name']} ({item['where']})",
                "item": item["name"],
                "where": item["where"],
                "from": item["version"],
                "to": entry["version"],
                "file": entry["file"],
                "method": entry["method"],
                "reset": entry["reset"],
                "minutes": entry["minutes"],
                "rom": _is_rom(entry),
            }
    parts = sorted(best.values(), key=lambda p: (not p["rom"], p["method"] != "ilo", p["component"]))
    return {
        "install": [p for p in parts if p["method"] in {"ilo", "bios"} and p["item"] != "iLO 5"],
        "elsewhere": [p for p in parts if p["method"] == "disc" or p["item"] == "iLO 5"],
        # The SPP has a System ROM package for this server (so "not newer" means current).
        "rom_matched": rom_matched,
    }


def phases_for(parts: list[dict]) -> list[dict[str, Any]]:
    """iLO-flashed parts (System ROM first), restart and read back; then BIOS-applied parts."""
    phases: list[dict[str, Any]] = []
    rom = [p for p in parts if p["method"] == "ilo" and p["rom"]]
    direct = [p for p in parts if p["method"] == "ilo" and not p["rom"]]
    bios = [p for p in parts if p["method"] == "bios"]
    for part in rom:
        phases += [{"kind": "flash", "part": part["id"]}, {"kind": "wait-ilo", "part": part["id"]},
                   {"kind": "restart"}, {"kind": "wait-start", "queue": False}, {"kind": "check", "parts": [part["id"]]}]
    for part in direct:
        phases += [{"kind": "flash", "part": part["id"]}, {"kind": "wait-ilo", "part": part["id"]}]
    if direct:
        if any(p["reset"] for p in direct):
            phases += [{"kind": "restart"}, {"kind": "wait-start", "queue": False}]
        phases.append({"kind": "check", "parts": [p["id"] for p in direct]})
    for part in bios:
        phases += [{"kind": "stage", "part": part["id"]}, {"kind": "wait-ilo", "part": part["id"]}, {"kind": "queue", "part": part["id"]}]
    if bios:
        phases += [{"kind": "restart"}, {"kind": "wait-start", "queue": True}, {"kind": "check", "parts": [p["id"] for p in bios]}]
    return phases


# ---------------------------------------------------------------- records

def _record(session: Session, actor: str, event_type: str, message: str, data: dict) -> AuditEvent:
    event = record_audit_event(session, actor=actor, event_type=event_type, message=message, data=data)
    session.commit()
    return event


def _latest(session: Session, event_type: str, **match: str) -> AuditEvent | None:
    query = select(AuditEvent).where(AuditEvent.event_type == event_type)
    for key, value in match.items():
        query = query.where(AuditEvent.data_json[key].as_string() == value)
    return session.scalar(query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(1))


def _events(session: Session, event_type: str, run_id: str) -> list[AuditEvent]:
    return list(session.scalars(
        select(AuditEvent)
        .where(AuditEvent.event_type == event_type, AuditEvent.data_json["run_id"].as_string() == run_id)
        .order_by(AuditEvent.created_at, AuditEvent.id)
    ))


def _now() -> datetime:
    return datetime.now(UTC)


def _stamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


# ---------------------------------------------------------------- context

def _config(session, device_id):
    from app.services.ilo_access_settings import ilo_config_for_device

    config = ilo_config_for_device(session, device_id)
    if not config.configured or config.fallback_hosts:
        raise PartsUpdateError("An exact saved iLO connection is required for this server.")
    return config


def _package(session, profile_id):
    from app.services.firmware_flow import _latest as latest_flow
    from app.services.firmware_packages import package_unchanged

    row = latest_flow(session, "kit.firmware_package_selected", profile_id)
    if not row or not package_unchanged(row.data_json["package"]):
        raise PartsUpdateError("Choose the SPP ISO on the Check firmware page first.")
    if not str(row.data_json["package"].get("path", "")).lower().endswith(".iso"):
        raise PartsUpdateError("Part-by-part updates read packages from an SPP ISO.")
    return row.data_json["package"]


def _identity(config) -> dict[str, Any]:
    from app.providers.ilo_redfish import ilo_target_fingerprint
    from app.services.esxi_install import _read_server

    server = _read_server(config)
    return {
        "hardware_identity": server["hardware_identity"],
        "endpoint_identity": ilo_target_fingerprint(config.host),
        "power": server["power"],
        "post": server["post"],
    }


def _post_stamp(config) -> str | None:
    from app.services import esxi_boot_workflow as boot

    system = boot._body(boot._get_redfish_resource(boot.SYSTEM_PATH, config=config))
    return ((system.get("Oem") or {}).get("Hpe") or {}).get("PostDiscoveryCompleteTimeStamp")


def _policy_blockers() -> list[str]:
    from app.providers.action_policy import ActionCategory, current_lab_action_policy

    policy = current_lab_action_policy()
    return [
        *policy.action_blockers(ACTION_INSTALL, ActionCategory.FIRMWARE_UPDATE),
        *policy.action_blockers(ACTION_RESTART, ActionCategory.POWER_ACTION),
    ]


# ---------------------------------------------------------------- review

def review(session: Session, profile_id: str, device_id: str, actor: str) -> dict[str, Any]:
    """Read the server and the SPP; nothing is sent. The plan is valid for 30 minutes."""
    package = _package(session, profile_id)
    config = _config(session, device_id)
    identity = _identity(config)
    items = inventory(config)
    found = compare(manifests(package), items)
    parts = found["install"]
    blockers = []
    rom_planned = any(p["rom"] for p in parts)
    if any(p["method"] == "bios" for p in parts) and not rom_planned and not found["rom_matched"]:
        # Without a confirmed current BIOS, BIOS-applied images can crash an old one.
        parts = [p for p in parts if p["method"] != "bios"]
        blockers.append("The SPP has no System ROM package matching this server, so parts the BIOS installs are not offered.")
    from app.providers import hpe_ilo_components as ilo

    try:
        if ilo.update_service(config)["busy"]:
            blockers.append("The iLO is busy with another update. Wait for it to finish, then review again.")
        waiting = [t for t in ilo.task_queue(config) if t["state"].lower() in {"pending", "inprogress", "running"}]
        if waiting:
            blockers.append("The iLO has queued updates waiting for a restart: " + ", ".join(t["filename"] or t["name"] for t in waiting) + ". Clear them first.")
    except Exception:
        blockers.append("The iLO update service could not be read.")
    phases = phases_for(parts)
    restarts = sum(1 for phase in phases if phase["kind"] == "restart")
    digest = hashlib.sha256(json.dumps({
        "parts": parts, "phases": phases, "hardware": identity["hardware_identity"],
        "endpoint": identity["endpoint_identity"], "package": package["path"],
    }, sort_keys=True).encode()).hexdigest()
    plan = {
        "review_id": secrets.token_hex(16),
        "digest": digest,
        "profile_id": profile_id,
        "device_id": device_id,
        "package": package.get("file_name") or package["path"],
        "parts": parts,
        "elsewhere": [{"component": p["component"], "from": p["from"], "to": p["to"],
                       "reason": "Installed afterwards by HPE's boot disc, if the SPP still lists it."}
                      for p in found["elsewhere"]],
        "phases": phases,
        "restarts": restarts,
        "minutes": sum(p["minutes"] for p in parts) + restarts * 10,
        "power": identity["power"],
        # Real blockers only. Permission is switched to "firmware only" by the installer when the
        # operator presses Update, and start() checks it again then.
        "blockers": blockers,
        "permission": _policy_blockers(),
        "expires_at": (_now() + REVIEW_TTL).isoformat(),
    }
    _record(session, actor, "kit.parts_update.review", "Part-by-part firmware review; nothing sent.",
            {k: plan[k] for k in ("review_id", "digest", "profile_id", "device_id", "expires_at")})
    return plan


# ---------------------------------------------------------------- run

def _run(session, device_id) -> AuditEvent | None:
    return _latest(session, "kit.parts_update.run", device_id=device_id)


def _operation(session, run_id) -> GuardedOperation | None:
    return session.get(GuardedOperation, run_id, populate_existing=True)


def start(session: Session, profile_id: str, device_id: str, actor: str, review_id: str) -> dict[str, Any]:
    from app.services.guarded_operation_ledger import OperationConflict, reserve

    reviewed = _latest(session, "kit.parts_update.review", review_id=review_id)
    if not reviewed or reviewed.data_json["device_id"] != device_id or reviewed.data_json["profile_id"] != profile_id:
        raise PartsUpdateError("Review the update again.")
    if _stamp(reviewed.data_json["expires_at"]) <= _now():
        raise PartsUpdateError("The review expired. Review the update again.")
    current = status(session, profile_id, device_id)
    if current["active"]:
        raise PartsUpdateError("A firmware update is already running on this server.")
    fresh = review(session, profile_id, device_id, actor)
    if fresh["digest"] != reviewed.data_json["digest"]:
        raise PartsUpdateError("The server or the SPP changed since the review. Check the new review and start again.")
    if fresh["blockers"] or fresh["permission"]:
        raise PartsUpdateError((fresh["blockers"] + fresh["permission"])[0])
    if not fresh["parts"]:
        raise PartsUpdateError("Nothing to install: every part this way can update is current.")
    config = _config(session, device_id)
    identity = _identity(config)
    try:
        operation = reserve(
            session, profile_id=profile_id, device_id=device_id, resource=RESOURCE,
            idempotency_key=secrets.token_hex(16), actor=actor,
            reviewed_intent={"digest": fresh["digest"], "review_id": review_id},
        )
    except OperationConflict as exc:
        raise PartsUpdateError(str(exc)) from None
    _record(session, actor, "kit.parts_update.run", "Part-by-part firmware update approved.", {
        "run_id": operation.id, "profile_id": profile_id, "device_id": device_id,
        "package": _package(session, profile_id), "parts": fresh["parts"], "phases": fresh["phases"],
        "hardware_identity": identity["hardware_identity"], "endpoint_identity": identity["endpoint_identity"],
    })
    return advance(session, profile_id, device_id, actor)


def _results(session, run_id) -> dict[int, dict]:
    return {e.data_json["index"]: e.data_json for e in _events(session, "kit.parts_update.result", run_id)}


def _result(session, actor, run_id, index, outcome, message, **extra):
    status_value = f"pu-{outcome}-{index}"
    session.execute(
        update(GuardedOperation)
        .where(GuardedOperation.id == run_id, GuardedOperation.active_device.is_not(None))
        .values(status=status_value, updated_at=utcnow())
    )
    _record(session, actor, "kit.parts_update.result", message,
            {"run_id": run_id, "index": index, "outcome": outcome, "message": message, **extra})


def _claim(session, actor, run_id, index) -> None:
    expected = "accepted" if index == 0 else f"pu-ok-{index - 1}"
    claim = session.execute(
        update(GuardedOperation)
        .where(GuardedOperation.id == run_id, GuardedOperation.status == expected, GuardedOperation.active_device.is_not(None))
        .values(status=f"pu-sent-{index}", updated_at=utcnow())
    )
    if claim.rowcount != 1:
        session.rollback()
        raise PartsUpdateError("This step is already claimed. Nothing was sent again.")
    _record(session, actor, "kit.parts_update.attempt", "Firmware step starting; outcome unverified.",
            {"run_id": run_id, "index": index, "at": _now().isoformat()})


def _finish(session, actor, run_id, outcome, message):
    session.execute(
        update(GuardedOperation).where(GuardedOperation.id == run_id)
        .values(status="verified" if outcome == "verified" else outcome, active_device=None, updated_at=utcnow())
    )
    _record(session, actor, "kit.parts_update.done", message, {"run_id": run_id, "outcome": outcome})


def _assert_target(run, config):
    identity = _identity(config)
    if identity["hardware_identity"] != run["hardware_identity"] or identity["endpoint_identity"] != run["endpoint_identity"]:
        raise PartsUpdateError("The iLO now answers for a different server. Nothing was sent.")
    return identity


def advance(session: Session, profile_id: str, device_id: str, actor: str) -> dict[str, Any]:
    """Do at most one bounded step of the open run, then return its status."""
    from app.providers import hpe_ilo_components as ilo
    from app.services import esxi_boot_workflow as boot
    from app.services.runtime_write_scope import dispatch_lease

    current = status(session, profile_id, device_id)
    if not current["active"] or current["state"] == "needs_attention":
        return current
    run = _run(session, device_id).data_json
    run_id = run["run_id"]
    phases, parts = run["phases"], {p["id"]: p for p in run["parts"]}
    done = _results(session, run_id)
    index = next((i for i in range(len(phases)) if i not in done), None)
    if index is None:
        _finish(session, actor, run_id, "verified", "Every listed part was read back at its new version.")
        return status(session, profile_id, device_id)
    phase = phases[index]
    part = parts.get(phase.get("part", ""))
    config = _config(session, device_id)
    attempts = {e.data_json["index"]: e.data_json for e in _events(session, "kit.parts_update.attempt", run_id)}
    if index in attempts:
        # A send is in flight (another request is uploading) or its reply was lost.
        if _now() - _stamp(attempts[index]["at"]) > SEND_REPLY_LIMIT:
            _result(session, actor, run_id, index, "uncertain", "A step was sent but no reply was recorded; its outcome is unknown and it was not sent again.")
        return status(session, profile_id, device_id)

    def send(action, function):
        _assert_target(run, config)
        blockers = _policy_blockers()
        if blockers:
            raise PartsUpdateError(blockers[0])
        _claim(session, actor, run_id, index)
        try:
            with dispatch_lease(action):
                return function()
        except ilo.ComponentError as exc:
            _result(session, actor, run_id, index, "uncertain" if exc.sent else "failed", str(exc))
            return None
        except Exception as exc:  # noqa: BLE001 - the outcome of an interrupted send is unknown
            _result(session, actor, run_id, index, "uncertain", f"The step was interrupted ({type(exc).__name__}); its outcome is unknown.")
            return None

    try:
        kind = phase["kind"]
        if kind in {"flash", "stage"}:
            if kind == "stage" and any(
                r["filename"] == part["file"] and not r["locked"] and numbers(r["version"]) == numbers(part["to"])
                for r in ilo.repository(config)
            ):
                _result(session, actor, run_id, index, "ok", f"{part['file']} is already in the iLO Repository.", skipped=True)
            else:
                data = package_bytes(run["package"], part["file"])
                sent = send(ACTION_INSTALL, lambda: ilo.upload_package(config, filename=part["file"], data=data, flash_now=kind == "flash") or True)
                if sent:
                    _result(session, actor, run_id, index, "ok", f"The iLO accepted {part['file']}.")
        elif kind == "wait-ilo":
            previous = done.get(index - 1, {})
            if previous.get("skipped"):
                _result(session, actor, run_id, index, "ok", "Nothing was uploaded, so there was nothing to wait for.")
            else:
                service = ilo.update_service(config)
                started = _stamp(attempts.get(index - 1, {}).get("at", _now().isoformat()))
                waited = _now() - started
                if service["busy"] and not _latest(session, "kit.parts_update.busy", run_id=run_id, index=str(index)):
                    _record(session, actor, "kit.parts_update.busy", "The iLO is working on the package.", {"run_id": run_id, "index": str(index)})
                seen_busy = bool(_latest(session, "kit.parts_update.busy", run_id=run_id, index=str(index)))
                # Right after an upload the iLO can still show the previous "Complete": finish only
                # once it has been seen working, or after 5 minutes, and never within 60 seconds.
                settled = waited >= MIN_ILO_WAIT and (seen_busy or waited >= QUIET_ILO_WAIT)
                if service["state"] in {"ERROR", "REJECTED"} and waited >= MIN_ILO_WAIT:
                    _result(session, actor, run_id, index, "failed", f"The iLO reported an error installing {part['component']} ({service['result'] or service['state']}).")
                elif service["state"] in {"COMPLETE", "COMPLETED", "IDLE"} and settled:
                    _result(session, actor, run_id, index, "ok", f"The iLO finished with {part['file']}.")
                elif _now() - started > ILO_TIMEOUT:
                    _result(session, actor, run_id, index, "uncertain", f"The iLO is still busy with {part['file']} after an hour.")
        elif kind == "queue":
            if send(ACTION_INSTALL, lambda: ilo.queue_bios_update(config, filename=part["file"])):
                _result(session, actor, run_id, index, "ok", f"{part['component']} is queued for the next start.")
        elif kind == "restart":
            if ilo.update_service(config)["busy"]:
                return status(session, profile_id, device_id)  # never restart while the iLO is flashing
            identity = _assert_target(run, config)
            stamp = _post_stamp(config)
            reset = "On" if identity["power"] == "Off" else "ForceRestart"
            response = send(ACTION_RESTART, lambda: boot._post_system_reset(reset, config=config))
            if response is not None:
                if response.get("status_code") in {200, 202, 204}:
                    _result(session, actor, run_id, index, "ok", "The server is restarting.", post_before=stamp, reset=reset)
                else:
                    _result(session, actor, run_id, index, "failed", f"The iLO refused the restart (HTTP {response.get('status_code')}).")
        elif kind == "wait-start":
            restart = done.get(index - 1, {})
            identity = _identity(config)
            stamp = _post_stamp(config)
            restarted = bool(stamp) and (not restart.get("post_before") or _stamp(stamp) > _stamp(restart["post_before"]))
            tasks = ilo.task_queue(config) if phase.get("queue") else []
            ours = {parts[p["part"]]["file"] for p in phases if p["kind"] == "queue"}
            failed = [t for t in tasks if t["filename"] in ours and t["state"].lower() == "exception"]
            open_tasks = [t for t in tasks if t["filename"] in ours and t["state"].lower() in {"pending", "inprogress", "running"}]
            began = _stamp(attempts.get(index - 1, {}).get("at", _now().isoformat()))
            if failed:
                _result(session, actor, run_id, index, "failed", "The BIOS reported a failure applying " + ", ".join(t["filename"] for t in failed) + ".")
            elif restarted and identity["post"] == "FinishedPost" and not open_tasks and all(
                t["state"].lower() in {"complete", "completed"} for t in tasks if t["filename"] in ours
            ):
                _result(session, actor, run_id, index, "ok", "The server restarted and finished starting.")
            elif _now() - began > START_TIMEOUT:
                _result(session, actor, run_id, index, "uncertain", "The server has not finished starting after two hours. Look at the iLO remote console.")
        elif kind == "check":
            items = inventory(config)
            short = []
            for pid in phase["parts"]:
                p = parts[pid]
                item = next((i for i in items if i["name"] == p["item"] and i["where"] == p["where"]), None)
                if not item or not at_least(item["version"], p["to"]):
                    short.append(f"{p['component']} (now {item['version'] if item else 'unknown'}, wanted {p['to']})")
            if short:
                _result(session, actor, run_id, index, "failed", "Not at the new version: " + "; ".join(short) + ". Nothing further was sent.")
            else:
                _result(session, actor, run_id, index, "ok", "Read back at the new version.", verified=phase["parts"])
    except PartsUpdateError:
        raise
    except Exception:  # noqa: BLE001 - reads fail while the iLO or host restarts; try again later
        pass
    return status(session, profile_id, device_id)


def close(session: Session, profile_id: str, device_id: str, actor: str) -> dict[str, Any]:
    """Release the server after a failure. Refused while a send has no recorded reply."""
    current = status(session, profile_id, device_id)
    if not current["active"]:
        return current
    if current["state"] != "needs_attention":
        raise PartsUpdateError("The update is still running. It can be closed once it stops.")
    _finish(session, actor, current["run_id"], "failed", "Closed by the operator after a stopped step.")
    return status(session, profile_id, device_id)


DESCRIBE = {
    "flash": "The iLO installs {component}",
    "wait-ilo": "Waiting for the iLO to finish {component}",
    "stage": "Copy {component} to the iLO",
    "queue": "Queue {component} for the next start",
    "restart": "Restart the server",
    "wait-start": "Waiting for the server to finish starting",
    "check": "Read the new versions back",
}


def status(session: Session, profile_id: str, device_id: str) -> dict[str, Any]:
    """Stored evidence only; never contacts the server."""
    row = _run(session, device_id)
    if not row or row.data_json.get("profile_id") != profile_id:
        return {"state": "not_started", "active": False, "phases": [], "parts": [], "message": "No part-by-part update has run on this server."}
    run = row.data_json
    operation = _operation(session, run["run_id"])
    results = _results(session, run["run_id"])
    attempts = {e.data_json["index"] for e in _events(session, "kit.parts_update.attempt", run["run_id"])}
    finished = _latest(session, "kit.parts_update.done", run_id=run["run_id"])
    parts = {p["id"]: p for p in run["parts"]}
    phases = []
    for i, phase in enumerate(run["phases"]):
        result = results.get(i)
        state = result["outcome"] if result else ("sent" if i in attempts else "todo")
        name = parts.get(phase.get("part", ""), {}).get("component", "")
        phases.append({"index": i, "kind": phase["kind"], "label": DESCRIBE[phase["kind"]].format(component=name),
                       "state": state, "message": result["message"] if result else None})
    verified = {pid for r in results.values() for pid in r.get("verified", [])}
    part_states = []
    for part in run["parts"]:
        mine = [p for p in phases if run["phases"][p["index"]].get("part") == part["id"]]
        bad = next((p for p in mine if p["state"] in {"failed", "uncertain"}), None)
        part_states.append({**{k: part[k] for k in ("id", "component", "from", "to", "method", "file")},
                            "state": "done" if part["id"] in verified else "failed" if bad else
                            "installed" if mine and all(p["state"] == "ok" for p in mine) else
                            "installing" if any(p["state"] in {"ok", "sent"} for p in mine) else "waiting"})
    problem = next((p for p in phases if p["state"] in {"failed", "uncertain"} or (p["state"] == "sent" and p["index"] not in results)), None)
    active = bool(operation and operation.active_device)
    if finished:
        state = "verified" if finished.data_json["outcome"] == "verified" else "failed"
        message = finished.message
    elif problem and problem["state"] == "sent":
        state, message = ("running", "Sending to the server…")
    elif problem:
        state, message = "needs_attention", problem["message"] or "A step needs attention."
    else:
        nxt = next((p for p in phases if p["state"] == "todo"), None)
        state, message = "running", (nxt["label"] + "…") if nxt else "Finishing…"
    return {
        "state": state, "active": active, "run_id": run["run_id"], "phases": phases, "parts": part_states,
        "message": message, "started_at": row.created_at.replace(tzinfo=UTC).isoformat(),
    }
