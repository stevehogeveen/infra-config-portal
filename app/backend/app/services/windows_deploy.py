"""Deploy a Windows OVA/OVF onto the verified standalone ESXi host and prove it is running.

Image: an .ova (or .ovf with its disks) in the app's media folder.
Target: the ESXi host this app installed and verified, signed in as root with the saved password.
Run (one GuardedOperation, resource "windows-deploy", holding the server):
  import   - govc imports the image as a powered-off, thin-provisioned VM on the chosen datastore,
             its networks mapped to the chosen port group. Long-running, in a worker thread.
  power    - power the new VM on (once).
  verify   - VMware Tools running and reporting a usable IPv4 address (DHCP).
A send is claimed once and never repeated; a send without a recorded reply needs attention.
"""

from __future__ import annotations

import ipaddress
import re
import secrets
import threading
import xml.etree.ElementTree as ElementTree
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AuditEvent, GuardedOperation, utcnow
from app.services.audit import record_audit_event

RESOURCE = "windows-deploy"
ACTION_IMPORT = "esxi.vm-deploy"
ACTION_POWER = "esxi.vm-power"
VM_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,62}$")
WINDOWS_NAME = re.compile(r"win|w2k|server[ _-]?20\d\d", re.I)
PHASES = ("import", "power", "verify")
TOOLS_TIMEOUT = timedelta(minutes=45)
IMPORT_REPLY_LIMIT = timedelta(hours=4, minutes=10)
HEARTBEAT_LIMIT = timedelta(minutes=3)
POWER_REPLY_LIMIT = timedelta(minutes=2)
# Each result may only follow the state it belongs to; a late or stale one changes nothing.
EXPECTED = {"import": ("wd-sent-import",), "power": ("wd-ok-import", "wd-sent-power"), "verify": ("wd-ok-power",)}
_workers: dict[str, threading.Thread] = {}


def _session_factory():
    from app.core.database import SessionLocal

    return SessionLocal


class WindowsDeployError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _stamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _record(session: Session, actor: str, event_type: str, message: str, data: dict) -> AuditEvent:
    event = record_audit_event(session, actor=actor, event_type=event_type, message=message, data=data)
    session.commit()
    return event


def _latest(session: Session, event_type: str, **match: str) -> AuditEvent | None:
    query = select(AuditEvent).where(AuditEvent.event_type == event_type)
    for key, value in match.items():
        query = query.where(AuditEvent.data_json[key].as_string() == value)
    return session.scalar(query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(1))


# ---------------------------------------------------------------- images

def _media_root() -> Path:
    from app.services.firmware_packages import media_root

    return media_root()


def _ovf_disks(path: Path) -> list[str]:
    """Files an .ovf references (its disks); they must sit beside it."""
    try:
        tree = ElementTree.parse(path)
    except (ElementTree.ParseError, OSError):
        return []
    return [element.attrib[key] for element in tree.iter() for key in element.attrib
            if element.tag.endswith("File") and key.endswith("href")]


def list_images() -> list[dict[str, Any]]:
    root = _media_root()
    if not root.is_dir():
        return []
    images = []
    candidates = [*root.glob("*.ova"), *root.glob("*/*.ova"), *root.glob("*.ovf"), *root.glob("*/*.ovf")]
    for path in sorted(candidates, key=lambda p: p.name.lower()):
        if path.name.startswith(".") or path.is_symlink() or not path.is_file():
            continue
        missing = [name for name in _ovf_disks(path) if not (path.parent / name).is_file()] if path.suffix.lower() == ".ovf" else []
        size = path.stat().st_size + sum((path.parent / n).stat().st_size for n in _ovf_disks(path) if (path.parent / n).is_file()) if path.suffix.lower() == ".ovf" else path.stat().st_size
        folder = path.parent.relative_to(root).as_posix()
        images.append({
            "path": path.relative_to(root).as_posix(),
            "name": path.name,
            "folder": "" if folder == "." else folder,
            "size_bytes": size,
            "kind": path.suffix.lower().lstrip("."),
            "missing": missing,
            "windows": bool(WINDOWS_NAME.search(path.name)),
        })
    return images


def _image(path: str) -> Path:
    from app.services.firmware_packages import FirmwarePackageError, media_path

    try:
        resolved = media_path(path)
    except FirmwarePackageError as exc:
        raise WindowsDeployError(str(exc)) from None
    if resolved.suffix.lower() not in {".ova", ".ovf"} or not resolved.is_file():
        raise WindowsDeployError("Choose an .ova or .ovf image from the media folder.")
    return resolved


# ---------------------------------------------------------------- ESXi host

