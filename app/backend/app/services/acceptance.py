"""Whole-kit acceptance test: prove the Windows VM is a usable lab machine, not just "steps done".

One GuardedOperation (resource "acceptance-test"), advanced one step per poll:
  outside - read-only: VM powered on, VMware Tools running, a usable address, and this PC can ping it.
  inside  - read-only commands inside Windows through VMware Tools (ping the gateway, look up a name,
            report its address), signed in with the saved Windows administrator account.
  reboot  - the one change: ask Windows to restart itself (VMware Tools, a clean restart). Sent once;
            a lost reply is decided by reading, never by sending again.
  after   - the outside checks again once Windows is back.
The Windows sign-in is kept owner-only under .local/windows/, never returned or logged.
"""

from __future__ import annotations

import ipaddress
import json
import platform
import re
import secrets
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AuditEvent, GuardedOperation, utcnow
from app.services.audit import record_audit_event

RESOURCE = "acceptance-test"
ACTION_POWER = "esxi.vm-power"
PHASES = ("outside", "inside", "reboot", "after")
EXPECTED = {"outside": ("ac-run-outside",), "inside": ("ac-ok-outside",), "reboot": ("ac-ok-inside", "ac-sent-reboot"), "after": ("ac-ok-reboot",)}
NEXT = {"outside": "ac-run-outside", "inside": "ac-ok-outside", "reboot": "ac-ok-inside", "after": "ac-ok-reboot"}
REBOOT_DEADLINE = timedelta(minutes=15)
REBOOT_GRACE = timedelta(seconds=45)
USERNAME = re.compile(r"^[A-Za-z0-9._\\-]{1,64}$")
HOSTNAME = re.compile(r"^(?=.{1,253}$)[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$")


class AcceptanceError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _root() -> Path:
    from app.services.hpe_raid import REPO_ROOT

    return REPO_ROOT / ".local" / "windows"


def _signin_path(device_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9-]", "", device_id)
    return _root() / f"{safe}.guest"


