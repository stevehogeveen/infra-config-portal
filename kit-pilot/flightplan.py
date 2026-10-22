"""The flight plan: Kit Pilot's setup page, saved into Lab Builder's own settings.

Everything the build needs is entered on one page and stored where Lab Builder's runs read it:
the kit (network), the equipment (rack plan), the server's iLO sign-in, the switch (console port,
first-setup settings, admin sign-in), ESXi (settings + ISO) and Windows (image, VM, test sign-in).
Passwords pass through to Lab Builder once; Kit Pilot never stores or returns them.
"""

from __future__ import annotations

import ipaddress
import re
import urllib.parse
from typing import Any

from engine import Api, ApiError

PROFILE_FIELDS = ("name", "description", "profile_topology", "subnet_cidr", "gateway", "vlan_id", "dns", "ntp", "mtu", "devices", "features", "global_settings", "address_plan")
HOSTNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{1,252}$")


class PlanError(Exception):
    pass


def _ip(value: str, what: str) -> str:
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        raise PlanError(f"{what} must be an IP address.") from None


def _q(path: str, device: str | None = None) -> str:
    return path + (f"?device_id={urllib.parse.quote(device)}" if device else "")


class FlightPlan:
    def __init__(self, api: Api) -> None:
        self.api = api

    # ------------------------------------------------------------- reading
    def active(self) -> dict[str, Any] | None:
        return (self.api.get("/api/v1/lab/profiles") or {}).get("active_profile") or None

    def _equipment(self, profile_id: str) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
        plan = self.api.get(f"/api/v1/rack-plans/{urllib.parse.quote(profile_id)}")
        server = next((e for e in plan["equipment"] if e["kind"] == "server"), None)
        switch = next((e for e in plan["equipment"] if e["kind"] == "switch"), None)
        return plan, server, switch

    def read(self) -> dict[str, Any]:
        """The whole plan as it stands; never a password, never an equipment contact."""
        profile = self.active()
        if not profile:
            return {"kit": {}, "server": {}, "switch": {}}
        p = profile["id"]
        settings = profile.get("global_settings") or {}
        kit = {"id": p, "name": profile.get("name"), "subnet": profile.get("subnet_cidr"), "gateway": profile.get("gateway") or settings.get("gateway"),
               "dns": profile.get("dns") or settings.get("dns_servers") or [], "domain": settings.get("domain_name")}
        _, server, switch = self._equipment(p)
        out: dict[str, Any] = {"kit": kit, "server": {}, "switch": {}}
        if server and server.get("device_id"):
            d = server["device_id"]
            s: dict[str, Any] = {"id": d, "name": server["name"], "model": server.get("model")}
            try:
                access = self.api.get(_q("/api/v1/providers/ilo-redfish/access-settings", d))
                s["ilo"] = {"host": access.get("host"), "username": access.get("username"), "password_configured": access.get("password_configured"),
                            "probe_ok": access.get("last_probe_status") == "ok" and access.get("last_probe_is_current"), "model": None}
            except ApiError:
                s["ilo"] = {}
            try:
                esxi = self.api.get(_q(f"/api/v1/rack-plans/{p}/esxi/settings", d))
                media = self.api.get(_q(f"/api/v1/rack-plans/{p}/esxi/media", d))
                s["esxi"] = {k: esxi.get(k) for k in ("hostname", "addressing", "management_ip", "vlan_id", "management_nic", "datastore_name", "saved_at", "password_set")}
                s["esxi"]["isos"] = [{"path": i["path"], "name": i["name"]} for i in media.get("isos", [])]
                s["esxi"]["selected_iso"] = (media.get("selected") or {}).get("path")
            except ApiError as exc:
                s["esxi"] = {"problem": str(exc)}
            try:
                win = self.api.get(_q(f"/api/v1/rack-plans/{p}/windows/setup", d) + "&host=false")  # records only; never asks ESXi
                signin = self.api.get(_q(f"/api/v1/rack-plans/{p}/windows/guest-signin", d))
                s["windows"] = {"images": [{"path": i["path"], "name": i["name"]} for i in win.get("images", []) if not i.get("missing")], "image": win.get("image"),
                                "vm_name": win.get("vm_name"), "datastore": win.get("datastore"), "network": win.get("network"), "saved_at": win.get("saved_at"),
                                "host": win.get("host"), "signin": {"username": signin.get("username"), "password_saved": signin.get("password_saved")}}
            except ApiError as exc:
                s["windows"] = {"problem": str(exc)}
            out["server"] = s
        if switch and switch.get("device_id"):
            d = switch["device_id"]
            w: dict[str, Any] = {"id": d, "name": switch["name"], "ports": switch.get("ports")}
            try:
                access = self.api.get(f"/api/v1/devices/{d}/switch-access")
                w.update(username=access.get("username"), password_configured=access.get("password_configured"), host=access.get("host"),
                         console_port=(access.get("console") or {}).get("port"), console_last=(access.get("console") or {}).get("last"))
                ports = self.api.get(f"/api/v1/devices/{d}/switch-console/ports")
                w["console_ports"] = ports.get("ports", [])
                w["console_problem"] = ports.get("problem")
                setup = self.api.get(_q(f"/api/v1/rack-plans/{p}/switch-setup/setup", d))
                w["setup"] = setup.get("settings") or {}
                w["default_hostname"] = (setup.get("defaults") or {}).get("hostname")
            except ApiError as exc:
                w["problem"] = str(exc)
            out["switch"] = w
        return out

    # ------------------------------------------------------------- saving
    def save(self, section: str, values: dict[str, Any]) -> dict[str, Any]:
        handler = {"kit": self.save_kit, "equipment": self.save_equipment, "ilo": self.save_ilo, "switch": self.save_switch, "esxi": self.save_esxi, "windows": self.save_windows}.get(section)
        if not handler:
            raise PlanError("Unknown section.")
        handler(values)
        return self.read()

    def save_kit(self, v: dict[str, Any]) -> None:
        name = (v.get("name") or "").strip()
        if len(name) < 2:
            raise PlanError("Give the kit a name (2 characters or more).")
        try:
            subnet = str(ipaddress.ip_network(v.get("subnet", "").strip(), strict=False))
        except ValueError:
            raise PlanError("Subnet must look like 192.0.2.0/27.") from None
        gateway = _ip(v.get("gateway") or "", "Gateway")
        dns = [_ip(d, "Each DNS server") for d in (v.get("dns") or [])][:8]
        domain = (v.get("domain") or "").strip().strip(".")
        profile = self.active()
        body = {k: profile.get(k) for k in PROFILE_FIELDS if profile and profile.get(k) is not None} if profile else {}
        settings = dict(body.get("global_settings") or {})
        settings.update(gateway=gateway, dns_servers=dns, domain_name=domain or None, subnet_prefix=int(subnet.split("/")[1]))
        body.update(name=name, subnet_cidr=subnet, gateway=gateway, dns=dns, global_settings=settings)
        body.setdefault("ntp", [])
        if profile:
            self.api._call("PUT", f"/api/v1/lab/profiles/{urllib.parse.quote(profile['id'])}", body)
        else:
            created = self.api.post("/api/v1/lab/profiles", body)
            self.api.post(f"/api/v1/lab/profiles/{urllib.parse.quote(created['id'])}/activate")

    def save_equipment(self, v: dict[str, Any]) -> None:
        profile = self.active()
        if not profile:
            raise PlanError("Save the kit first.")
        p = profile["id"]
        plan, server, switch = self._equipment(p)
        server_name, switch_name = (v.get("server_name") or "").strip(), (v.get("switch_name") or "").strip()
        if not server_name and not switch_name:
            raise PlanError("Name the server, the switch, or both.")
        # Leaving a device out removes it from the kit's plan (its records stay). That must be said on purpose.
        dropping = [e["name"] for e, keep in ((server, server_name), (switch, switch_name)) if e and not keep]
        if dropping and not v.get("remove_missing"):
            raise PlanError(f"{' and '.join(dropping)} would be removed from the kit. Confirm that, or name it as well.")
        model = v.get("server_model") or "HPE DL360 Gen10"
        height = 2 if "DL380" in model else 1
        ports = 48 if int(v.get("switch_ports") or 24) == 48 else 24
        others = [e for e in plan["equipment"] if e["kind"] not in ("server", "switch")]
        units = max(int(plan.get("rack_units") or 12), 4)
        equipment = []
        if server_name:  # a kit with no server keeps none; an existing one keeps its device id and bays
            equipment.append({**(server or {}), "id": (server or {}).get("id") or "server-1", "name": server_name, "kind": "server", "model": model, "device_id": (server or {}).get("device_id"),
                              "position": units - height + 1, "height": height, "mount": "rack", "ports": 0, "uplink_ports": 0, "bay_count": (server or {}).get("bay_count") or (24 if height == 2 else 10),
                              "occupied_bays": (server or {}).get("occupied_bays") or []})
        if switch_name:
            equipment.append({**(switch or {}), "id": (switch or {}).get("id") or "switch-1", "name": switch_name, "kind": "switch", "model": (switch or {}).get("model") or "Cisco Catalyst", "device_id": (switch or {}).get("device_id"),
                              "position": units - (height if server_name else 0), "height": 1, "mount": "rack", "ports": ports, "uplink_ports": (switch or {}).get("uplink_ports") or 4, "bay_count": 0, "occupied_bays": []})
        equipment += others
        self.api._call("PUT", f"/api/v1/rack-plans/{urllib.parse.quote(p)}", {"revision": plan.get("revision", 0), "rack_units": units, "equipment": equipment})

    def _server(self) -> tuple[str, str]:
        profile = self.active()
        if not profile:
            raise PlanError("Save the kit first.")
        _, server, _ = self._equipment(profile["id"])
        if not server or not server.get("device_id"):
            raise PlanError("Save the equipment first.")
        return profile["id"], server["device_id"]

    def _switch(self) -> tuple[str, str]:
        profile = self.active()
        if not profile:
            raise PlanError("Save the kit first.")
        _, _, switch = self._equipment(profile["id"])
        if not switch or not switch.get("device_id"):
            raise PlanError("Save the equipment first.")
        return profile["id"], switch["device_id"]

    def save_ilo(self, v: dict[str, Any]) -> None:
        _, d = self._server()
        body = {k: v[k].strip() for k in ("host", "username", "password") if v.get(k) and v[k].strip()}
        if "host" not in body:
            raise PlanError("Enter the iLO address.")
        self.api._call("PUT", _q("/api/v1/providers/ilo-redfish/access-settings", d), body)

    def save_switch(self, v: dict[str, Any]) -> None:
        p, d = self._switch()
        hostname, domain, username = (v.get("hostname") or "").strip(), (v.get("domain") or "").strip(), (v.get("username") or "").strip()
        if not hostname or not domain or not username:
            raise PlanError("Enter the switch name, domain and admin user.")
        access = {"username": username}
        if v.get("password"):
            access["password"] = v["password"]
        self.api._call("PUT", f"/api/v1/devices/{d}/switch-access", access)
        setup = {"hostname": hostname, "domain": domain, "username": username, "vlan": int(v.get("vlan") or 1), "mode": v.get("mode") or "dhcp",
                 "address": v.get("address") or None, "prefix": v.get("prefix") or None, "gateway": None, "save": True}
        if setup["mode"] == "static":
            if not setup["address"] or not setup["prefix"]:
                raise PlanError("A static address needs address/prefix, like 192.0.2.2/24.")
            _ip(setup["address"], "The switch address")
            kit = self.active() or {}
            setup["gateway"] = kit.get("gateway") or (kit.get("global_settings") or {}).get("gateway")
        if v.get("password"):
            setup["password"] = v["password"]
        self.api._call("PUT", _q(f"/api/v1/rack-plans/{urllib.parse.quote(p)}/switch-setup/setup", d), setup)

    def save_esxi(self, v: dict[str, Any]) -> None:
        p, d = self._server()
        hostname = (v.get("hostname") or "").strip()
        if not HOSTNAME.match(hostname):
            raise PlanError("Enter the ESXi host name (letters, digits, dots and dashes).")
        body = {"hostname": hostname, "addressing": v.get("addressing") or "dhcp", "management_ip": None, "vlan_id": 0,
                "management_nic": "vmnic0", "datastore_name": (v.get("datastore_name") or "VMdata").strip() or "VMdata"}
        if body["addressing"] == "static":
            body["management_ip"] = _ip(v.get("management_ip") or "", "The ESXi address")
        if v.get("root_password"):
            body["root_password"] = v["root_password"]
        current = self.api.get(_q(f"/api/v1/rack-plans/{p}/esxi/settings", d))
        body["management_nic"] = current.get("management_nic") or "vmnic0"
        body["vlan_id"] = current.get("vlan_id") or 0
        self.api._call("PUT", _q(f"/api/v1/rack-plans/{urllib.parse.quote(p)}/esxi/settings", d), body)
        if v.get("iso"):
            self.api.post(_q(f"/api/v1/rack-plans/{urllib.parse.quote(p)}/esxi/media", d), {"path": v["iso"]})

    def save_windows(self, v: dict[str, Any]) -> None:
        p, d = self._server()
        image, vm_name = (v.get("image") or "").strip(), (v.get("vm_name") or "").strip()
        if not image:
            raise PlanError("Choose the Windows image.")
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9-]{0,62}$", vm_name):
            raise PlanError("Name the VM with letters, digits and dashes.")
        setup = self.api.get(_q(f"/api/v1/rack-plans/{p}/windows/setup", d) + "&host=false")
        datastore = setup.get("datastore") or (setup.get("host") or {}).get("default_datastore") or self.api.get(_q(f"/api/v1/rack-plans/{p}/esxi/settings", d)).get("datastore_name") or "VMdata"
        network = setup.get("network") or "VM Network"  # ESXi's default port group; the deploy review checks it exists
        self.api._call("PUT", _q(f"/api/v1/rack-plans/{urllib.parse.quote(p)}/windows/setup", d), {"image": image, "vm_name": vm_name, "datastore": datastore, "network": network})
        if v.get("password"):
            username = (v.get("username") or "Administrator").strip()
            self.api._call("PUT", _q(f"/api/v1/rack-plans/{urllib.parse.quote(p)}/windows/guest-signin", d), {"username": username, "password": v["password"]})

    # ------------------------------------------------------------- reading equipment (explicit click only)
    def read_equipment(self, what: str, values: dict[str, Any]) -> dict[str, Any]:
        if what == "ilo":
            _, d = self._server()
            probe = self.api.post(_q("/api/v1/providers/ilo-redfish/probe", d))
            ok = probe.get("status") == "ok"
            model = next((s.get("Model") for s in (probe.get("systems") or []) if isinstance(s, dict) and s.get("Model")), None)
            return {"ok": ok, "message": (f"The server answered: {model}." if model else "The server answered.") if ok else (probe.get("message") or "The iLO did not answer.")}
        if what == "switch":
            _, d = self._switch()
            port = (values.get("port") or "").strip()
            ports = self.api.get(f"/api/v1/devices/{d}/switch-console/ports")
            chosen = next((x for x in ports.get("ports", []) if x["port"] == port), None)
            if not chosen:
                raise PlanError("Choose the COM port the console cable is on.")
            baud = (chosen.get("recommended_bauds") or [9600])[0]
            read = self.api.post(f"/api/v1/devices/{d}/switch-console/identify", {"port": port, "baud": baud, "candidate_fingerprint": chosen["candidate_fingerprint"]}, timeout=180)
            ok = bool(read.get("answered"))
            return {"ok": ok, "message": (f"The switch answered on {port}: {read.get('model') or 'model unknown'}. {read.get('state_text') or ''}".strip()) if ok else (read.get("message") or "Nothing answered on the console cable.")}
        raise PlanError("Unknown read.")