def _host(session: Session, profile_id: str, device_id: str) -> dict[str, Any]:
    from app.services import esxi_install

    status = esxi_install.install_status(session, profile_id, device_id)
    if status.get("state") != "verified" or not status.get("management_ip"):
        raise WindowsDeployError("Install and verify ESXi on this server first (Prepare ESXi).")
    password = esxi_install._root_password(device_id)
    if not password:
        raise WindowsDeployError("The ESXi root password is not saved. Enter it again on Prepare ESXi.")
    return {"address": status["management_ip"], "password": password, "datastore": (status.get("datastore") or {}).get("name")}


def _read_host(host: dict[str, Any]) -> dict[str, Any]:
    from app.providers import esxi_govc as govc

    try:
        return {"datastores": govc.datastores(host["address"], host["password"]),
                "networks": govc.networks(host["address"], host["password"]), "problem": None}
    except govc.GovcError as exc:
        return {"datastores": [], "networks": [], "problem": f"ESXi at {host['address']} could not be read: {exc}"}


# ---------------------------------------------------------------- settings

def get_setup(session: Session, profile_id: str, device_id: str, read_host: bool = True) -> dict[str, Any]:
    """Saved settings and the image list; with read_host, ESXi is also asked for its datastores and networks."""
    saved = _latest(session, "kit.windows.settings", profile_id=profile_id, device_id=device_id)
    settings = dict(saved.data_json) if saved else {}
    try:
        host = _host(session, profile_id, device_id)
        found = _read_host(host) if read_host else {"datastores": [], "networks": [], "problem": None}
        target = {"address": host["address"], **found, "default_datastore": host["datastore"]}
    except WindowsDeployError as exc:
        target = {"address": None, "datastores": [], "networks": [], "problem": str(exc), "default_datastore": None}
    return {
        "images": list_images(),
        "image": settings.get("image"),
        "vm_name": settings.get("vm_name"),
        "datastore": settings.get("datastore"),
        "network": settings.get("network"),
        "saved_at": saved.created_at.replace(tzinfo=UTC).isoformat() if saved else None,
        "host": target,
    }


