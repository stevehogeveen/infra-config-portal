"""Per-switch sign-in for the Connect step: the address the switch answers SSH on, its sign-in,
and a read-only check that reads its identity (show version, show inventory, show interfaces
status). The check never enters configuration mode and never keeps raw output; only parsed facts
(hostname, model, software version, serial, port count) are returned and cached."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import DeviceInventory, SwitchDeviceCredential
from app.providers.action_policy import REAL_CONTACT_MODES, current_lab_action_policy
from app.providers.cisco_ansible import SSH_PORT, _ios_xe_version, _read_paramiko_channel, _tcp_connect
from app.providers.probe_cache import get_probe_result, record_probe_result

PROVIDER_ID = "cisco-switch"
CHECK_COMMANDS = ("terminal length 0", "show version", "show inventory", "show interfaces status")


class SwitchAccessError(ValueError):
    pass


class SwitchNotFoundError(LookupError):
    pass


def is_switch_type(device_type: str | None) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", (device_type or "").casefold()).split("_")
    return "switch" in normalized or "cisco" in normalized


def require_switch(session: Session, device_id: str) -> DeviceInventory:
    device = session.get(DeviceInventory, device_id)
    if device is None:
        raise SwitchNotFoundError(device_id)
    if not is_switch_type(device.device_type):
        raise SwitchAccessError("The selected equipment is not a switch.")
    return device


def read_access(session: Session, device_id: str) -> dict[str, Any]:
    device = require_switch(session, device_id)
    record = session.get(SwitchDeviceCredential, device_id)
    saved = _saved(record)
    host = saved.get("host") or _clean(device.host)
    last, checked_at = get_probe_result(PROVIDER_ID, scope=device_id)
    current = isinstance(last, dict) and last.get("host") == host and last.get("username") == saved.get("username")
    return {
        "device_id": device_id,
        "host": host,
        "username": saved.get("username"),
        "username_configured": bool(saved.get("username")),
        "password_configured": bool(saved.get("password")),
        "enable_password_configured": bool(saved.get("enable_password")),
        "updated_at": record.updated_at.isoformat() if record is not None and record.updated_at else None,
        # The last answer counts only for the saved address and sign-in it was read with.
        "last_check": {**_public(last), "checked_at": checked_at} if current else None,
        "console": {"port": saved.get("console_port"), "baud": _int(saved.get("console_baud")), "last": console_last(device_id)},
    }


def save_access(session: Session, device_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    device = require_switch(session, device_id)
    record = session.get(SwitchDeviceCredential, device_id)
    saved = _saved(record)
    updates = {field: value for field in ("host", "username", "password", "enable_password")
               if field in payload and (value := _clean(payload.get(field)))}
    if not updates:
        raise SwitchAccessError("Enter the switch address and sign-in.")
    merged = {**saved, **updates}
    if record is None:
        session.add(SwitchDeviceCredential(device_id=device_id, credentials_json=merged))
    else:
        record.credentials_json = merged
    if "host" in updates:
        device.host = updates["host"]
    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise SwitchAccessError("Could not save the switch sign-in locally.") from None
    return read_access(session, device_id)


def check(session: Session, device_id: str, *, connect=None) -> dict[str, Any]:
    """Read-only identity check over SSH with fixed show commands."""
    require_switch(session, device_id)
    saved = _saved(session.get(SwitchDeviceCredential, device_id))
    host, username, password = saved.get("host"), saved.get("username"), saved.get("password")
    if not host or not username or not password:
        raise SwitchAccessError("Save the switch address, username and password first.")
    mode = settings.provider_mode
    if mode not in REAL_CONTACT_MODES:
        return _record(device_id, host, username, "blocked", "The app is in practice mode, so it does not contact real equipment.")
    if not current_lab_action_policy(mode).readonly_allowed:
        return _record(device_id, host, username, "blocked", "The lab safety acknowledgements needed for read-only checks are not set.")
    timeout = float(settings.ansible_cisco_timeout_seconds or 10)
    reach = _tcp_connect(host, SSH_PORT, timeout)
    if not reach["reachable"]:
        return _record(device_id, host, username, "unreachable",
                       f"Nothing answered SSH at {host}. A new switch needs its management address and SSH set up "
                       "from the console cable first; check the address and that the switch's management port is cabled.")
    try:
        outputs = (connect or _ssh_outputs)(host, username, password, timeout)
    except _SignInRefused:
        return _record(device_id, host, username, "sign_in_failed", f"The switch at {host} refused the username or password.")
    except Exception as exc:  # noqa: BLE001 - the reason is reported, never the output
        return _record(device_id, host, username, "failed", f"The SSH session to {host} stopped: {exc.__class__.__name__}.")
    facts = parse_identity(outputs)
    if not facts.get("version") and not facts.get("model"):
        return _record(device_id, host, username, "failed",
                       f"{host} accepted the sign-in but did not answer like a Cisco switch.", facts)
    name = facts.get("hostname") or host
    return _record(device_id, host, username, "ok",
                   f"{name} answered: {facts.get('model') or 'Cisco switch'}, software {facts.get('version') or 'unknown'}.", facts)


class _SignInRefused(Exception):
    pass


def _ssh_outputs(host: str, username: str, password: str, timeout: float, commands: tuple[str, ...] = CHECK_COMMANDS) -> dict[str, str]:
    """Sign in over SSH and run fixed read-only show commands; returns each command's output."""
    import paramiko  # type: ignore[import-untyped]

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        try:
            client.connect(hostname=host, port=SSH_PORT, username=username, password=password, look_for_keys=False,
                           allow_agent=False, timeout=timeout, auth_timeout=timeout, banner_timeout=timeout)
        except paramiko.AuthenticationException:
            raise _SignInRefused() from None
        channel = client.invoke_shell(width=200, height=80)
        outputs = {"banner": _read_paramiko_channel(channel, seconds=1.5)}
        for command in commands:
            if not command.startswith(("show ", "terminal length ")):
                raise ValueError("Only fixed read-only commands are sent.")
            channel.send(command + "\n")
            outputs[command] = _read_paramiko_channel(channel, seconds=max(timeout, 3.0))
        return outputs
    finally:
        client.close()


