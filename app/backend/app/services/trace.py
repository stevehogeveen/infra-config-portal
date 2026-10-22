"""Trace the path: Windows VM -> VM network -> ESXi -> server port -> cable -> switch port -> gateway.

Stored records only (no equipment contact). Each hop says whether it is proven by a check the app
ran (with when), only planned/saved, or unknown; the first hop that is not proven is where the
evidence stops, and the page says what would prove it.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session


def _hop(name: str, detail: str | None, state: str, source: str, at: str | None = None, prove: str | None = None) -> dict[str, Any]:
    return {"name": name, "detail": detail, "state": state, "source": source, "at": at, "prove": prove}


def _cable_for(cables: list[dict[str, Any]], device_id: str, nic: str | None) -> dict[str, Any] | None:
    mine = [cable for cable in cables if cable.get("server_id") == device_id]
    if nic:
        nic = nic.lower()
        exact = [c for c in mine if c.get("mac") == nic or str(c.get("server_port") or "").lower().startswith(nic + " ")]
        if exact:
            return exact[0]
    return None


def server_path(session: Session, profile_id: str, device_id: str, name: str, cables: dict[str, Any] | None,
                switch_names: dict[str, str]) -> dict[str, Any]:
    from app.services import acceptance, esxi_install, switch_access, windows_deploy

    windows = windows_deploy.status(session, profile_id, device_id)
    esxi = esxi_install.install_status(session, profile_id, device_id)
    settings = esxi_install.get_settings(session, profile_id, device_id)
    test = acceptance.status(session, profile_id, device_id)
    nic = settings.get("management_nic") or "vmnic0"
    hops = []
    if windows.get("state") == "verified":
        hops.append(_hop("Windows VM", f"{windows.get('vm_name')} at {windows.get('address')}", "proven", "VMware Tools reported its address"))
        hops.append(_hop("VM network", windows.get("network"), "saved", "Deploy settings",
                         prove="Run the acceptance test: Windows pinging its gateway proves the VM network."))
    else:
        hops.append(_hop("Windows VM", windows.get("vm_name"), "unknown", "Not deployed yet", prove="Deploy Windows (Install Windows)."))
    if esxi.get("state") == "verified":
        hops.append(_hop("ESXi host", f"{settings.get('hostname') or 'ESXi'} at {esxi.get('management_ip')}", "proven", "ESXi answered after its install", esxi.get("verified_at")))
    else:
        hops.append(_hop("ESXi host", esxi.get("management_ip"), "unknown", "Not installed yet", prove="Install ESXi (Prepare ESXi)."))
    # A kit uses one cabled port for ESXi management and VM traffic; a VM on another uplink is not traced.
    hops.append(_hop("Server port", nic, "saved", "ESXi management port (VM traffic assumed to share it)",
                     prove="Read the cables (My Rack, Cables) to see which switch port it reaches."))
    cable = _cable_for((cables or {}).get("cables") or [], device_id, nic)
    if cable:
        hops[-1] = _hop("Server port", cable.get("server_port"), "proven", "Cable map", (cables or {}).get("checked_at"))
        hops.append(_hop("Cable", f"{cable.get('server_port')} to {cable.get('switch')} {cable.get('switch_port')}", "proven",
                         "Switch MAC table matched the server's port", (cables or {}).get("checked_at")))
        last = switch_access.read_access(session, cable["switch_id"]).get("last_check") or {}
        hops.append(_hop("Switch port", f"{cable.get('switch')} {cable.get('switch_port')}, VLAN {cable.get('vlan')}",
                         "proven" if last.get("status") == "ok" else "saved", "Switch check over SSH" if last.get("status") == "ok" else "Cable map",
                         last.get("checked_at") or (cables or {}).get("checked_at")))
    else:
        hops.append(_hop("Cable", None, "unknown", "Not read",
                         prove="Read the cables (My Rack, Cables). The switch must be set up and traffic must have flowed."))
        hops.append(_hop("Switch port", None, "unknown", "Not read"))
    # Proof from the acceptance test counts only for this VM and only if it ran after this deployment.
    current_test = (test.get("vm") == windows.get("vm_name") and test.get("started_at") and windows.get("started_at")
                    and str(test["started_at"]) >= str(windows["started_at"]))
    gateway = next((check for phase in test.get("phases", []) for check in phase.get("checks", [])
                    if str(check.get("name", "")).startswith("Windows reaches the gateway")), None) if current_test else None
    if gateway and gateway.get("ok"):
        hops.append(_hop("Gateway", gateway["name"].removeprefix("Windows reaches the gateway "), "proven", "Acceptance test: Windows pinged it", test.get("finished_at") or test.get("started_at")))
        for hop in hops:
            if hop["name"] == "VM network" and hop["state"] == "saved":
                hop.update(state="proven", source="Acceptance test: traffic left the VM", at=test.get("finished_at") or test.get("started_at"), prove=None)
    else:
        kit = settings.get("kit") or {}
        hops.append(_hop("Gateway", kit.get("gateway"), "saved" if kit.get("gateway") else "unknown", "Kit network settings",
                         prove="Run the acceptance test (Install Windows, step 4)."))
    stop = next((index for index, hop in enumerate(hops) if hop["state"] != "proven"), None)
    return {"device_id": device_id, "name": name, "hops": hops, "stops_at": stop}


def build(session: Session, profile_id: str) -> dict[str, Any]:
    from app.api.rack_plans import get_plan
    from app.services import cable_map

    plan = get_plan(profile_id, session)
    cables = cable_map.last(profile_id)
    switch_names = {item.device_id: item.name for item in plan.equipment if item.kind == "switch" and item.device_id}
    return {"servers": [server_path(session, profile_id, item.device_id, item.name, cables, switch_names)
                        for item in plan.equipment if item.kind == "server" and item.device_id],
            "cables_read_at": (cables or {}).get("checked_at")}
