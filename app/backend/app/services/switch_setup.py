"""First setup of a kit's Cisco switch over its console cable, then proof over SSH.

Settings: name, domain, admin user and password (these become the switch's SSH sign-in),
optional enable password, management VLAN, DHCP or a static address with gateway, save or not.
Run (one GuardedOperation, resource "switch-setup", holding the switch):
  configure - over the console (through the console helper): skip the new-switch setup dialog,
              send the reviewed configuration, save it, and read the management address.
              One claimed send, in a worker thread; never repeated.
  verify    - read-only: sign in over SSH at that address and read the switch's identity.
A send without a recorded end needs attention; nothing is resent automatically.
"""

from __future__ import annotations

import re
import secrets
import threading
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AuditEvent, GuardedOperation, SwitchDeviceCredential, utcnow
from app.services.audit import record_audit_event
from app.services import switch_access

RESOURCE = "switch-setup"
ACTION = "cisco-console.bootstrap"
PHASES = ("configure", "verify")
CONSOLE_FRESH = timedelta(minutes=30)
HEARTBEAT_LIMIT = timedelta(minutes=6)
DHCP_WAIT = 180.0
VERIFY_DEADLINE = timedelta(minutes=10)
EXPECTED = {"configure": ("sw-sent-configure",), "verify": ("sw-ok-configure",)}
SETTING_KEYS = ("hostname", "domain", "vlan", "mode", "address", "prefix", "gateway", "save", "uplink", "uplink_mode")
_workers: dict[str, threading.Thread] = {}


def _session_factory():
    from app.core.database import SessionLocal

    return SessionLocal


class SwitchSetupError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _record(session: Session, actor: str, event_type: str, message: str, data: dict) -> AuditEvent:
    event = record_audit_event(session, actor=actor, event_type=event_type, message=message, data=data)
    session.commit()
    return event


def _latest(session: Session, event_type: str, **match: str) -> AuditEvent | None:
    query = select(AuditEvent).where(AuditEvent.event_type == event_type)
    for key, value in match.items():
        query = query.where(AuditEvent.data_json[key].as_string() == value)
    return session.scalar(query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(1))


# ---------------------------------------------------------------- settings

def _stored(session: Session, device_id: str) -> dict[str, Any]:
    record = session.get(SwitchDeviceCredential, device_id, populate_existing=True)
    return dict(record.credentials_json) if record is not None and isinstance(record.credentials_json, dict) else {}


def suggested_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9-]+", "-", name or "").strip("-").lower()
    return (cleaned if cleaned[:1].isalpha() else f"sw-{cleaned}")[:63] or "lab-switch"


def get_setup(session: Session, device_id: str, equipment_name: str = "") -> dict[str, Any]:
    switch_access.require_switch(session, device_id)
    stored = _stored(session, device_id)
    setup = stored.get("setup") if isinstance(stored.get("setup"), dict) else None
    return {
        "settings": setup,
        "defaults": {"hostname": suggested_name(equipment_name), "domain": "lab.local", "vlan": 1, "mode": "dhcp", "uplink": "auto", "uplink_mode": "access",
                     "address": None, "prefix": 24, "gateway": None, "save": True, "username": "admin"},
        "username": stored.get("username"),
        "password_configured": bool(stored.get("password")),
        "enable_password_configured": bool(stored.get("enable_password")),
        "console": {"port": stored.get("console_port"), "baud": switch_access._int(stored.get("console_baud")),
                    "last": switch_access.console_last(device_id)},
    }


