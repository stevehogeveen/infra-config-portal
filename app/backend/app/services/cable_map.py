"""Cable map: which server port is plugged into which switch port.

Read-only, on an explicit click: the iLO lists every server network port with its MAC address
(and the iLO's own port); the switch's address table (show mac address-table) says which switch
port has seen each MAC. Matching the two gives "server port -> switch port". A port seen only
after traffic flows; an idle port is reported as unknown, never guessed.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

PROVIDER = "cable-map"
MAC_ROW = re.compile(r"^\s*(\d+|All)\s+([0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4})\s+\S+\s+(\S+)", re.M)
STATUS_ROW = re.compile(r"^(\S+)\s.*?\b(connected|notconnect|disabled|err-disabled)\b\s+(\S+)", re.M)


def _mac(value: str) -> str:
    digits = re.sub(r"[^0-9a-f]", "", value.lower())
    return ":".join(digits[i:i + 2] for i in range(0, 12, 2)) if len(digits) == 12 else ""


def parse_mac_table(text: str) -> dict[str, dict[str, str]]:
    """MAC -> {port, vlan} from 'show mac address-table' (CPU and port-channel rows skipped)."""
    out: dict[str, dict[str, str]] = {}
    for vlan, mac, port in MAC_ROW.findall(text):
        if port.upper() == "CPU" or port.lower().startswith("po"):
            continue
        out[_mac(mac)] = {"port": port, "vlan": vlan}
    return out


def parse_status(text: str) -> dict[str, dict[str, str]]:
    """port -> {state, vlan} from 'show interfaces status'."""
    return {port: {"state": state, "vlan": vlan} for port, state, vlan in STATUS_ROW.findall(text) if re.search(r"\d", port)}


def _server_ports(session: Session, device_id: str) -> list[dict[str, Any]]:
    from app.services import esxi_boot_workflow as boot
    from app.services import esxi_install

    ports = esxi_install._network_ports(session, device_id) or []
    rows = [{"mac": port["mac"], "label": esxi_install._port_label(port), "link": port.get("link")} for port in ports]
    try:
        config = esxi_install._config(session, device_id)
        ilo = boot._body(boot._get_redfish_resource("/redfish/v1/Managers/1/EthernetInterfaces/1/", config=config))
        mac = _mac(str(ilo.get("MACAddress") or ""))
        if mac:
            rows.append({"mac": mac, "label": "iLO port", "link": None})
    except Exception:  # noqa: BLE001 - the iLO's own port is optional in the map
        pass
    return rows


def build(servers: dict[str, list[dict[str, Any]]], switches: dict[str, dict[str, str]], names: dict[str, str]) -> dict[str, Any]:
    """servers: device -> ports; switches: device -> raw outputs. Pure; tested directly."""
    cables, unknown_ports, idle = [], [], []
    learned: dict[str, list[tuple[str, dict[str, str]]]] = {}
    status: dict[str, dict[str, dict[str, str]]] = {}
    for switch_id, outputs in switches.items():
        for mac, row in parse_mac_table(outputs.get("show mac address-table", "")).items():
            learned.setdefault(mac, []).append((switch_id, row))
        status[switch_id] = parse_status(outputs.get("show interfaces status", ""))
    matched_ports: set[tuple[str, str]] = set()
    for server_id, ports in servers.items():
        for port in ports:
            seen = learned.get(port["mac"]) or []
            if len(seen) > 1:
                idle.append({"server": names.get(server_id, "server"), "server_port": port["label"],
                             "note": "Seen on more than one switch (" + ", ".join(f"{names.get(s, 'switch')} {r['port']}" for s, r in seen) + "); the direct cable is unclear."})
                continue
            if seen:
                switch_id, row = seen[0]
                matched_ports.add((switch_id, row["port"]))
                cables.append({"server_id": server_id, "server": names.get(server_id, "server"), "server_port": port["label"], "mac": port["mac"],
                               "switch_id": switch_id, "switch": names.get(switch_id, "switch"), "switch_port": row["port"], "vlan": row["vlan"]})
            elif port.get("link"):
                idle.append({"server": names.get(server_id, "server"), "server_port": port["label"],
                             "note": "Cable connected, but this switch has not seen it (another switch, or no traffic yet)."})
    for switch_id, ports in status.items():
        for port, row in ports.items():
            if row["state"] == "connected" and (switch_id, port) not in matched_ports:
                unknown_ports.append({"switch": names.get(switch_id, "switch"), "switch_port": port, "vlan": row["vlan"],
                                      "note": "Something is plugged in here that is not a server in this kit (often the uplink)."})
    return {"cables": cables, "unmatched_server_ports": idle, "other_switch_ports": unknown_ports}


def read(session: Session, profile_id: str, *, ssh=None, server_ports=None) -> dict[str, Any]:
    from app.api.rack_plans import get_plan
    from app.core.config import settings
    from app.providers.action_policy import REAL_CONTACT_MODES, current_lab_action_policy
    from app.providers.probe_cache import record_probe_result
    from app.services import switch_access

    if settings.provider_mode not in REAL_CONTACT_MODES or not current_lab_action_policy(settings.provider_mode).readonly_allowed:
        return {"state": "blocked", "message": "The app is not allowed to contact real equipment in this mode.", "cables": []}
    plan = get_plan(profile_id, session)
    names = {item.device_id: item.name for item in plan.equipment if item.device_id}
    servers = {item.device_id: (server_ports or _server_ports)(session, item.device_id)
               for item in plan.equipment if item.kind == "server" and item.device_id}
    switches, problems = {}, []
    for item in plan.equipment:
        if item.kind != "switch" or not item.device_id:
            continue
        saved = switch_access._saved(session.get(switch_access.SwitchDeviceCredential, item.device_id))
        if not saved.get("host") or not saved.get("password"):
            problems.append(f"{item.name} is not set up yet, so its ports cannot be read.")
            continue
        try:
            switches[item.device_id] = (ssh or switch_access._ssh_outputs)(
                saved["host"], saved["username"], saved["password"], 15.0,
                ("terminal length 0", "show mac address-table", "show interfaces status"))
        except Exception as exc:  # noqa: BLE001 - reported, never retried
            problems.append(f"{item.name} did not answer over SSH ({exc.__class__.__name__}).")
    result = {"state": "ok" if switches else "blocked", "checked_at": datetime.now(UTC).isoformat(), "problems": problems,
              **build(servers, switches, names)}
    record_probe_result(PROVIDER, result, scope=profile_id)
    return result


def last(profile_id: str) -> dict[str, Any] | None:
    from app.providers.probe_cache import get_probe_result

    value, _ = get_probe_result(PROVIDER, scope=profile_id)
    return value if isinstance(value, dict) else None