def parse_identity(outputs: dict[str, str]) -> dict[str, Any]:
    version_text = outputs.get("show version", "")
    inventory = outputs.get("show inventory", "")
    every = "\n".join(outputs.values())
    prompt = re.findall(r"(?m)^([A-Za-z0-9][\w.-]{0,62})[>#]\s*(?:\S.*)?$", every)
    model = (_first(r"Model [Nn]umber\s*:\s*(\S+)", version_text)
             or _first(r'PID:\s*(\S+?)\s*,', inventory)
             or _first(r"cisco\s+(\S+)\s+\(.*\)\s+processor", version_text))
    serial = (_first(r"System [Ss]erial [Nn]umber\s*:\s*(\S+)", version_text)
              or _first(r"SN:\s*(\S+)", inventory)
              or _first(r"Processor board ID\s+(\S+)", version_text))
    ports = re.findall(r"(?m)^\s*((?:Gi|Te|Fa|Tw|Fo|Hu|Eth)\S*\d)\s", outputs.get("show interfaces status", ""))
    uptime = _first(r"uptime is ([^\n]+)", version_text)
    return {
        "hostname": prompt[-1] if prompt else _first(r"(?m)^(\S+) uptime is", version_text),
        "model": model,
        "version": _ios_xe_version(version_text) if version_text else None,
        "serial": serial,
        "port_count": len(set(ports)) or None,
        "uptime": uptime.strip() if uptime else None,
    }


