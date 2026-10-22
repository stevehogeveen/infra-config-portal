"""Reset for the next person: return a kit's Cisco switch to factory settings over its console cable.

Locked down (destructive): needs LAB_ALLOW_FACTORY_RESET=true, the typed "switch reset only"
permission, and the typed phrase "ERASE <switch name>". One GuardedOperation, resource
"switch-reset", holding the switch:
  erase   - over the console: reach the # prompt (the app's saved enable password if asked),
            check the serial is the switch this kit set up, then write erase, delete vlan.dat and
            reload without saving. One claimed send, in a worker thread; never repeated.
  restart - the same console session watches the switch start again; done only when it shows its
            new-switch setup dialog (proof the settings are gone).
"""

from __future__ import annotations

import secrets
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AuditEvent, DeviceInventory, GuardedOperation, utcnow
from app.services import switch_access
from app.services.audit import record_audit_event

RESOURCE = "switch-reset"
ACTION = "cisco-console.erase-reload"
PHASES = ("erase", "restart")
CONSOLE_FRESH = timedelta(minutes=30)
HEARTBEAT_LIMIT = timedelta(minutes=6)
EXPECTED = {"erase": ("rs-sent-erase",), "restart": ("rs-ok-erase",)}
ERASES = ["Its saved settings (startup configuration): name, users and passwords, management address, SSH",
          "Its VLAN database (vlan.dat)",
          "Then it restarts without saving, so it comes back as a new switch"]
_workers: dict[str, threading.Thread] = {}


class SwitchResetError(RuntimeError):
    pass


def _session_factory():
    from app.core.database import SessionLocal

    return SessionLocal


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


def phrase(name: str) -> str:
    return f"ERASE {name}"


SCOPE_BLOCKER = "outside the enabled live-operation scope"


def _policy_blockers() -> list[str]:
    """Everything the lab policy says, plus: the runtime permission must be exactly "switch reset only"."""
    from app.providers.action_policy import ActionCategory, current_lab_action_policy
    from app.services.runtime_write_scope import runtime_override

    blockers = list(current_lab_action_policy().action_blockers(ACTION, ActionCategory.FACTORY_RESET))
    if runtime_override() != "switch_reset_only" and not any(SCOPE_BLOCKER in b for b in blockers):
        blockers.append("This hardware action is outside the enabled live-operation scope.")
    return blockers


def enabled() -> bool:
    from app.core.config import settings
    from app.providers.action_policy import LOCAL_LAB_READWRITE_MODE, current_lab_action_policy

    policy = current_lab_action_policy(settings.provider_mode)
    return settings.provider_mode == LOCAL_LAB_READWRITE_MODE and bool(policy.allow_factory_reset)


def _known_serial(session: Session, device_id: str) -> str | None:
    """The serial this app recorded when it set the switch up (console), if any."""
    rows = session.scalars(select(AuditEvent).where(AuditEvent.event_type == "kit.switch.result",
                                                    AuditEvent.data_json["phase"].as_string() == "configure",
                                                    AuditEvent.data_json["outcome"].as_string() == "ok")
                           .order_by(AuditEvent.created_at.desc()).limit(50))
    for event in rows:
        run = _latest(session, "kit.switch.run", run_id=str(event.data_json.get("run_id")))
        if run and run.data_json.get("device_id") == device_id:
            return event.data_json.get("serial")
    return None


