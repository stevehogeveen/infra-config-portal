from dataclasses import replace

import pytest

from app.models import DeviceInventory
from app.services import switch_access as service

VERSION = """Cisco IOS XE Software, Version 16.12.04
lab-sw01 uptime is 3 weeks, 2 days
Model Number                       : C9300-48T
System Serial Number               : FOC0000X000
lab-sw01#"""
INVENTORY = 'NAME: "c93xx Stack", DESCR: "c93xx Stack"\nPID: C9300-48T         , VID: V02  , SN: FOC0000X000\nlab-sw01#'
STATUS = "Port      Name   Status       Vlan\nGi1/0/1          connected    1\nGi1/0/2          notconnect   1\nTe1/1/1          notconnect   1\nlab-sw01#"


@pytest.fixture
def switch(db_session):
    db_session.add(DeviceInventory(id="sw-1", device_type="cisco_switch", display_name="Cisco switch 1"))
    db_session.add(DeviceInventory(id="srv-1", device_type="ilo", display_name="Server"))
    db_session.commit()
    return "sw-1"


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(service, "settings", replace(service.settings, provider_mode="local-readonly"))
    monkeypatch.setattr(service, "current_lab_action_policy", lambda mode: type("P", (), {"readonly_allowed": True})())
    monkeypatch.setattr(service, "_tcp_connect", lambda host, port, timeout: {"reachable": True})


def test_save_and_read_never_return_passwords(db_session, switch):
    read = service.save_access(db_session, switch, {"host": "192.0.2.40", "username": "admin", "password": "Fixture-Pass-1", "enable_password": "Fixture-Enable-1"})
    assert read["host"] == "192.0.2.40" and read["username"] == "admin"
    assert read["password_configured"] and read["enable_password_configured"]
    assert "Fixture-Pass-1" not in str(read) and "Fixture-Enable-1" not in str(read)
    # A blank password keeps the saved one.
    read = service.save_access(db_session, switch, {"host": "192.0.2.41", "password": ""})
    assert read["host"] == "192.0.2.41" and read["password_configured"]


def test_a_server_is_not_a_switch(db_session, switch):
    with pytest.raises(service.SwitchAccessError):
        service.read_access(db_session, "srv-1")


def test_check_reads_identity_and_the_answer_belongs_to_the_saved_sign_in(db_session, switch, live):
    service.save_access(db_session, switch, {"host": "192.0.2.40", "username": "admin", "password": "Fixture-Pass-1"})
    sent = []

    def connect(host, username, password, timeout):
        sent.append(host)
        return {"show version": VERSION, "show inventory": INVENTORY, "show interfaces status": STATUS}

    result = service.check(db_session, switch, connect=connect)
    assert result["status"] == "ok"
    expected = {"hostname": "lab-sw01", "model": "C9300-48T", "version": "16.12.04", "serial": "FOC0000X000", "port_count": 3}
    assert {key: result[key] for key in expected} == expected
    assert "Fixture-Pass-1" not in str(result)
    assert service.read_access(db_session, switch)["last_check"]["model"] == "C9300-48T"
    # A new address means the old answer no longer proves anything.
    service.save_access(db_session, switch, {"host": "192.0.2.41"})
    assert service.read_access(db_session, switch)["last_check"] is None


def test_unreachable_and_refused_sign_in_say_why(db_session, switch, live, monkeypatch):
    service.save_access(db_session, switch, {"host": "192.0.2.40", "username": "admin", "password": "Fixture-Pass-1"})

    def refused(*args):
        raise service._SignInRefused()

    assert service.check(db_session, switch, connect=refused)["status"] == "sign_in_failed"
    monkeypatch.setattr(service, "_tcp_connect", lambda host, port, timeout: {"reachable": False})
    result = service.check(db_session, switch, connect=refused)
    assert result["status"] == "unreachable" and "console" in result["message"]


def test_practice_mode_never_contacts_the_switch(db_session, switch, monkeypatch):
    monkeypatch.setattr(service, "settings", replace(service.settings, provider_mode="mock"))
    service.save_access(db_session, switch, {"host": "192.0.2.40", "username": "admin", "password": "Fixture-Pass-1"})
    result = service.check(db_session, switch, connect=lambda *a: pytest.fail("contacted"))
    assert result["status"] == "blocked"


def test_api_round_trip(client, db_session, switch):
    response = client.put(f"/api/v1/devices/{switch}/switch-access", json={"host": "192.0.2.40", "username": "admin", "password": "Fixture-Pass-1"})
    assert response.status_code == 200 and response.json()["password_configured"]
    assert client.get("/api/v1/devices/srv-1/switch-access").status_code == 409
    assert client.get("/api/v1/devices/missing/switch-access").status_code == 404


# Console cable: COM ports come from the helper on the PC; the identity check is read-only.
from types import SimpleNamespace

from app.providers import console_bridge

PORTS = [
    SimpleNamespace(device="COM3", description="Intel(R) Active Management Technology - SOL", manufacturer="Intel", hwid=r"PCI\VEN_8086&DEV_51E3", product="", interface="", serial_number=None, location=None, vid=None, pid=None),
    SimpleNamespace(device="COM5", description="Prolific USB-to-Serial Comm Port", manufacturer="Prolific", hwid="USB VID:PID=067B:2303 LOCATION=5&0000&0&6", product="", interface="", serial_number=None, location=None, vid=None, pid=None),
]
SHOW_VERSION = """Cisco IOS XE Software, Version 16.12.04
Cisco IOS Software [Gibraltar], Catalyst L3 Switch Software (CAT9K_IOSXE), Version 16.12.4
Model Number                       : C9300-48T
System Serial Number               : FOC0000X000
Switch>"""