def _first(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None


def _record(device_id: str, host: str, username: str, status: str, message: str, facts: dict[str, Any] | None = None) -> dict[str, Any]:
    result = {"status": status, "message": message, "host": host, "username": username, **(facts or {}),
              "checked_at": datetime.now(timezone.utc).isoformat()}
    record_probe_result(PROVIDER_ID, result, scope=device_id)
    return _public(result) | {"checked_at": result["checked_at"]}


def _public(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    keys = ("status", "message", "host", "hostname", "model", "version", "serial", "port_count", "uptime")
    return {key: result.get(key) for key in keys}


def _saved(record: SwitchDeviceCredential | None) -> dict[str, Any]:
    if record is None or not isinstance(record.credentials_json, dict):
        return {}
    # Text values are trimmed; structured ones (the first-setup settings) are kept as they are.
    return {key: _clean(value) if isinstance(value, str) or value is None else value
            for key, value in record.credentials_json.items()}


def _clean(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


# Console cable: the first contact with a new switch. The PC's COM ports are listed through the
# console helper (scripts/console-bridge.ps1); the operator picks one and the app reads the switch
# through it with the fixed read-only identity check (a blank Enter, then show version).

CONSOLE_PROVIDER = "cisco-switch-console"
CONSOLE_BAUDS = (9600, 115200)
PROMPT_TEXT = {
    "exec": "The switch is at its normal prompt.",
    "privileged-exec": "The switch is at its enable (#) prompt.",
    "setup-wizard": "The switch is new: it is waiting at its first-setup questions. The app sets it up from here.",
    "login-required": "The switch asks for a console username and password, so it has been set up before.",
    "config-mode": "The switch is in configuration mode; someone left it mid-change. Nothing was sent.",
    "rommon-bootloader": "The switch is in its boot loader (ROMMON), not running its software.",
}


def console_ports(session: Session, device_id: str, *, lister=None) -> dict[str, Any]:
    from app.providers import console_bridge
    from app.services.cisco_console_identity import list_cisco_console_identity_candidates

    require_switch(session, device_id)
    saved = _saved(session.get(SwitchDeviceCredential, device_id))
    try:
        ports = (lister or console_bridge.list_ports)()
    except (console_bridge.BridgeUnavailable, ValueError) as exc:
        return {"helper_running": False, "ports": [], "saved_port": saved.get("console_port"),
                "saved_baud": _int(saved.get("console_baud")),
                "problem": "The console helper isn't running on this PC. Start it with "
                           "start-lab-builder.cmd (or start-console-bridge.cmd), then refresh.",
                "detail": exc.__class__.__name__}
    listed = list_cisco_console_identity_candidates(port_enumerator=lambda: ports)
    by_port = {getattr(item, "device", None): item for item in ports}
    out = []
    for candidate in listed["candidates"]:
        raw = by_port.get(candidate["port"])
        usb = candidate.get("transport") == "usb-serial"
        out.append({**candidate, "usb": usb,
                    "hint": "USB console cable" if usb else "Built into this PC, not a console cable",
                    "raw_present": raw is not None})
    # Recommend the USB adapter when it is the only one.
    usb_ports = [item for item in out if item["usb"]]
    if len(usb_ports) == 1:
        usb_ports[0]["recommended"] = True
    return {"helper_running": True, "ports": out, "bauds": list(CONSOLE_BAUDS),
            "saved_port": saved.get("console_port"), "saved_baud": _int(saved.get("console_baud")),
            "problem": None if out else "No COM ports are present. Plug in the USB console cable, then refresh."}


def console_identify(session: Session, device_id: str, port: str, baud: int, fingerprint: str, *, lister=None, opener=None) -> dict[str, Any]:
    from app.providers import console_bridge
    from app.services.cisco_console_identity import verify_cisco_console_identity

    require_switch(session, device_id)
    if baud not in CONSOLE_BAUDS:
        raise SwitchAccessError("Choose 9600 or 115200.")
    try:
        result = verify_cisco_console_identity(port=port, baud=baud, candidate_fingerprint=fingerprint,
                                               port_enumerator=lister or console_bridge.list_ports,
                                               connection_opener=opener or console_bridge.open_port)
    except console_bridge.BridgeUnavailable:
        raise SwitchAccessError("The console helper isn't running on this PC.") from None
    state = result.get("prompt_state") or "unknown"
    answered = bool(result.get("identity_verified")) or state in PROMPT_TEXT
    summary = {
        "port": port, "baud": baud, "answered": answered,
        "identity_verified": bool(result.get("identity_verified")),
        "prompt_state": state,
        "state_text": PROMPT_TEXT.get(state),
        "model": result.get("model"), "version": result.get("software_version"),
        "message": result.get("message"),
        "checked_at": result.get("checked_at") or datetime.now(timezone.utc).isoformat(),
    }
    if not answered:
        summary["message"] = (f"Nothing that looks like a Cisco console answered on {port} at {baud}. "
                              "Check the cable is in the switch's CONSOLE port, or try the other speed.")
        summary["detail"] = result.get("message")
    record_probe_result(CONSOLE_PROVIDER, summary, scope=device_id)
    if answered:
        _remember_console(session, device_id, port, baud)
    return summary


def console_last(device_id: str) -> dict[str, Any] | None:
    last, _ = get_probe_result(CONSOLE_PROVIDER, scope=device_id)
    return last if isinstance(last, dict) else None


def _remember_console(session: Session, device_id: str, port: str, baud: int) -> None:
    record = session.get(SwitchDeviceCredential, device_id)
    merged = {**_saved(record), "console_port": port, "console_baud": str(baud)}
    if record is None:
        session.add(SwitchDeviceCredential(device_id=device_id, credentials_json=merged))
    else:
        record.credentials_json = merged
    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def console_address(session: Session, device_id: str, *, opener=None) -> dict[str, Any]:
    """Read-only: over the console cable, read which addresses the switch has (for DHCP).

    Sends one Enter, and at a normal prompt only "show ip interface brief | exclude unassigned".
    It never answers the new-switch setup dialog, a login or a confirmation.
    """
    from app.providers import console_bridge
    from app.providers.cisco_console_setup import ENTRY, Console, PRIV, EXEC
    from app.services.cisco_console_identity import _readonly_contact_blockers

    require_switch(session, device_id)
    saved = _saved(session.get(SwitchDeviceCredential, device_id))
    port, baud = saved.get("console_port"), _int(saved.get("console_baud"))
    if not port or not baud:
        raise SwitchAccessError("Read the switch on its console cable first (step 1), so the app knows which COM port it is on.")
    blockers = _readonly_contact_blockers(settings.provider_mode)
    if blockers:
        raise SwitchAccessError(blockers[0])
    try:
        connection = (opener or console_bridge.open_port)(port, baud)
    except console_bridge.BridgeUnavailable:
        raise SwitchAccessError("The console helper isn't running on this PC.") from None
    except OSError as exc:
        raise SwitchAccessError(f"{port} could not be opened: {exc}") from None
    try:
        console = Console(connection)
        console.send("\r")
        state, _ = console.expect(ENTRY, timeout=15)
        if state == "press_return":
            console.send("\r")
            state, _ = console.expect(ENTRY, timeout=15)
        if state not in {"exec", "priv"}:
            text = {
                "wizard": "The switch is new and has no address yet. Run First setup (step 2).",
                "autoinstall": "The switch is new and has no address yet. Run First setup (step 2).",
                "login": "The switch asks for a console login, so its address can't be read over the console.",
                "config": "The switch is sitting in configuration mode; nothing was sent.",
                "rommon": "The switch is in its boot loader (ROMMON), not running its software.",
            }.get(state, f"The switch did not answer on {port}.")
            return {"state": state, "message": text, "addresses": [], "address": None}
        console.send("show ip interface brief | exclude unassigned\r")
        _, output = console.expect({"priv": PRIV, "exec": EXEC}, timeout=20)
    finally:
        try:
            connection.close()
        except Exception:  # noqa: BLE001
            pass
    addresses = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 2 and re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", parts[1]) and not parts[0].lower().startswith("interface"):
            addresses.append({"interface": parts[0], "address": parts[1], "method": parts[3] if len(parts) > 3 else None,
                              "status": " ".join(parts[4:-1]) if len(parts) > 5 else (parts[4] if len(parts) > 4 else None)})
    setup = saved.get("setup") if isinstance(saved.get("setup"), dict) else {}
    vlan = f"vlan{int(setup.get('vlan') or 1)}"
    chosen = (next((a for a in addresses if a["interface"].lower() == vlan), None)
              or next((a for a in addresses if a["interface"].lower().startswith("vlan")), None)
              or (addresses[0] if addresses else None))
    if chosen:
        save_access(session, device_id, {"host": chosen["address"]})
        message = f"The switch has {chosen['address']} on {chosen['interface']}" + (" (from DHCP)." if (chosen.get("method") or "").upper() == "DHCP" else ".")
    else:
        message = "The switch has no address yet. If it uses DHCP, check its network cable is on a port in the management VLAN and a DHCP server answers there."
    result = {"state": "ok", "message": message, "addresses": addresses, "address": chosen["address"] if chosen else None,
              "checked_at": datetime.now(timezone.utc).isoformat()}
    record_probe_result("cisco-switch-console-address", result, scope=device_id)
    return result