def save_settings(session: Session, device_id: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:

    switch_access.require_switch(session, device_id)
    stored = _stored(session, device_id)
    password = payload.get("password") or stored.get("password")
    enable = payload.get("enable_password") or stored.get("enable_password")
    setup = {key: payload.get(key) for key in SETTING_KEYS}
    setup["vlan"] = int(setup["vlan"] or 1)
    setup["mode"] = setup["mode"] or "dhcp"
    setup["uplink"] = (setup.get("uplink") or "auto").strip() or "auto"
    setup["uplink_mode"] = setup.get("uplink_mode") or "access"
    if setup["mode"] != "static":
        setup.update(address=None, gateway=None)
    plan = _plan({**stored, "setup": setup, "username": payload.get("username"), "password": password, "enable_password": enable})
    problems = plan.problems()
    if problems:
        raise SwitchSetupError(problems[0])
    record = session.get(SwitchDeviceCredential, device_id)
    merged = {**stored, "setup": setup, "username": plan.username, "password": password}
    if enable:
        merged["enable_password"] = enable
    if setup["mode"] == "static":
        merged["host"] = setup["address"]
    if record is None:
        session.add(SwitchDeviceCredential(device_id=device_id, credentials_json=merged))
    else:
        record.credentials_json = merged
    session.commit()
    _record(session, actor, "kit.switch.settings", "Switch first-setup settings saved (no switch contacted).",
            {"device_id": device_id, **{k: setup[k] for k in SETTING_KEYS}, "username": plan.username})
    return get_setup(session, device_id)


def _plan(stored: dict[str, Any]):
    from app.providers.cisco_console_setup import SetupPlan

    setup = stored.get("setup") or {}
    return SetupPlan(hostname=str(setup.get("hostname") or ""), domain=str(setup.get("domain") or ""),
                     username=str(stored.get("username") or ""), password=str(stored.get("password") or ""),
                     enable_secret=stored.get("enable_password") or None, vlan=int(setup.get("vlan") or 1),
                     mode=str(setup.get("mode") or "dhcp"), address=setup.get("address"),
                     prefix=int(setup["prefix"]) if setup.get("prefix") not in (None, "") else None,
                     gateway=setup.get("gateway"), save=bool(setup.get("save", True)),
                     uplink=str(setup.get("uplink") or "auto"), uplink_mode=str(setup.get("uplink_mode") or "access"))


# ---------------------------------------------------------------- review

def _policy_blockers() -> list[str]:
    from app.providers.action_policy import ActionCategory, current_lab_action_policy

    return current_lab_action_policy().action_blockers(ACTION, ActionCategory.NETWORK_CONFIG)


def review(session: Session, device_id: str, *, lister=None) -> dict[str, Any]:
    """Reads the saved settings and the PC's COM ports; the switch is not contacted."""
    from app.providers import console_bridge

    switch_access.require_switch(session, device_id)
    stored = _stored(session, device_id)
    if not isinstance(stored.get("setup"), dict):
        return {"ready": False, "blockers": ["Fill in the switch settings and save them."], "permission": []}
    plan = _plan(stored)
    blockers = plan.problems()
    port, baud = stored.get("console_port"), switch_access._int(stored.get("console_baud"))
    last = switch_access.console_last(device_id)
    if not port or not last or not last.get("answered"):
        blockers.append("Read the switch on its console cable first (step 1).")
    else:
        checked = datetime.fromisoformat(str(last["checked_at"]).replace("Z", "+00:00"))
        if _now() - _aware(checked) > CONSOLE_FRESH:
            blockers.append("The console reading is more than 30 minutes old. Read the switch again.")
        if last.get("prompt_state") not in {"setup-wizard", "exec", "privileged-exec"}:
            blockers.append(last.get("state_text") or "The switch is not at a prompt the app can set up from.")
        try:
            listed = (lister or console_bridge.list_ports)()
            if not any(getattr(item, "device", None) == port for item in listed):
                blockers.append(f"{port} is no longer on this PC. Plug the console cable back in and read the switch again.")
        except (console_bridge.BridgeUnavailable, ValueError):
            blockers.append("The console helper isn't running on this PC.")
    notes = []
    if plan.vlan != 1:
        where = plan.uplink if plan.uplink != "auto" else "the one port with a network cable (found when the setup runs)"
        how = "untagged (access)" if plan.uplink_mode == "access" else "tagged (trunk)"
        notes.append(f"VLAN {plan.vlan} is put on {where}, {how}. The port it plugs into on your network must carry VLAN {plan.vlan} the same way.")
    if (last or {}).get("prompt_state") != "setup-wizard":
        notes.append("The switch is not showing its new-switch setup dialog, so it may already have settings. Its users, management address and SSH settings are replaced.")
    return {"ready": not blockers, "blockers": blockers, "permission": _policy_blockers(), "notes": notes,
            "replace_needed": (last or {}).get("prompt_state") != "setup-wizard",
            "console_port": port, "baud": baud, "prompt_state": (last or {}).get("prompt_state"),
            "hostname": plan.hostname, "vlan": plan.vlan, "mode": plan.mode, "address": plan.address,
            "prefix": plan.prefix, "gateway": plan.gateway, "username": plan.username, "save": plan.save,
            "preview": plan.preview()}


# ---------------------------------------------------------------- run

def _run(session, device_id) -> AuditEvent | None:
    return _latest(session, "kit.switch.run", device_id=device_id)


def _results(session, run_id) -> dict[str, dict]:
    rows = session.scalars(select(AuditEvent).where(
        AuditEvent.event_type == "kit.switch.result", AuditEvent.data_json["run_id"].as_string() == run_id
    ).order_by(AuditEvent.created_at, AuditEvent.id))
    return {r.data_json["phase"]: r.data_json for r in rows}


def _result(session, actor, run_id, phase, outcome, message, **extra) -> bool:
    moved = session.execute(update(GuardedOperation)
                            .where(GuardedOperation.id == run_id, GuardedOperation.active_device.is_not(None),
                                   GuardedOperation.status.in_(EXPECTED[phase]))
                            .values(status=f"sw-{outcome}-{phase}", updated_at=utcnow()))
    if moved.rowcount != 1:
        session.rollback()
        return False
    record_audit_event(session, actor=actor, event_type="kit.switch.result", message=message,
                       data={"run_id": run_id, "phase": phase, "outcome": outcome, "message": message, **extra})
    session.commit()
    return True


def _heartbeat(session, run_id, step: str) -> None:
    session.execute(update(GuardedOperation).where(GuardedOperation.id == run_id, GuardedOperation.status == "sw-sent-configure")
                    .values(updated_at=utcnow()))
    session.commit()
    _record(session, "lab-builder", "kit.switch.progress", f"Switch setup: {step}.", {"run_id": run_id, "step": step})


def _finish(session, actor, run_id, outcome, message, **extra):
    session.execute(update(GuardedOperation).where(GuardedOperation.id == run_id)
                    .values(status=outcome, active_device=None, updated_at=utcnow()))
    _record(session, actor, "kit.switch.done", message, {"run_id": run_id, "outcome": outcome, **extra})


def _configure_worker(run: dict[str, Any], stored: dict[str, Any], actor: str, opener=None) -> None:
    from app.providers import console_bridge
    from app.providers.cisco_console_setup import Console, SetupStopped, configure, reach_privileged, read_address, read_running_config, read_serial, scrub
    from app.services.runtime_write_scope import dispatch_lease

    plan = _plan(stored)
    with _session_factory()() as session:
        connection = None
        console = None
        try:
            with dispatch_lease(ACTION):
                connection = (opener or console_bridge.open_port)(run["console_port"], run["baud"])
                console = Console(connection)
                _heartbeat(session, run["run_id"], "reaching the switch's prompt")
                start_state = reach_privileged(console)
                if start_state != "wizard" and not run.get("replace_existing"):
                    raise SetupStopped("The switch skipped its new-switch setup dialog, so it may already have settings. Nothing was changed; confirm replacing them and run again.", sent=False)
                serial = read_serial(console)
                _heartbeat(session, run["run_id"], "reading the switch's configuration as it is now")
                config_before = read_running_config(console)
                done = configure(console, plan, progress=lambda step: _heartbeat(session, run["run_id"], step))
                address, status = read_address(console, plan.vlan)
                deadline = time.monotonic() + DHCP_WAIT
                while plan.mode == "dhcp" and not address and time.monotonic() < deadline:
                    _heartbeat(session, run["run_id"], "waiting for a DHCP address")
                    time.sleep(10)
                    address, status = read_address(console, plan.vlan)
                _heartbeat(session, run["run_id"], "reading the switch's configuration after the setup")
                config_after = read_running_config(console)
        except SetupStopped as exc:
            sent = (console.sent if console else [])
            _result(session, actor, run["run_id"], "configure", "failed", scrub(str(exc), plan.password, plan.enable_secret), changed=exc.sent, sent=sent)
            return
        except Exception as exc:  # noqa: BLE001 - an interrupted console session has an unknown outcome
            sent = (console.sent if console else [])
            outcome = "uncertain" if any(line.startswith("configure terminal") for line in sent) else "failed"
            _result(session, actor, run["run_id"], "configure", outcome,
                    f"The console session stopped ({type(exc).__name__})." + (" Some settings may have been sent; read the switch on its console before trying again." if outcome == "uncertain" else " Nothing was changed."),
                    sent=sent)
            return
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:  # noqa: BLE001
                    pass
        if not address:
            _result(session, actor, run["run_id"], "configure", "failed",
                    (f"The settings were sent{' and saved' if done['saved'] else ''}, but Vlan{plan.vlan} has no address"
                     + (" from DHCP after 3 minutes. Check the switch's uplink is in a VLAN with a DHCP server." if plan.mode == "dhcp" else ".")),
                    sent=done["sent"], saved=done["saved"], interface_status=status, config_before=config_before, config_after=config_after)
            return
        _result(session, actor, run["run_id"], "configure", "ok",
                f"{plan.hostname} is set up at {address}{' and saved' if done['saved'] else ' (not saved)'}.",
                address=address, saved=done["saved"], sent=done["sent"], start_state=start_state, interface_status=status, serial=serial,
                config_before=config_before, config_after=config_after)


def start(session: Session, profile_id: str, device_id: str, actor: str, *, replace_existing: bool = False, opener=None, lister=None) -> dict[str, Any]:
    from app.services.guarded_operation_ledger import OperationConflict, reserve

    if status(session, profile_id, device_id)["active"]:
        raise SwitchSetupError("A switch setup is already running.")
    snapshot = _stored(session, device_id)
    plan = review(session, device_id, lister=lister)
    if plan["blockers"] or plan["permission"]:
        raise SwitchSetupError((plan["blockers"] + plan["permission"])[0])
    if _plan(snapshot).preview() != plan["preview"]:
        raise SwitchSetupError("The settings changed while they were being reviewed. Review them again.")
    if plan["prompt_state"] != "setup-wizard" and not replace_existing:
        raise SwitchSetupError("This switch is not showing its new-switch setup dialog. Confirm that its existing settings may be replaced.")
    intent = {k: plan[k] for k in ("console_port", "baud", "hostname", "vlan", "mode", "address", "prefix", "gateway", "username", "save")}
    intent["replace_existing"] = bool(replace_existing)
    try:
        operation = reserve(session, profile_id=profile_id, device_id=device_id, resource=RESOURCE,
                            idempotency_key=secrets.token_hex(16), actor=actor, reviewed_intent=intent)
    except OperationConflict as exc:
        raise SwitchSetupError(str(exc)) from None
    run = {"run_id": operation.id, "profile_id": profile_id, "device_id": device_id, **intent}
    _record(session, actor, "kit.switch.run", "Switch first setup approved.", run)
    claim = session.execute(update(GuardedOperation)
                            .where(GuardedOperation.id == operation.id, GuardedOperation.status == "accepted")
                            .values(status="sw-sent-configure", updated_at=utcnow()))
    if claim.rowcount != 1:
        session.rollback()
        raise SwitchSetupError("This setup is already claimed. Nothing was sent again.")
    _record(session, actor, "kit.switch.attempt", "Switch setup over the console starting; outcome unverified.",
            {"run_id": operation.id, "phase": "configure", "at": _now().isoformat()})
    worker = threading.Thread(target=_configure_worker, args=(run, snapshot, actor, opener),
                              name=f"switch-setup-{operation.id}", daemon=True)
    _workers[operation.id] = worker
    worker.start()
    return status(session, profile_id, device_id)


def advance(session: Session, profile_id: str, device_id: str, actor: str) -> dict[str, Any]:
    """Watch the console run; then sign in over SSH (read-only) until it answers."""
    current = status(session, profile_id, device_id)
    if not current["active"] or current["state"] == "needs_attention":
        return current
    run = _run(session, device_id).data_json
    run_id = run["run_id"]
    results = _results(session, run_id)
    if "configure" not in results:
        operation = session.get(GuardedOperation, run_id, populate_existing=True)
        worker = _workers.get(run_id)
        if (worker is None or not worker.is_alive()) and _now() - _aware(operation.updated_at) > HEARTBEAT_LIMIT:
            _result(session, actor, run_id, "configure", "uncertain",
                    "The console session's end was not recorded (the app restarted). Read the switch on its console before trying again; nothing was resent.")
        return status(session, profile_id, device_id)
    configured = _latest(session, "kit.switch.result", run_id=run_id, phase="configure")
    address = configured.data_json.get("address")
    if _now() - _aware(configured.created_at) > VERIFY_DEADLINE:
        _result(session, actor, run_id, "verify", "uncertain",
                f"The switch has not answered SSH at {address} for 10 minutes. Check the switch's uplink cable and VLAN.")
        return status(session, profile_id, device_id)
    switch_access.save_access(session, device_id, {"host": address})
    check = switch_access.check(session, device_id)
    _record(session, actor, "kit.switch.observed", "Read-only SSH check.", {"run_id": run_id, **{k: check.get(k) for k in ("status", "message", "checked_at")}})
    serial = configured.data_json.get("serial")
    if check.get("status") == "ok" and (check.get("hostname") or "").lower() != run["hostname"].lower():
        _result(session, actor, run_id, "verify", "failed",
                f"Something answered SSH at {address}, but it calls itself {check.get('hostname') or 'something else'}, not {run['hostname']}. Another device may have that address.")
    elif check.get("status") == "ok" and serial and check.get("serial") and check["serial"] != serial:
        _result(session, actor, run_id, "verify", "failed",
                f"The switch at {address} has a different serial number from the one on the console cable. Another device may have that address.")
    elif check.get("status") == "ok" and _result(session, actor, run_id, "verify", "ok", check["message"], address=address,
                                                  model=check.get("model"), version=check.get("version"), hostname=check.get("hostname")):
        _finish(session, actor, run_id, "verified", f"{check.get('hostname') or run['hostname']} answers SSH at {address}.",
                address=address, model=check.get("model"), version=check.get("version"), hostname=check.get("hostname"))
    elif check.get("status") == "sign_in_failed":
        _result(session, actor, run_id, "verify", "failed", f"SSH at {address} refused the admin sign-in that was just set.")
    return status(session, profile_id, device_id)


def close(session: Session, profile_id: str, device_id: str, actor: str) -> dict[str, Any]:
    current = status(session, profile_id, device_id)
    if not current["active"]:
        return current
    if current["state"] != "needs_attention":
        raise SwitchSetupError("The setup is still running. It can be closed once it stops.")
    worker = _workers.get(current["run_id"])
    if worker is not None and worker.is_alive():
        raise SwitchSetupError("The console session is still running. Wait for it to finish.")
    _finish(session, actor, current["run_id"], "failed", "Closed by the operator after a stopped step.")
    return status(session, profile_id, device_id)


LABELS = {"configure": "Set up {hostname} over the console ({port})", "verify": "{hostname} answers SSH at its new address"}


def status(session: Session, profile_id: str, device_id: str) -> dict[str, Any]:
    """Stored evidence only; never contacts the switch."""
    row = _run(session, device_id)
    if not row or row.data_json.get("profile_id") != profile_id:
        return {"state": "not_started", "active": False, "phases": [], "message": "The switch has not been set up from the app."}
    run = row.data_json
    operation = session.get(GuardedOperation, run["run_id"], populate_existing=True)
    results = _results(session, run["run_id"])
    progress = _latest(session, "kit.switch.progress", run_id=run["run_id"])
    observed = _latest(session, "kit.switch.observed", run_id=run["run_id"])
    done = _latest(session, "kit.switch.done", run_id=run["run_id"])
    phases = []
    for phase in PHASES:
        result = results.get(phase)
        configured_ok = results.get("configure", {}).get("outcome") == "ok"
        state = result["outcome"] if result else "sent" if (phase == "configure" or configured_ok) else "todo"
        phases.append({"phase": phase, "label": LABELS[phase].format(hostname=run["hostname"], port=run["console_port"]),
                       "state": state, "message": result["message"] if result else None})
    configured = results.get("configure") or {}
    base = {"run_id": run["run_id"], "phases": phases, "hostname": run["hostname"], "console_port": run["console_port"],
            "address": configured.get("address"), "sent": configured.get("sent"), "saved": configured.get("saved"),
            "step": progress.data_json.get("step") if progress and "configure" not in results else None,
            "last_check": observed.data_json if observed else None,
            "active": bool(operation and operation.active_device)}
    if done:
        data = done.data_json
        return {**base, "state": "verified" if data["outcome"] == "verified" else "failed", "message": done.message,
                "model": data.get("model"), "version": data.get("version")}
    problem = next((p for p in phases if p["state"] in {"failed", "uncertain"}), None)
    if problem:
        return {**base, "state": "needs_attention", "message": problem["message"]}
    return {**base, "state": "running", "message": "Setting the switch up…" if "configure" not in results else "Checking SSH at the new address…"}
