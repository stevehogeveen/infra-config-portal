"""The flight plan forwards each card to Lab Builder's own settings endpoints, and never returns a password."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from engine import Api  # noqa: E402
from flightplan import FlightPlan, PlanError  # noqa: E402


class FakeApi(Api):
    """Records every call; answers like Lab Builder after a kit and its equipment exist."""

    def __init__(self) -> None:
        super().__init__("http://fake")
        self.calls: list[tuple[str, str, dict | None]] = []
        self.profile: dict | None = {"id": "kit-1", "name": "Kit", "subnet_cidr": "192.0.2.0/27", "gateway": "192.0.2.1", "dns": ["192.0.2.53"], "ntp": [],
                                     "global_settings": {"gateway": "192.0.2.1", "dns_servers": ["192.0.2.53"], "domain_name": "lab.test"}, "version": 3, "history": []}
        self.rack = {"revision": 2, "rack_units": 12, "equipment": [
            {"id": "server-1", "device_id": "srv", "name": "HPE DL360 1", "kind": "server", "model": "HPE DL360 Gen10", "position": 12, "height": 1, "mount": "rack", "ports": 0, "uplink_ports": 0, "bay_count": 10, "occupied_bays": []},
            {"id": "switch-1", "device_id": "sw", "name": "Cisco switch 1", "kind": "switch", "model": "Catalyst", "position": 11, "height": 1, "mount": "rack", "ports": 24, "uplink_ports": 4, "bay_count": 0, "occupied_bays": []}]}

    def _call(self, method, path, body=None, timeout=None):
        self.calls.append((method, path, body))
        clean = path.split("?")[0]
        if clean == "/api/v1/lab/profiles":
            return {"active_profile": self.profile}
        if clean.startswith("/api/v1/lab/profiles/") and method == "PUT":
            assert "version" not in body and "history" not in body, "the full stored profile must not be sent back"
            self.profile = {**self.profile, **body}
            return self.profile
        if clean == "/api/v1/rack-plans/kit-1":
            if method == "PUT":
                for item in body["equipment"]:
                    item["device_id"] = item.get("device_id") or f"new-{item['kind']}"
                self.rack = {**body, "revision": body["revision"] + 1}
            return self.rack
        if clean == "/api/v1/providers/ilo-redfish/access-settings":
            return {"host": "192.0.2.10", "username": "Administrator", "password_configured": True, "last_probe_status": "ok", "last_probe_is_current": True}
        if clean.endswith("/esxi/settings"):
            return {"hostname": "esx01", "addressing": "dhcp", "management_ip": None, "vlan_id": 0, "management_nic": "aa:bb", "datastore_name": "VMdata", "saved_at": "x", "password_set": True}
        if clean.endswith("/esxi/media"):
            return {"isos": [{"path": "esxi.iso", "name": "esxi.iso"}], "selected": {"path": "esxi.iso"}}
        if clean.endswith("/windows/setup"):
            return {"images": [{"path": "win.ova", "name": "win.ova", "missing": []}], "image": "win.ova", "vm_name": "windows01", "datastore": "VMdata", "network": "VM Network", "saved_at": "x",
                    "host": {"default_datastore": "VMdata", "networks": ["VM Network"]}}
        if clean.endswith("/windows/guest-signin"):
            return {"username": "Administrator", "password_saved": True}
        if clean.endswith("/switch-access"):
            return {"username": "admin", "password_configured": True, "host": None, "console": {"port": "COM5", "last": {"answered": True, "model": "C9300"}}}
        if clean.endswith("/switch-console/ports"):
            return {"ports": [{"port": "COM5", "description": "USB serial", "recommended": True, "candidate_fingerprint": "f5", "recommended_bauds": [9600]}], "problem": None}
        if clean.endswith("/switch-console/identify"):
            return {"answered": True, "model": "C9300-48T", "state_text": "At its normal prompt."}
        if clean.endswith("/switch-setup/setup"):
            return {"settings": {"hostname": "lab-sw01", "domain": "lab.test", "vlan": 100, "mode": "dhcp"}, "defaults": {"hostname": "cisco-switch-1"}}
        if clean == "/api/v1/providers/ilo-redfish/probe":
            return {"status": "ok", "systems": [{"Model": "ProLiant DL360 Gen10"}]}
        return {}

    def sent(self, method, suffix):
        return [b for m, p, b in self.calls if m == method and p.split("?")[0].endswith(suffix)]


@pytest.fixture
def plan():
    return FlightPlan(FakeApi())


def test_reading_the_plan_never_returns_a_password(plan):
    text = json.dumps(plan.read())
    assert "password_configured" in text and "Fixture" not in text
    assert not any(k in text for k in ('"password"', '"root_password"', '"enable_password"'))
    assert plan.read()["switch"]["console_ports"][0]["port"] == "COM5"


def test_kit_save_sends_only_allowed_profile_fields(plan):
    plan.save("kit", {"name": "Kit Single", "subnet": "192.0.2.0/27", "gateway": "192.0.2.1", "dns": ["192.0.2.53", "192.0.2.54"], "domain": "lab.test"})
    body = plan.api.sent("PUT", "/lab/profiles/kit-1")[0]
    assert body["name"] == "Kit Single" and body["subnet_cidr"] == "192.0.2.0/27" and body["global_settings"]["dns_servers"] == ["192.0.2.53", "192.0.2.54"]
    assert body["global_settings"]["subnet_prefix"] == 27 and "version" not in body
    with pytest.raises(PlanError):
        plan.save("kit", {"name": "K", "subnet": "x", "gateway": "y"})


def test_equipment_save_keeps_device_ids_and_the_revision(plan):
    plan.save("equipment", {"server_name": "HPE DL360 1", "server_model": "HPE DL360 Gen10", "switch_name": "Cisco switch 1", "switch_ports": 48})
    body = plan.api.sent("PUT", "/rack-plans/kit-1")[0]
    assert body["revision"] == 2
    server, switch = body["equipment"][0], body["equipment"][1]
    assert server["device_id"] == "srv" and switch["device_id"] == "sw" and switch["ports"] == 48 and server["height"] == 1


def test_ilo_and_switch_saves_pass_passwords_through_once(plan):
    plan.save("ilo", {"host": "192.0.2.10", "username": "Administrator", "password": "Fixture-Ilo-1"})
    assert plan.api.sent("PUT", "/access-settings")[0] == {"host": "192.0.2.10", "username": "Administrator", "password": "Fixture-Ilo-1"}
    plan.save("ilo", {"host": "192.0.2.10", "username": "Administrator", "password": ""})
    assert "password" not in plan.api.sent("PUT", "/access-settings")[1]
    plan.save("switch", {"hostname": "lab-sw01", "domain": "lab.test", "vlan": 100, "mode": "dhcp", "username": "admin", "password": "Fixture-Sw-1"})
    assert plan.api.sent("PUT", "/switch-access")[0] == {"username": "admin", "password": "Fixture-Sw-1"}
    setup = plan.api.sent("PUT", "/switch-setup/setup")[0]
    assert setup["hostname"] == "lab-sw01" and setup["vlan"] == 100 and setup["mode"] == "dhcp" and setup["save"] is True and setup["password"] == "Fixture-Sw-1"
    with pytest.raises(PlanError):
        plan.save("switch", {"hostname": "lab-sw01", "domain": "lab.test", "vlan": 1, "mode": "static", "username": "admin"})


def test_esxi_and_windows_saves(plan):
    plan.save("esxi", {"hostname": "esx01", "addressing": "static", "management_ip": "192.0.2.20", "datastore_name": "VMdata", "root_password": "Fixture-Root-1", "iso": "esxi.iso"})
    body = plan.api.sent("PUT", "/esxi/settings")[0]
    assert body["management_ip"] == "192.0.2.20" and body["root_password"] == "Fixture-Root-1" and body["management_nic"] == "aa:bb"
    assert plan.api.sent("POST", "/esxi/media")[0] == {"path": "esxi.iso"}
    plan.save("windows", {"image": "win.ova", "vm_name": "windows01", "username": "Administrator", "password": "Fixture-Win-1"})
    assert plan.api.sent("PUT", "/windows/setup")[0] == {"image": "win.ova", "vm_name": "windows01", "datastore": "VMdata", "network": "VM Network"}
    assert plan.api.sent("PUT", "/windows/guest-signin")[0] == {"username": "Administrator", "password": "Fixture-Win-1"}


def test_read_buttons_read_and_say_what_answered(plan):
    assert plan.read_equipment("ilo", {})["message"] == "The server answered: ProLiant DL360 Gen10."
    read = plan.read_equipment("switch", {"port": "COM5"})
    assert read["ok"] and "C9300-48T" in read["message"]
    assert plan.api.sent("POST", "/switch-console/identify")[0] == {"port": "COM5", "baud": 9600, "candidate_fingerprint": "f5"}
    with pytest.raises(PlanError):
        plan.read_equipment("switch", {"port": "COM9"})


def test_a_kit_can_be_server_only_or_switch_only(plan):
    plan.save("equipment", {"server_name": "HPE DL360 1", "server_model": "HPE DL360 Gen10", "switch_name": "", "switch_ports": 24, "remove_missing": True})
    body = plan.api.sent("PUT", "/rack-plans/kit-1")[-1]
    assert [e["kind"] for e in body["equipment"]] == ["server"] and body["equipment"][0]["device_id"] == "srv"
    with pytest.raises(PlanError):
        plan.save("equipment", {"server_name": "", "switch_name": ""})


def test_leaving_a_device_out_needs_an_explicit_removal(plan):
    with pytest.raises(PlanError, match="would be removed"):
        plan.save("equipment", {"server_name": "", "switch_name": "Cisco switch 1", "switch_ports": 24})
    plan.save("equipment", {"server_name": "", "switch_name": "Cisco switch 1", "switch_ports": 24, "remove_missing": True})
    assert [e["kind"] for e in plan.api.sent("PUT", "/rack-plans/kit-1")[-1]["equipment"]] == ["switch"]