def save_settings(session: Session, profile_id: str, device_id: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    image = _image(str(payload.get("image") or ""))
    name = str(payload.get("vm_name") or "").strip()
    if not VM_NAME.fullmatch(name):
        raise WindowsDeployError("Name the VM with letters, digits and dashes (up to 63), starting with a letter or digit.")
    if image.suffix.lower() == ".ovf":
        missing = [n for n in _ovf_disks(image) if not (image.parent / n).is_file()]
        if missing:
            raise WindowsDeployError("This OVF export is incomplete. Put these files in the same folder as the .ovf: " + ", ".join(missing))
    host = _host(session, profile_id, device_id)
    found = _read_host(host)
    if found["problem"]:
        raise WindowsDeployError(found["problem"])
    datastore = str(payload.get("datastore") or "")
    network = str(payload.get("network") or "")
    if datastore not in {d["name"] for d in found["datastores"]}:
        raise WindowsDeployError("Choose a datastore this ESXi host has.")
    if network not in found["networks"]:
        raise WindowsDeployError("Choose a VM network this ESXi host has.")
    _record(session, actor, "kit.windows.settings", "Windows VM settings saved; nothing sent to ESXi.", {
        "profile_id": profile_id, "device_id": device_id, "image": image.relative_to(_media_root()).as_posix(),
        "vm_name": name, "datastore": datastore, "network": network,
    })
    return get_setup(session, profile_id, device_id)


# ---------------------------------------------------------------- review

def _policy_blockers() -> list[str]:
    from app.providers.action_policy import ActionCategory, current_lab_action_policy

    policy = current_lab_action_policy()
    return [*policy.action_blockers(ACTION_IMPORT, ActionCategory.VM_DEPLOY),
            *policy.action_blockers(ACTION_POWER, ActionCategory.VM_DEPLOY)]


def review(session: Session, profile_id: str, device_id: str) -> dict[str, Any]:
    """Read ESXi and the image; nothing is sent."""
    from app.providers import esxi_govc as govc

    saved = _latest(session, "kit.windows.settings", profile_id=profile_id, device_id=device_id)
    if not saved:
        return {"ready": False, "blockers": ["Choose the Windows image and save the VM settings."], "permission": []}
    settings = saved.data_json
    blockers: list[str] = []
    host = _host(session, profile_id, device_id)
    try:
        image = _image(settings["image"])
    except WindowsDeployError as exc:
        return {"ready": False, "blockers": [str(exc)], "permission": []}
    size = next((i["size_bytes"] for i in list_images() if i["path"] == settings["image"]), image.stat().st_size)
    found = _read_host(host)
    if found["problem"]:
        blockers.append(found["problem"])
    store = next((d for d in found["datastores"] if d["name"] == settings["datastore"]), None)
    if store is None and not found["problem"]:
        blockers.append(f"Datastore {settings['datastore']} is not on this ESXi host.")
    elif store and store["free"] < size + 10 * 1024**3:
        blockers.append(f"Datastore {settings['datastore']} has too little free space for this image.")
    if settings["network"] not in found["networks"] and not found["problem"]:
        blockers.append(f"VM network {settings['network']} is not on this ESXi host.")
    mappings: list[str] = []
    if not found["problem"]:
        try:
            if govc.vm_info(host["address"], host["password"], settings["vm_name"]) is not None:
                blockers.append(f"A VM named {settings['vm_name']} already exists on this host. Choose another name.")
            mappings = govc.ovf_networks(host["address"], host["password"], str(image))
        except govc.GovcError as exc:
            blockers.append(f"The image could not be read: {exc}")
    return {
        "ready": not blockers, "blockers": blockers, "permission": _policy_blockers(),
        "image": settings["image"], "size_bytes": size, "vm_name": settings["vm_name"],
        "datastore": settings["datastore"], "network": settings["network"], "mappings": mappings,
        "address": host["address"], "free_bytes": store["free"] if store else None,
    }


# ---------------------------------------------------------------- run

def _run(session, device_id) -> AuditEvent | None:
    return _latest(session, "kit.windows.run", device_id=device_id)


def _results(session, run_id) -> dict[str, dict]:
    rows = session.scalars(select(AuditEvent).where(
        AuditEvent.event_type == "kit.windows.result", AuditEvent.data_json["run_id"].as_string() == run_id
    ).order_by(AuditEvent.created_at, AuditEvent.id))
    return {r.data_json["phase"]: r.data_json for r in rows}


def _result(session, actor, run_id, phase, outcome, message, **extra) -> bool:
    moved = session.execute(update(GuardedOperation)
                            .where(GuardedOperation.id == run_id, GuardedOperation.active_device.is_not(None),
                                   GuardedOperation.status.in_(EXPECTED[phase]))
                            .values(status=f"wd-{outcome}-{phase}", updated_at=utcnow()))
    if moved.rowcount != 1:
        session.rollback()
        return False
    record_audit_event(session, actor=actor, event_type="kit.windows.result", message=message,
                       data={"run_id": run_id, "phase": phase, "outcome": outcome, "message": message, **extra})
    session.commit()
    return True


def _heartbeat(session, run_id) -> None:
    session.execute(update(GuardedOperation).where(GuardedOperation.id == run_id, GuardedOperation.status == "wd-sent-import")
                    .values(updated_at=utcnow()))
    session.commit()


def _claim(session, actor, run_id, phase, expected):
    claim = session.execute(update(GuardedOperation)
                            .where(GuardedOperation.id == run_id, GuardedOperation.status == expected, GuardedOperation.active_device.is_not(None))
                            .values(status=f"wd-sent-{phase}", updated_at=utcnow()))
    if claim.rowcount != 1:
        session.rollback()
        raise WindowsDeployError("This step is already claimed. Nothing was sent again.")
    _record(session, actor, "kit.windows.attempt", f"Windows deploy step '{phase}' starting; outcome unverified.",
            {"run_id": run_id, "phase": phase, "at": _now().isoformat()})


def _finish(session, actor, run_id, outcome, message, **extra):
    session.execute(update(GuardedOperation).where(GuardedOperation.id == run_id)
                    .values(status=outcome, active_device=None, updated_at=utcnow()))
    _record(session, actor, "kit.windows.done", message, {"run_id": run_id, "outcome": outcome, **extra})


def _import_worker(run: dict[str, Any], password: str, actor: str) -> None:
    from app.providers import esxi_govc as govc
    from app.services.runtime_write_scope import dispatch_lease

    with _session_factory()() as session:
        try:
            with dispatch_lease(ACTION_IMPORT):
                govc.import_vm(run["address"], password, path=str(_image(run["image"])), datastore=run["datastore"],
                               name=run["vm_name"], network=run["network"], mappings=run["mappings"],
                               heartbeat=lambda: _heartbeat(session, run["run_id"]))
        except govc.GovcError as exc:
            _result(session, actor, run["run_id"], "import", "failed", f"The import stopped: {exc}")
            return
        except Exception as exc:  # noqa: BLE001 - an interrupted import has an unknown outcome
            _result(session, actor, run["run_id"], "import", "uncertain", f"The import was interrupted ({type(exc).__name__}).")
            return
        _result(session, actor, run["run_id"], "import", "ok", f"{run['vm_name']} was imported onto {run['datastore']}.")


def start(session: Session, profile_id: str, device_id: str, actor: str) -> dict[str, Any]:
    from app.services.guarded_operation_ledger import OperationConflict, reserve

    if status(session, profile_id, device_id)["active"]:
        raise WindowsDeployError("A Windows deployment is already running on this server.")
    plan = review(session, profile_id, device_id)
    if plan["blockers"] or plan["permission"]:
        raise WindowsDeployError((plan["blockers"] + plan["permission"])[0])
    host = _host(session, profile_id, device_id)
    try:
        operation = reserve(session, profile_id=profile_id, device_id=device_id, resource=RESOURCE,
                            idempotency_key=secrets.token_hex(16), actor=actor,
                            reviewed_intent={k: plan[k] for k in ("image", "vm_name", "datastore", "network", "address")})
    except OperationConflict as exc:
        raise WindowsDeployError(str(exc)) from None
    run = {"run_id": operation.id, "profile_id": profile_id, "device_id": device_id,
           **{k: plan[k] for k in ("image", "size_bytes", "vm_name", "datastore", "network", "mappings", "address")}}
    _record(session, actor, "kit.windows.run", "Windows deployment approved.", run)
    _claim(session, actor, operation.id, "import", "accepted")
    worker = threading.Thread(target=_import_worker, args=(run, host["password"], actor), name=f"windows-import-{operation.id}", daemon=True)
    _workers[operation.id] = worker
    worker.start()
    return status(session, profile_id, device_id)


def advance(session: Session, profile_id: str, device_id: str, actor: str) -> dict[str, Any]:
    """One bounded step: watch the import, power on once, then wait for VMware Tools."""
    from app.providers import esxi_govc as govc
    from app.services.runtime_write_scope import dispatch_lease

    current = status(session, profile_id, device_id)
    if not current["active"] or current["state"] == "needs_attention":
        return current
    run = _run(session, device_id).data_json
    run_id = run["run_id"]
    results = _results(session, run_id)
    password = _host(session, profile_id, device_id)["password"]
    address_of_run = run["address"]  # bound at review: never follow a later host record
    operation = session.get(GuardedOperation, run_id, populate_existing=True)
    if "import" not in results:
        worker = _workers.get(run_id)
        beat = operation.updated_at.replace(tzinfo=UTC) if operation.updated_at.tzinfo is None else operation.updated_at
        if (worker is None or not worker.is_alive()) and _now() - beat > HEARTBEAT_LIMIT:
            # No live worker here and no heartbeat anywhere: the import's end was never recorded.
            _result(session, actor, run_id, "import", "uncertain", "The import's outcome was not recorded (the app restarted). It was not started again.")
        return status(session, profile_id, device_id)
    power_result = _latest(session, "kit.windows.result", run_id=run_id, phase="power")
    if power_result and power_result.data_json["outcome"] == "ok" and _now() - power_result.created_at.replace(tzinfo=UTC) > TOOLS_TIMEOUT:
        # The deadline holds even while ESXi cannot be read.
        _result(session, actor, run_id, "verify", "uncertain",
                "VMware Tools has not reported Windows and an address after 45 minutes. Open the VM console in the ESXi host client.")
        return status(session, profile_id, device_id)
    try:
        vm = govc.vm_info(address_of_run, password, run["vm_name"])
    except govc.GovcError:
        return current  # ESXi busy or restarting; read again later
    if "power" not in results:
        power_attempt = _latest(session, "kit.windows.attempt", run_id=run_id, phase="power")
        if vm is not None and vm["power"] == "poweredOn":
            _result(session, actor, run_id, "power", "ok", f"{run['vm_name']} is powered on.")
        elif power_attempt:
            # Power-on was sent but its reply was lost: decide by reading, never by sending again.
            if _now() - _stamp(power_attempt.data_json["at"]) > POWER_REPLY_LIMIT:
                _result(session, actor, run_id, "power", "uncertain", f"Power-on was sent but {run['vm_name']} is not on. It was not sent again.")
        elif vm is None:
            _result(session, actor, run_id, "power", "failed", f"ESXi does not show {run['vm_name']} after the import.")
        else:
            _claim(session, actor, run_id, "power", "wd-ok-import")
            try:
                with dispatch_lease(ACTION_POWER):
                    govc.power_on(address_of_run, password, run["vm_name"])
                _result(session, actor, run_id, "power", "ok", f"{run['vm_name']} was powered on.")
            except Exception as exc:  # noqa: BLE001
                _result(session, actor, run_id, "power", "uncertain", f"Powering on did not confirm ({type(exc).__name__}). It was not sent again.")
        return status(session, profile_id, device_id)
    address = _usable_address(vm)
    windows = "windows" in str((vm or {}).get("guest_os") or "").lower()
    if vm and vm["power"] == "poweredOn" and vm["tools"] == "guestToolsRunning" and address and windows:
        _result(session, actor, run_id, "verify", "ok", f"Windows is running at {address}.", address=address,
                hostname=vm.get("hostname"), guest_os=vm.get("guest_os"))
        _finish(session, actor, run_id, "verified", f"{run['vm_name']} is running Windows at {address}.", address=address,
                hostname=vm.get("hostname"), guest_os=vm.get("guest_os"))
    else:
        _record(session, actor, "kit.windows.observed", "Read-only VM check.", {
            "run_id": run_id, "checked_at": _now().isoformat(), "power": vm.get("power") if vm else None,
            "tools": vm.get("tools") if vm else None, "address": vm.get("ip") if vm else None,
            "guest_os": vm.get("guest_os") if vm else None})
    return status(session, profile_id, device_id)


def _usable_address(vm: dict[str, Any] | None) -> str | None:
    if not vm:
        return None
    for value in [vm.get("ip"), *vm.get("addresses", [])]:
        try:
            address = ipaddress.ip_address(str(value))
        except ValueError:
            continue
        if address.version == 4 and not (address.is_link_local or address.is_loopback or address.is_unspecified
                                         or address.is_multicast or address.is_reserved or str(address) == "255.255.255.255"):
            return str(address)
    return None


def close(session: Session, profile_id: str, device_id: str, actor: str) -> dict[str, Any]:
    current = status(session, profile_id, device_id)
    if not current["active"]:
        return current
    if current["state"] != "needs_attention":
        raise WindowsDeployError("The deployment is still running. It can be closed once it stops.")
    worker = _workers.get(current["run_id"])
    if worker is not None and worker.is_alive():
        raise WindowsDeployError("The import is still running in the app. Wait for it to finish before closing.")
    _finish(session, actor, current["run_id"], "failed", "Closed by the operator after a stopped step.")
    return status(session, profile_id, device_id)


LABELS = {"import": "Import {vm} onto {datastore}", "power": "Power {vm} on", "verify": "Windows starts and VMware Tools reports its address"}


def status(session: Session, profile_id: str, device_id: str) -> dict[str, Any]:
    """Stored evidence only; never contacts ESXi."""
    row = _run(session, device_id)
    if not row or row.data_json.get("profile_id") != profile_id:
        return {"state": "not_started", "active": False, "phases": [], "message": "Windows has not been deployed from the app on this server."}
    run = row.data_json
    operation = session.get(GuardedOperation, run["run_id"], populate_existing=True)
    results = _results(session, run["run_id"])
    attempts = {r.data_json["phase"] for r in session.scalars(select(AuditEvent).where(
        AuditEvent.event_type == "kit.windows.attempt", AuditEvent.data_json["run_id"].as_string() == run["run_id"]))}
    observed = _latest(session, "kit.windows.observed", run_id=run["run_id"])
    done = _latest(session, "kit.windows.done", run_id=run["run_id"])
    phases = []
    for phase in PHASES:
        result = results.get(phase)
        state = result["outcome"] if result else "sent" if phase in attempts else "todo"
        phases.append({"phase": phase, "label": LABELS[phase].format(vm=run["vm_name"], datastore=run["datastore"]),
                       "state": state, "message": result["message"] if result else None})
    problem = next((p for p in phases if p["state"] in {"failed", "uncertain"}), None)
    base = {"run_id": run["run_id"], "phases": phases, "vm_name": run["vm_name"], "datastore": run["datastore"],
            "network": run["network"], "image": run["image"], "esxi_address": run["address"],
            "started_at": row.created_at.replace(tzinfo=UTC).isoformat(),
            "last_check": observed.data_json if observed else None,
            "active": bool(operation and operation.active_device)}
    if done:
        data = done.data_json
        return {**base, "state": "verified" if data["outcome"] == "verified" else "failed", "message": done.message,
                "address": data.get("address"), "hostname": data.get("hostname"), "guest_os": data.get("guest_os")}
    if problem:
        return {**base, "state": "needs_attention", "message": problem["message"]}
    if "import" not in results:
        return {**base, "state": "running", "message": f"Importing {run['image']} onto {run['datastore']}. Large images take a while."}
    return {**base, "state": "running", "message": "Waiting for Windows to start and VMware Tools to report its address."}