class FakeConsole:
    def __init__(self, replies):
        self.replies, self.out, self.sent = replies, b"", []
        self.timeout = 0.1

    @property
    def in_waiting(self):
        return len(self.out)

    def read(self, size=1):
        data, self.out = self.out[:size], self.out[size:]
        return data

    def write(self, data):
        self.sent.append(data)
        self.out += self.replies.get(data, b"").encode() if isinstance(self.replies.get(data, b""), str) else self.replies.get(data, b"")
        return len(data)

    def close(self):
        pass


def test_console_ports_lists_the_usb_cable_first_choice(db_session, switch):
    listed = service.console_ports(db_session, switch, lister=lambda: PORTS)
    assert listed["helper_running"]
    by_port = {item["port"]: item for item in listed["ports"]}
    assert by_port["COM5"]["usb"] and by_port["COM5"]["recommended"]
    assert not by_port["COM3"]["usb"] and "not a console cable" in by_port["COM3"]["hint"]


def test_console_ports_explain_a_missing_helper(db_session, switch):
    def down():
        raise console_bridge.BridgeUnavailable("refused")

    listed = service.console_ports(db_session, switch, lister=down)
    assert not listed["helper_running"] and "start-lab-builder.cmd" in listed["problem"]


def test_console_identify_reads_show_version_and_remembers_the_port(db_session, switch, live, monkeypatch):
    monkeypatch.setattr("app.services.cisco_console_identity._readonly_contact_blockers", lambda mode: [])
    fingerprint = {item["port"]: item for item in service.console_ports(db_session, switch, lister=lambda: PORTS)["ports"]}["COM5"]["candidate_fingerprint"]
    console = FakeConsole({b"\r\n": "\r\nSwitch>", b"show version\r\n": SHOW_VERSION})
    result = service.console_identify(db_session, switch, "COM5", 9600, fingerprint, lister=lambda: PORTS, opener=lambda port, baud: console)
    assert result["identity_verified"] and result["model"] == "C9300-48T"
    assert console.sent == [b"\r\n", b"show version\r\n"]
    assert service.read_access(db_session, switch)["console"]["port"] == "COM5"


def test_a_new_switch_at_its_setup_questions_is_not_answered(db_session, switch, live, monkeypatch):
    monkeypatch.setattr("app.services.cisco_console_identity._readonly_contact_blockers", lambda mode: [])
    fingerprint = {item["port"]: item for item in service.console_ports(db_session, switch, lister=lambda: PORTS)["ports"]}["COM5"]["candidate_fingerprint"]
    wizard = "\r\n         --- System Configuration Dialog ---\r\n\r\nWould you like to enter the initial configuration dialog? [yes/no]: "
    console = FakeConsole({b"\r\n": wizard})
    result = service.console_identify(db_session, switch, "COM5", 9600, fingerprint, lister=lambda: PORTS, opener=lambda port, baud: console)
    assert result["prompt_state"] == "setup-wizard" and result["answered"]
    # Nothing beyond the blank Enter: no "yes"/"no", no show command.
    assert all(sent == b"\r\n" for sent in console.sent)


def test_bridge_connection_reads_like_a_serial_port():
    import socket

    left, right = socket.socketpair()
    connection = console_bridge.BridgeConnection(left)
    right.sendall(b"Switch>")
    assert connection.read(100) == b"Switch>"
    connection.write(b"\r\n")
    assert right.recv(10) == b"\r\n"
    connection.close(); right.close()


class BriefConsole(FakeConsole):
    def write(self, data):
        self.sent.append(data)
        line = data.decode().strip()
        if line == "":
            self.out += self.first.encode()
        elif line.startswith("show ip interface brief"):
            self.out += ("\nInterface              IP-Address      OK? Method Status                Protocol\n"
                         "Vlan1                  192.0.2.61      YES DHCP   up                    up\nSwitch>").encode()
        return len(data)


def test_console_address_reads_the_dhcp_address_without_answering_anything(db_session, switch, live, monkeypatch):
    monkeypatch.setattr("app.services.cisco_console_identity._readonly_contact_blockers", lambda mode: [])
    service._remember_console(db_session, switch, "COM5", 9600)
    console = BriefConsole({})
    console.first = "\nSwitch>"
    result = service.console_address(db_session, switch, opener=lambda port, baud: console)
    assert result["address"] == "192.0.2.61" and "DHCP" in result["message"]
    assert service.read_access(db_session, switch)["host"] == "192.0.2.61"
    assert [d.decode() for d in console.sent] == ["\r", "show ip interface brief | exclude unassigned\r"]
    new = BriefConsole({})
    new.first = "\n--- System Configuration Dialog ---\n\nWould you like to enter the initial configuration dialog? [yes/no]: "
    result = service.console_address(db_session, switch, opener=lambda port, baud: new)
    assert result["state"] == "wizard" and [d.decode() for d in new.sent] == ["\r"]