def _signin(device_id: str) -> dict[str, str] | None:
    path = _signin_path(device_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("username") and data.get("password") else None


def save_signin(device_id: str, username: str, password: str) -> dict[str, Any]:
    from app.services.esxi_install import _write_private

    username = (username or "").strip()
    if not USERNAME.fullmatch(username):
        raise AcceptanceError("Enter the Windows administrator user name (for example Administrator).")
    if not password or len(password) > 128 or any(ord(c) < 32 for c in password):
        raise AcceptanceError("Enter the Windows administrator password.")
    _root().mkdir(parents=True, exist_ok=True)
    _write_private(_signin_path(device_id), json.dumps({"username": username, "password": password}))
    return signin_status(device_id)


def signin_status(device_id: str) -> dict[str, Any]:
    saved = _signin(device_id)
    return {"username": saved["username"] if saved else None, "password_saved": bool(saved)}


def _target(session: Session, profile_id: str, device_id: str) -> dict[str, Any]:
    from app.services import esxi_install, windows_deploy

    host = windows_deploy._host(session, profile_id, device_id)
    status = windows_deploy.status(session, profile_id, device_id)
    if status.get("state") != "verified" or not status.get("vm_name"):
        raise AcceptanceError("Deploy and verify Windows first (Install Windows).")
    kit = esxi_install.get_settings(session, profile_id, device_id).get("kit") or {}
    return {"esxi": host["address"], "password": host["password"], "vm": status["vm_name"], "gateway": kit.get("gateway"),
            "default_name": _default_lookup(session, profile_id, device_id)}


def _default_lookup(session: Session, profile_id: str, device_id: str) -> str | None:
    """The ESXi host's name (with the kit's domain): something every kit's DNS should know. Stored settings only."""
    from app.services import esxi_install

    try:
        esxi = esxi_install.get_settings(session, profile_id, device_id)
    except Exception:  # noqa: BLE001 - only a suggestion
        return None
    name, domain = esxi.get("hostname"), (esxi.get("kit") or {}).get("domain_name")
    return f"{name}.{domain}" if name and domain and "." not in name else name


def _policy_blockers() -> list[str]:
    from app.providers.action_policy import ActionCategory, current_lab_action_policy

    return list(current_lab_action_policy().action_blockers(ACTION_POWER, ActionCategory.VM_DEPLOY))


def _latest(session: Session, event_type: str, **match: str) -> AuditEvent | None:
    query = select(AuditEvent).where(AuditEvent.event_type == event_type)
    for key, value in match.items():
        query = query.where(AuditEvent.data_json[key].as_string() == value)
    return session.scalar(query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(1))


def _run(session: Session, device_id: str) -> AuditEvent | None:
    return _latest(session, "kit.acceptance.run", device_id=device_id)


def _results(session: Session, run_id: str) -> dict[str, dict[str, Any]]:
    rows = session.scalars(select(AuditEvent).where(AuditEvent.event_type == "kit.acceptance.result",
                                                    AuditEvent.data_json["run_id"].as_string() == run_id).order_by(AuditEvent.created_at, AuditEvent.id))
    return {row.data_json["phase"]: row.data_json for row in rows}


def _result(session: Session, actor: str, run_id: str, phase: str, outcome: str, message: str, checks: list[dict[str, Any]], **extra: Any) -> bool:
    moved = session.execute(update(GuardedOperation).where(GuardedOperation.id == run_id, GuardedOperation.active_device.is_not(None),
                                                           GuardedOperation.status.in_(EXPECTED[phase]))
                            .values(status=f"ac-{outcome}-{phase}", updated_at=utcnow()))
    if moved.rowcount != 1:
        session.rollback()
        return False
    record_audit_event(session, actor=actor, event_type="kit.acceptance.result", message=message,
                       data={"run_id": run_id, "phase": phase, "outcome": outcome, "message": message, "checks": checks, **extra})
    session.commit()
    return True


def _complete(session: Session, actor: str, run_id: str, checks: list[dict[str, Any]], address: str | None, vm: str) -> None:
    """The last check and the end of the run in one transaction: no window where all checks passed but the run stays open."""
    moved = session.execute(update(GuardedOperation).where(GuardedOperation.id == run_id, GuardedOperation.active_device.is_not(None),
                                                           GuardedOperation.status == "ac-ok-reboot")
                            .values(status="verified", active_device=None, updated_at=utcnow()))
    if moved.rowcount != 1:
        session.rollback()
        return
    back = f"Windows is back at {address}."
    record_audit_event(session, actor=actor, event_type="kit.acceptance.result", message=back,
                       data={"run_id": run_id, "phase": "after", "outcome": "ok", "message": back, "checks": checks})
    message = f"Acceptance test passed: {vm} works from inside and outside and survives a restart."
    record_audit_event(session, actor=actor, event_type="kit.acceptance.done", message=message, data={"run_id": run_id, "outcome": "verified"})
    session.commit()


def _finish(session: Session, actor: str, run_id: str, outcome: str, message: str) -> None:
    session.execute(update(GuardedOperation).where(GuardedOperation.id == run_id).values(status=outcome, active_device=None, updated_at=utcnow()))
    record_audit_event(session, actor=actor, event_type="kit.acceptance.done", message=message, data={"run_id": run_id, "outcome": outcome})
    session.commit()


def _usable(address: str | None) -> bool:
    try:
        ip = ipaddress.ip_address(str(address))
    except ValueError:
        return False
    return ip.version == 4 and not (ip.is_link_local or ip.is_loopback or ip.is_unspecified)


def _ping_from_pc(address: str) -> bool:
    flag = "-n" if platform.system() == "Windows" else "-c"
    try:
        return subprocess.run(["ping", flag, "2", address], capture_output=True, timeout=20, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _outside(target: dict[str, Any], *, ping=_ping_from_pc) -> tuple[bool, list[dict[str, Any]], str | None]:
    from app.providers import esxi_govc as govc

    vm = govc.vm_info(target["esxi"], target["password"], target["vm"])
    address = (vm or {}).get("ip")
    checks = [
        {"name": "VM is powered on", "ok": bool(vm and vm["power"] == "poweredOn")},
        {"name": "VMware Tools is running", "ok": bool(vm and vm["tools"] == "guestToolsRunning")},
        {"name": "Windows has an address", "ok": _usable(address), "detail": address},
    ]
    if _usable(address):
        checks.append({"name": "This PC can reach it (ping)", "ok": ping(address), "detail": address})
    return all(check["ok"] for check in checks), checks, address


BOOT_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
BOOT_CHECK = "Windows reports when it last started"


def _boot_time(target: dict[str, Any], login: str) -> str | None:
    """When Windows itself last started (UTC). A restart is proven only by this changing."""
    from app.providers import esxi_govc as govc

    code, out = govc.guest_run(target["esxi"], target["password"], target["vm"], login, "powershell", "-NoProfile", "-NonInteractive", "-Command",
                               "(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToUniversalTime().ToString('o')")
    lines = [line.strip() for line in out.splitlines() if line.strip()]
    return lines[-1] if code == 0 and lines and BOOT_TIME.match(lines[-1]) else None


def _inside(target: dict[str, Any], login: str, name: str) -> tuple[bool, list[dict[str, Any]]]:
    from app.providers import esxi_govc as govc

    checks = []
    if target.get("gateway"):
        code, out = govc.guest_run(target["esxi"], target["password"], target["vm"], login, "ping", "-n", "2", target["gateway"])
        # Windows ping exits 0 on "Destination host unreachable" too; only a reply has TTL=.
        checks.append({"name": f"Windows reaches the gateway {target['gateway']}", "ok": code == 0 and "TTL=" in out.upper()})
    code, out = govc.guest_run(target["esxi"], target["password"], target["vm"], login, "nslookup", name)
    answer = out.split("Name:", 1)[1] if "Name:" in out else ""
    resolved = code == 0 and bool(re.search(r"^Address(es)?:\s+\S+", answer, re.M))
    checks.append({"name": f"Windows looks up {name}", "ok": resolved})
    code, out = govc.guest_run(target["esxi"], target["password"], target["vm"], login, "hostname")
    checks.append({"name": "Signed in to Windows", "ok": code == 0, "detail": out.strip().splitlines()[-1] if out.strip() else None})
    boot = _boot_time(target, login)
    checks.append({"name": BOOT_CHECK, "ok": bool(boot), "detail": boot})
    return all(check["ok"] for check in checks), checks


def start(session: Session, profile_id: str, device_id: str, actor: str, name: str | None = None) -> dict[str, Any]:
    from app.services.guarded_operation_ledger import OperationConflict, reserve

    if status(session, profile_id, device_id)["active"]:
        raise AcceptanceError("An acceptance test is already running on this server.")
    target = _target(session, profile_id, device_id)
    if blockers := _policy_blockers():
        raise AcceptanceError(blockers[0])
    if not _signin(device_id):
        raise AcceptanceError("Save the Windows administrator sign-in first.")
    lookup = (name or target.get("default_name") or "").strip()
    if not HOSTNAME.fullmatch(lookup):
        raise AcceptanceError("Enter a name for Windows to look up (for example the ESXi host name).")
    try:
        operation = reserve(session, profile_id=profile_id, device_id=device_id, resource=RESOURCE, idempotency_key=secrets.token_hex(16),
                            actor=actor, reviewed_intent={"vm": target["vm"], "esxi": target["esxi"], "lookup": lookup})
    except OperationConflict as exc:
        raise AcceptanceError(str(exc)) from None
    session.execute(update(GuardedOperation).where(GuardedOperation.id == operation.id).values(status="ac-run-outside"))
    record_audit_event(session, actor=actor, event_type="kit.acceptance.run", message="Acceptance test started.",
                       data={"run_id": operation.id, "profile_id": profile_id, "device_id": device_id, "vm": target["vm"], "esxi": target["esxi"], "lookup": lookup})
    session.commit()
    return status(session, profile_id, device_id)


def advance(session: Session, profile_id: str, device_id: str, actor: str, *, ping=_ping_from_pc) -> dict[str, Any]:
    from app.providers import esxi_govc as govc
    from app.services.runtime_write_scope import dispatch_lease

    current = status(session, profile_id, device_id)
    if not current["active"] or current["state"] == "needs_attention":
        return current
    run = _run(session, device_id).data_json
    run_id = run["run_id"]
    results = _results(session, run_id)
    target = _target(session, profile_id, device_id)
    signin = _signin(device_id)
    login = f"{signin['username']}:{signin['password']}" if signin else ""
    phase = next((p for p in PHASES if p not in results), None)
    if phase is None:  # every check recorded but the run still open: close it from the records
        passed = all(r["outcome"] == "ok" for r in results.values())
        _finish(session, actor, run_id, "verified" if passed else "failed", "Acceptance test closed from its recorded checks.")
        return status(session, profile_id, device_id)
    if (target["vm"], target["esxi"]) != (run["vm"], run["esxi"]):
        _result(session, actor, run_id, phase, "failed", "The Windows VM or its ESXi host changed after the test started. Nothing was sent; run the test again.", [])
        return status(session, profile_id, device_id)
    try:
        if "outside" not in results:
            ok, checks, _ = _outside(target, ping=ping)
            _result(session, actor, run_id, "outside", "ok" if ok else "failed", "Windows answers from outside." if ok else "Windows is not reachable from outside.", checks)
        elif "inside" not in results:
            if not signin:
                _result(session, actor, run_id, "inside", "failed", "The Windows sign-in is no longer saved.", [])
            else:
                ok, checks = _inside(target, login, run["lookup"])
                boot = next((check["detail"] for check in checks if check["name"] == BOOT_CHECK), None)
                _result(session, actor, run_id, "inside", "ok" if ok else "failed", "Windows works from inside." if ok else "A check inside Windows failed.", checks, boot=boot)
        elif "reboot" not in results:
            attempt = _latest(session, "kit.acceptance.attempt", run_id=run_id)
            if not attempt and (blockers := _policy_blockers()):
                _result(session, actor, run_id, "reboot", "failed", f"Restart not sent: {blockers[0]}", [])
            elif not attempt:
                claim = session.execute(update(GuardedOperation).where(GuardedOperation.id == run_id, GuardedOperation.status == "ac-ok-inside")
                                        .values(status="ac-sent-reboot", updated_at=utcnow()))
                if claim.rowcount != 1:
                    session.rollback()
                    return status(session, profile_id, device_id)
                record_audit_event(session, actor=actor, event_type="kit.acceptance.attempt", message="Windows restart requested; outcome unverified.",
                                   data={"run_id": run_id, "at": _now().isoformat()})
                session.commit()
                try:
                    with dispatch_lease(ACTION_POWER):
                        govc.guest_reboot(target["esxi"], target["password"], target["vm"])
                except Exception as exc:  # noqa: BLE001 - decided by reading, never resent
                    record_audit_event(session, actor=actor, event_type="kit.acceptance.observed", message=f"Restart reply not confirmed ({type(exc).__name__}).",
                                       data={"run_id": run_id})
                    session.commit()
            else:
                sent = datetime.fromisoformat(attempt.data_json["at"])
                if _now() - sent < REBOOT_GRACE:
                    return status(session, profile_id, device_id)
                ok, checks, _ = _outside(target, ping=ping)
                before = results["inside"].get("boot")
                after = _boot_time(target, login) if ok and signin else None
                if ok:
                    checks.append({"name": "Windows started again", "ok": bool(after and after != before), "detail": after})
                if ok and after and after != before:
                    _result(session, actor, run_id, "reboot", "ok", "Windows restarted and came back.", checks, boot=after)
                elif _now() - sent > REBOOT_DEADLINE:
                    message = ("Windows answers, but its start time did not change: it never restarted." if ok and after == before
                               else "Windows has not come back 15 minutes after the restart. Open the VM console in ESXi.")
                    _result(session, actor, run_id, "reboot", "uncertain", message + " Nothing was sent again.", checks)
        elif "after" not in results:
            ok, checks, address = _outside(target, ping=ping)
            if ok:
                _complete(session, actor, run_id, checks, address, target["vm"])
            else:
                _result(session, actor, run_id, "after", "failed", "Windows did not answer after the restart.", checks)
    except govc.GovcError as exc:
        record_audit_event(session, actor=actor, event_type="kit.acceptance.observed", message=str(exc)[:300], data={"run_id": run_id})
        session.commit()
        # A read that fails ends that check; while waiting on the restart, only the deadline decides.
        if phase != "reboot":
            _result(session, actor, run_id, phase, "failed", str(exc)[:300], [])
        else:
            attempt = _latest(session, "kit.acceptance.attempt", run_id=run_id)
            if attempt and _now() - datetime.fromisoformat(attempt.data_json["at"]) > REBOOT_DEADLINE:
                _result(session, actor, run_id, "reboot", "uncertain", "Windows has not come back 15 minutes after the restart. Open the VM console in ESXi. Nothing was sent again.", [])
    return status(session, profile_id, device_id)


def close(session: Session, profile_id: str, device_id: str, actor: str) -> dict[str, Any]:
    current = status(session, profile_id, device_id)
    if current["active"] and current["state"] == "needs_attention":
        _finish(session, actor, current["run_id"], "failed", "Closed by the operator after a failed check.")
    elif current["active"]:
        raise AcceptanceError("The test is still running.")
    return status(session, profile_id, device_id)


LABELS = {"outside": "Windows answers from outside", "inside": "Windows works from inside", "reboot": "Windows restarts cleanly", "after": "Windows is back after the restart"}


def status(session: Session, profile_id: str, device_id: str) -> dict[str, Any]:
    """Stored records only; never contacts ESXi or Windows."""
    row = _run(session, device_id)
    signin = {**signin_status(device_id)}
    default = _default_lookup(session, profile_id, device_id)
    if not row or row.data_json.get("profile_id") != profile_id:
        return {"state": "not_started", "active": False, "phases": [], "message": "", "signin": signin, "default_lookup": default}
    run = row.data_json
    operation = session.get(GuardedOperation, run["run_id"], populate_existing=True)
    results = _results(session, run["run_id"])
    done = _latest(session, "kit.acceptance.done", run_id=run["run_id"])
    phases = [{"phase": phase, "label": LABELS[phase], "state": results[phase]["outcome"] if phase in results else "todo",
               "message": results[phase]["message"] if phase in results else None, "checks": results[phase]["checks"] if phase in results else []}
              for phase in PHASES]
    first_open = next((p for p in phases if p["state"] == "todo"), None)
    if first_open and operation and operation.active_device:
        first_open["state"] = "running"
    base = {"run_id": run["run_id"], "phases": phases, "vm": run["vm"], "lookup": run["lookup"], "signin": signin, "default_lookup": default,
            "started_at": row.created_at.replace(tzinfo=UTC).isoformat() if row.created_at.tzinfo is None else row.created_at.isoformat(),
            "active": bool(operation and operation.active_device)}
    if done:
        return {**base, "state": "verified" if done.data_json["outcome"] == "verified" else "failed", "message": done.message,
                "finished_at": done.created_at.replace(tzinfo=UTC).isoformat() if done.created_at.tzinfo is None else done.created_at.isoformat()}
    problem = next((p for p in phases if p["state"] in {"failed", "uncertain"}), None)
    if problem:
        return {**base, "state": "needs_attention", "message": problem["message"]}
    return {**base, "state": "running", "message": "Testing…"}