def review(session: Session, device_id: str, *, lister=None) -> dict[str, Any]:
    """Saved console port, the last console reading and permission; the switch is not contacted."""
    from app.providers import console_bridge

    device = switch_access.require_switch(session, device_id)
    saved = switch_access._saved(session.get(switch_access.SwitchDeviceCredential, device_id))
    blockers: list[str] = []
    if not enabled():
        blockers.append("Reset is turned off for this lab (LAB_ALLOW_FACTORY_RESET is not true).")
    port, baud = saved.get("console_port"), switch_access._int(saved.get("console_baud"))
    last = switch_access.console_last(device_id)
    if not port or not last or not last.get("answered"):
        blockers.append("Read the switch on its console cable first (Set up the switch, step 1).")
    else:
        checked = datetime.fromisoformat(str(last["checked_at"]).replace("Z", "+00:00"))
        if _now() - _aware(checked) > CONSOLE_FRESH:
            blockers.append("The console reading is more than 30 minutes old. Read the switch again.")
        if last.get("prompt_state") == "setup-wizard":
            blockers.append("The switch already shows its new-switch setup dialog: it has no settings to erase.")
        elif last.get("prompt_state") not in {"exec", "privileged-exec", "config-mode"}:
            blockers.append(last.get("state_text") or "The switch is not at a prompt the app can work from.")
        try:
            listed = (lister or console_bridge.list_ports)()
            if not any(getattr(item, "device", None) == port for item in listed):
                blockers.append(f"{port} is no longer on this PC. Plug the console cable back in and read the switch again.")
        except (console_bridge.BridgeUnavailable, ValueError):
            blockers.append("The console helper isn't running on this PC.")
    name = device.display_name or "the switch"
    serial = _known_serial(session, device_id)
    if not serial:
        blockers.append("The app has no record of this switch's serial number (it was not set up from this app), so it cannot prove which switch is on the cable.")
    # The dialog itself switches on "switch reset only"; only the other permission problems are shown here.
    permission = [b for b in _policy_blockers() if SCOPE_BLOCKER not in b]
    return {"ready": not blockers, "blockers": blockers, "permission": permission, "name": name,
            "phrase": phrase(name), "console_port": port, "baud": baud, "model": (last or {}).get("model"),
            "serial": serial, "prompt_state": (last or {}).get("prompt_state"), "erases": ERASES}


def _run(session, device_id) -> AuditEvent | None:
    return _latest(session, "kit.switch_reset.run", device_id=device_id)


def _results(session, run_id) -> dict[str, dict]:
    rows = session.scalars(select(AuditEvent).where(AuditEvent.event_type == "kit.switch_reset.result",
                                                    AuditEvent.data_json["run_id"].as_string() == run_id)
                           .order_by(AuditEvent.created_at, AuditEvent.id))
    return {r.data_json["phase"]: r.data_json for r in rows}


def _result(session, actor, run_id, phase, outcome, message, **extra) -> bool:
    moved = session.execute(update(GuardedOperation).where(GuardedOperation.id == run_id, GuardedOperation.active_device.is_not(None),
                                                           GuardedOperation.status.in_(EXPECTED[phase]))
                            .values(status=f"rs-{outcome}-{phase}", updated_at=utcnow()))
    if moved.rowcount != 1:
        session.rollback()
        return False
    record_audit_event(session, actor=actor, event_type="kit.switch_reset.result", message=message,
                       data={"run_id": run_id, "phase": phase, "outcome": outcome, "message": message, **extra})
    session.commit()
    return True


def _heartbeat(session, run_id, step: str) -> None:
    session.execute(update(GuardedOperation).where(GuardedOperation.id == run_id, GuardedOperation.status.in_(("rs-sent-erase", "rs-ok-erase")))
                    .values(updated_at=utcnow()))
    session.commit()
    _record(session, "lab-builder", "kit.switch_reset.progress", f"Switch reset: {step}.", {"run_id": run_id, "step": step})


def _finish(session, actor, run_id, outcome, message) -> None:
    session.execute(update(GuardedOperation).where(GuardedOperation.id == run_id).values(status=outcome, active_device=None, updated_at=utcnow()))
    _record(session, actor, "kit.switch_reset.done", message, {"run_id": run_id, "outcome": outcome})


