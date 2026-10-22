"""Plain-words help for the common stops: what to check, in order, before pressing Try again.
Matched on the stop message; nothing here sends anything."""

from __future__ import annotations

import re

ADVICE: list[tuple[re.Pattern, str, list[str]]] = [
    (re.compile(r"no address from DHCP|has no address", re.I), "The switch got no DHCP address.", [
        "Is a cable from the lab network (the one with the DHCP server) in one of the switch's ports? With VLAN 1, any port.",
        "Does that port show a link light on both ends?",
        "If the management VLAN is not 1, the port it plugs into must carry that VLAN, and a DHCP server must answer there.",
        "The settings are saved on the switch; Try again reads the address again without resending them."]),
    (re.compile(r"VMware Tools|Windows (has no|is not reachable)|did not answer after the restart|no guest address", re.I), "Windows has no usable address yet.", [
        "Give it time: Windows can take several minutes after power-on before VMware Tools reports an address.",
        "In the ESXi host client, open the VM's console: is Windows at the sign-in screen, or still setting up?",
        "Is the VM on the right port group (the one with DHCP), and is that port group's uplink cabled?",
        "An address starting 169.254 means no DHCP answer reached the VM.",
        "Try again only re-checks; nothing is redeployed."]),
    (re.compile(r"refused the saved administrator sign-in|sign-in failed|sign_in_failed", re.I), "The sign-in was refused.", [
        "Re-enter the password on Install Windows, step 4 (or Connect for the switch), then Try again.",
        "For a fresh Windows image, the administrator password may be the image's default until first sign-in."]),
    (re.compile(r"iLO did not answer|the iLO did not answer|could not be read|Nothing answered", re.I), "The iLO did not answer.", [
        "Is this PC's wired port linked (its own light on), and on the same network as the iLO?",
        "Is the server's iLO port (the dedicated one, not the data NICs) cabled and lit?",
        "The iLO's address comes from DHCP and can move: use Find it on the network to look for it again.",
        "Power: the iLO answers whenever the server has mains, even when the server is off."]),
    (re.compile(r"console|COM\d", re.I), "The console cable did not answer.", [
        "Is the blue console cable in the switch's CONSOLE port (not a network port) and in this PC's USB?",
        "Pick the COM port that appears when you plug the cable in; it is usually the one marked (console cable).",
        "Is the console helper running (start-lab-builder.cmd starts it)?",
        "Nobody else may have the COM port open (a terminal program, for example)."]),
    (re.compile(r"already has RAID volumes|existing volumes", re.I), "The disks already hold RAID volumes.", [
        "Kit Pilot never deletes volumes. If they are not needed, wipe them on Disks & RAID (a guarded, typed step).",
        "If they are the ones you want, the RAID leg is already done; Try again will skip it."]),
    (re.compile(r"ESXi answers but|reachable", re.I), "ESXi answers but is not verified yet.", [
        "Open Prepare ESXi and finish the check there; it signs in as root and proves the host name, address and boot disk.",
        "With DHCP, the address may differ from the plan; Kit Pilot finds it by the management port's MAC."]),
    (re.compile(r"not come back|restart", re.I), "A restart did not finish.", [
        "Open the device's console (iLO remote console, or ESXi's VM console) and look at the screen.",
        "Nothing was sent twice; Try again reads again and continues from where it stopped."]),
]


def advice(message: str) -> dict | None:
    """{'title', 'steps'} for a known kind of stop, else None."""
    for pattern, title, steps in ADVICE:
        if pattern.search(message or ""):
            return {"title": title, "steps": steps}
    return None