def _worker(run: dict[str, Any], enable_password: str | None, actor: str, opener=None) -> None:
    from app.providers import console_bridge
    from app.providers.cisco_console_setup import Console, SetupStopped, factory_erase, read_serial, scrub, wake_for_reset
    from app.services.runtime_write_scope import dispatch_lease

    with _session_factory()() as session:
        connection = console = None
        erased = False
        try:
            with dispatch_lease(ACTION):
                connection = (opener or console_bridge.open_port)(run["console_port"], run["baud"])
                console = Console(connection)
                _heartbeat(session, run["run_id"], "reaching the switch's prompt")
                wake_for_reset(console, enable_password)
                serial = read_serial(console)
                if not serial or serial != run["serial"]:
                    raise SetupStopped(f"The switch on {run['console_port']} is not the one this kit set up (serial {serial or 'unknown'}). Nothing was erased.", sent=False)

                def progress(step: str) -> None:
                    nonlocal erased
                    if step.startswith("restarting"):
                        erased = True
                    _heartbeat(session, run["run_id"], step)

                done = factory_erase(console, progress=progress)
        except SetupStopped as exc:
            text = scrub(str(exc), enable_password)
            sent = console.sent if console else []
            if erased and exc.sent:
                _result(session, actor, run["run_id"], "erase", "ok", "The settings were erased and the restart was sent.", sent=sent)
                _result(session, actor, run["run_id"], "restart", "uncertain", text)
            else:
                _result(session, actor, run["run_id"], "erase", "uncertain" if exc.sent else "failed", text, sent=sent)
            return
        except Exception as exc:  # noqa: BLE001 - an interrupted console session has an unknown outcome
            sent = console.sent if console else []
            outcome = "uncertain" if sent else "failed"
            _result(session, actor, run["run_id"], "erase", outcome,
                    f"The console session stopped ({type(exc).__name__})." + (" Read the switch on its console before trying again." if sent else " Nothing was sent."), sent=sent)
            return
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:  # noqa: BLE001
                    pass
        _result(session, actor, run["run_id"], "erase", "ok", "The settings and VLAN database were erased; the switch restarted without saving.", sent=done["sent"])
        if done["factory"]:
            _result(session, actor, run["run_id"], "restart", "ok", "The switch started again showing its new-switch setup dialog.")
        else:
            _result(session, actor, run["run_id"], "restart", "failed", "The switch started again but did not show its new-switch setup dialog; some settings may remain. Read it on the console.")


def start(session: Session, profile_id: str, device_id: str, actor: str, confirmation: str, *, opener=None, lister=None) -> dict[str, Any]:
    from app.services.guarded_operation_ledger import OperationConflict, reserve

    if status(session, profile_id, device_id)["active"]:
        raise SwitchResetError("A switch reset is already running.")
    plan = review(session, device_id, lister=lister)
    problems = plan["blockers"] + _policy_blockers()
    if problems:
        raise SwitchResetError(problems[0])
    if confirmation != plan["phrase"]:
        raise SwitchResetError(f"Type {plan['phrase']} exactly to erase this switch.")
    intent = {k: plan[k] for k in ("console_port", "baud", "name", "serial", "model")}
    try:
        operation = reserve(session, profile_id=profile_id, device_id=device_id, resource=RESOURCE,
                            idempotency_key=secrets.token_hex(16), actor=actor, reviewed_intent=intent)
    except OperationConflict as exc:
        raise SwitchResetError(str(exc)) from None
    run = {"run_id": operation.id, "profile_id": profile_id, "device_id": device_id, **intent}
    _record(session, actor, "kit.switch_reset.run", "Switch reset approved (typed confirmation).", run)
    claim = session.execute(update(GuardedOperation).where(GuardedOperation.id == operation.id, GuardedOperation.status == "accepted")
                            .values(status="rs-sent-erase", updated_at=utcnow()))
    if claim.rowcount != 1:
        session.rollback()
        raise SwitchResetError("This reset is already claimed. Nothing was sent again.")
    _record(session, actor, "kit.switch_reset.attempt", "Switch erase over the console starting; outcome unverified.",
            {"run_id": operation.id, "at": _now().isoformat()})
    enable = switch_access._saved(session.get(switch_access.SwitchDeviceCredential, device_id)).get("enable_password")
    worker = threading.Thread(target=_worker, args=(run, enable, actor, opener), name=f"switch-reset-{operation.id}", daemon=True)
    _workers[operation.id] = worker
    worker.start()
    return status(session, profile_id, device_id)


def advance(session: Session, profile_id: str, device_id: str, actor: str) -> dict[str, Any]:
    """Watch the console worker (stored records only); a lost worker is decided, never resent."""
    current = status(session, profile_id, device_id)
    if not current["active"]:
        return current
    run_id = current["run_id"]
    results = _results(session, run_id)
    if all(results.get(p, {}).get("outcome") == "ok" for p in PHASES):
        _finish(session, actor, run_id, "verified", f"{current['name']} is back to factory settings.")
        return status(session, profile_id, device_id)
    if current["state"] == "needs_attention":
        return current
    operation = session.get(GuardedOperation, run_id, populate_existing=True)
    worker = _workers.get(run_id)
    if (worker is None or not worker.is_alive()) and _now() - _aware(operation.updated_at) > HEARTBEAT_LIMIT:
        phase = next(p for p in PHASES if p not in results)
        _result(session, actor, run_id, phase, "uncertain",
                "The console session's end was not recorded (the app restarted). Read the switch on its console; nothing was resent.")
    return status(session, profile_id, device_id)


def close(session: Session, profile_id: str, device_id: str, actor: str) -> dict[str, Any]:
    current = status(session, profile_id, device_id)
    if not current["active"]:
        return current
    if current["state"] != "needs_attention":
        raise SwitchResetError("The reset is still running. It can be closed once it stops.")
    worker = _workers.get(current["run_id"])
    if worker is not None and worker.is_alive():
        raise SwitchResetError("The console session is still running. Wait for it to finish.")
    _finish(session, actor, current["run_id"], "failed", "Closed by the operator after a stopped step.")
    return status(session, profile_id, device_id)


LABELS = {"erase": "Erase {name}'s settings over the console ({port})", "restart": "{name} starts again as a new switch"}


def status(session: Session, profile_id: str, device_id: str) -> dict[str, Any]:
    """Stored records only; never contacts the switch."""
    row = _run(session, device_id)
    device = session.get(DeviceInventory, device_id)
    name = (device.display_name if device else None) or "the switch"
    if not row or row.data_json.get("profile_id") != profile_id:
        return {"state": "not_started", "active": False, "phases": [], "message": "", "name": name}
    run = row.data_json
    operation = session.get(GuardedOperation, run["run_id"], populate_existing=True)
    results = _results(session, run["run_id"])
    progress = _latest(session, "kit.switch_reset.progress", run_id=run["run_id"])
    done = _latest(session, "kit.switch_reset.done", run_id=run["run_id"])
    phases = []
    for phase in PHASES:
        result = results.get(phase)
        state = result["outcome"] if result else "sent" if phase == "erase" or "erase" in results else "todo"
        phases.append({"phase": phase, "label": LABELS[phase].format(name=run["name"], port=run["console_port"]),
                       "state": state, "message": result["message"] if result else None})
    base = {"run_id": run["run_id"], "phases": phases, "name": run["name"], "console_port": run["console_port"],
            "step": progress.data_json.get("step") if progress and len(results) < len(PHASES) else None,
            "active": bool(operation and operation.active_device)}
    if done:
        return {**base, "state": "verified" if done.data_json["outcome"] == "verified" else "failed", "message": done.message}
    problem = next((p for p in phases if p["state"] in {"failed", "uncertain"}), None)
    if problem:
        return {**base, "state": "needs_attention", "message": problem["message"]}
    return {**base, "state": "running", "message": "Erasing the switch…" if "erase" not in results else "Waiting for the switch to start again…"}
