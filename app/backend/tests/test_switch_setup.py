from contextlib import nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.models import DeviceInventory
from app.providers import cisco_console_setup as driver
from app.services import switch_access
from app.services import switch_setup as service

PASSWORD = "Fixture-Pass-1"
ENABLE = "Fixture-Enable-1"


class FakeSwitch:
    """A console that answers like a new Cisco switch (documentation addresses only)."""

    def __init__(self, start="wizard", refuse=(), address="192.0.2.50", ask=(), connected=("Gi1/0/48",)):
        self.ask = ask
        self.connected = connected
        self.state, self.name, self.mode = start, "Switch", "exec"
        self.out, self.lines, self.refuse, self.address = b"", [], refuse, address
        self.closed = False

    @property
    def in_waiting(self):
        return len(self.out)

    def read(self, size=1):
        data, self.out = self.out[:size], self.out[size:]
        return data

    def _say(self, text):
        self.out += text.encode()

    def prompt(self):
        suffix = {"exec": ">", "priv": "#", "config": "(config)#", "if": "(config-if)#", "line": "(config-line)#", "vlan": "(config-vlan)#"}[self.mode]
        return f"\n{self.name}{suffix}"

    def write(self, data):
        line = data.decode().rstrip("\r")
        self.lines.append(line)
        if self.state == "wizard":
            if line == "":
                self._say("\n         --- System Configuration Dialog ---\n\nWould you like to enter the initial configuration dialog? [yes/no]: ")
            elif line == "no":
                self.state = "return"
                self._say("\n\nPress RETURN to get started!\n")
            return len(data)
        if self.state == "login":
            self._say("\n\nUser Access Verification\n\nUsername: ")
            return len(data)
        if self.state == "exec" and line == "":
            self.state = "ready"
            self._say(self.prompt())
            return len(data)
        if self.state == "return":
            self.state = "ready"
            self._say(self.prompt())
            return len(data)
        if line == "enable":
            self.mode = "priv"
        elif line == "configure terminal":
            self.mode = "config"
            self._say("\nEnter configuration commands, one per line.  End with CNTL/Z.")
        elif line == "end":
            self.mode = "priv"
        elif line == "write memory":
            self._say("\nBuilding configuration...\n[OK]")
        elif line == "show running-config":
            body = (f"\nBuilding configuration...\n\nCurrent configuration : 123 bytes\n!\nversion 17.15\nhostname {self.name}\n"
                    + ("username admin privilege 15 secret 9 $9$abc\nenable secret 9 $9$def\n" if self.mode == "priv" and self.name != "Switch" else "")
                    + "line vty 0 15\n login\nend")
            if getattr(self, "syslog_in_config", False):  # a log line lands mid-output, splitting " login" (as a real switch does)
                at = body.index(" login") + len(" lo")
                body = body[:at] + "\n*Oct 22 14:42:38.254: %CDP-4-NATIVE_VLAN_MISMATCH: Native VLAN mismatch discovered on GigabitEthernet1/0/2 (100), with Switch GigabitEthernet1/0/14 (670)." + body[at:]
            if getattr(self, "paged", False):
                half = len(body) // 2
                self.pending_page = body[half:]
                self._say(body[:half] + "\n --More-- ")
                return len(data)
            self._say(body)
        elif line == " " and getattr(self, "pending_page", None):
            self._say(self.pending_page)
            self.pending_page = None
        elif line == "show ip ssh":
            self._say("\nSSH Enabled - version 2.0\nAuthentication methods:publickey,keyboard-interactive,password")
            if getattr(self, "late_syslog", False):  # the prompt, then a log line on top of it (as a real switch does)
                self._say(self.prompt() + "\n*Oct 18 14:08:05.123: %SSH-5-ENABLED: SSH 2.0 has been enabled\n")
                self.late_syslog = False
                return len(data)
        elif line.startswith("show version | include"):
            self._say("\nSystem Serial Number               : FOC0000X000")
        elif line == "show interfaces status":
            rows = ["Port         Name               Status       Vlan       Duplex  Speed Type"]
            for n in range(1, 49):
                port = f"Gi1/0/{n}"
                rows.append(f"{port:<12} {'':<18} {'connected' if port in self.connected else 'notconnect':<12} 1          a-full a-1000 10/100/1000BaseTX")
            self._say("\n" + "\n".join(rows))
        elif line.startswith("show ip interface brief"):
            self._say(f"\nVlan1                  {self.address or 'unassigned'}     YES DHCP   up                    up")
        elif self.mode in {"config", "if", "line", "vlan"}:
            if line in self.ask:
                self._say("\nProceed? [confirm]")
                return len(data)
            if line.startswith("crypto key generate") and getattr(self, "keys_exist", False):
                self._say(f"\n% You already have RSA keys defined named {self.name}.lab.local.\n% They will be replaced.\n\nDo you really want to replace them? [yes/no]: ")
                return len(data)
            if line == "no" and getattr(self, "keys_exist", False):
                self._say("\n% Key pair was not generated.")
                self._say(self.prompt())
                return len(data)
            if any(word in line for word in self.refuse):
                self._say("\n                 ^\n% Invalid input detected at '^' marker.\n")
            elif line.startswith("hostname "):
                self.name = line.split()[1]
            elif line.startswith("interface "):
                self.mode = "if"
            elif line.startswith("line vty") or line.startswith("line console"):
                self.mode = "line"
            elif line.startswith("vlan "):
                self.mode = "vlan"
            elif line == "exit":
                self.mode = "config"
        self._say(self.prompt())
        return len(data)

    def close(self):
        self.closed = True


def plan(**change):
    values = dict(hostname="lab-sw01", domain="lab.local", username="admin", password=PASSWORD, enable_secret=ENABLE,
                  vlan=1, mode="dhcp", save=True)
    values.update(change)
    return driver.SetupPlan(**values)


def run_driver(switch, setup):
    console = driver.Console(switch)
    start = driver.reach_privileged(console)
    done = driver.configure(console, setup)
    return start, done, driver.read_address(console, setup.vlan)


def test_a_new_switch_skips_the_dialog_and_is_configured_and_saved():
    switch = FakeSwitch()
    start, done, (address, _) = run_driver(switch, plan())
    assert start == "wizard" and done["saved"] and address == "192.0.2.50"
    assert switch.lines[:2] == ["", "no"]  # only "no" is ever answered to the setup dialog
    assert "ip address dhcp" in switch.lines and "transport input ssh" in switch.lines and "write memory" in switch.lines
    shown = "\n".join(done["sent"])
    assert PASSWORD not in shown and ENABLE not in shown and "secret ********" in shown
    assert not any(word in " ".join(switch.lines) for word in ("erase", "reload", "delete", "boot system"))


def test_static_address_sets_mask_and_gateway():
    switch = FakeSwitch()
    run_driver(switch, plan(mode="static", address="192.0.2.40", prefix=24, gateway="192.0.2.1"))
    assert "ip address 192.0.2.40 255.255.255.0" in switch.lines
    assert "ip default-gateway 192.0.2.1" in switch.lines


def test_a_switch_that_asks_for_a_login_is_left_alone():
    switch = FakeSwitch(start="login")
    with pytest.raises(driver.SetupStopped) as stopped:
        run_driver(switch, plan())
    assert stopped.value.sent is False and "configure terminal" not in switch.lines


def test_the_first_refused_line_stops_and_leaves_config_mode_unsaved():
    switch = FakeSwitch(refuse=("ip ssh",))
    with pytest.raises(driver.SetupStopped) as stopped:
        run_driver(switch, plan())
    assert stopped.value.sent is True and "ip ssh version 2" in str(stopped.value)
    assert switch.lines[-1] == "end" and "write memory" not in switch.lines


def test_older_ios_spelling_is_tried_once():
    switch = FakeSwitch(refuse=("ip domain name",))
    run_driver(switch, plan())
    assert "ip domain-name lab.local" in switch.lines


def test_plan_checks():
    assert plan().problems() == []
    assert any("gateway" in p for p in plan(mode="static", address="192.0.2.40", prefix=24, gateway="198.51.100.1").problems())
    assert any("password" in p for p in plan(password="short").problems())
    assert any("VLAN" in p for p in plan(vlan=1003).problems())


# ---------------------------------------------------------------- service

PORTS = [SimpleNamespace(device="COM5", description="Prolific USB-to-Serial Comm Port", manufacturer="Prolific",
                         hwid="USB VID:PID=067B:2303 LOCATION=5&0000&0&6", product="", interface="",
                         serial_number=None, location=None, vid=None, pid=None)]


@pytest.fixture
def kit(db_session, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    db_session.add(DeviceInventory(id="sw-1", device_type="cisco_switch", display_name="Cisco switch 1"))
    db_session.commit()
    monkeypatch.setattr(service, "_session_factory", lambda: sessionmaker(bind=db_session.get_bind()))
    monkeypatch.setattr(service, "_policy_blockers", lambda: [])
    monkeypatch.setattr("app.services.runtime_write_scope.dispatch_lease", lambda action: nullcontext())
    monkeypatch.setattr("app.providers.console_bridge.list_ports", lambda: PORTS)
    monkeypatch.setattr(service, "DHCP_WAIT", 0)
    return "sw-1"


def answered_on_console(db_session, device_id, state="setup-wizard"):
    from app.providers.probe_cache import record_probe_result

    record_probe_result(switch_access.CONSOLE_PROVIDER, {"port": "COM5", "baud": 9600, "answered": True, "prompt_state": state,
                                                         "checked_at": datetime.now(UTC).isoformat()}, scope=device_id)
    switch_access._remember_console(db_session, device_id, "COM5", 9600)


def save(db_session, **change):
    payload = dict(hostname="lab-sw01", domain="lab.local", username="admin", password=PASSWORD, enable_password=None,
                   vlan=1, mode="dhcp", address=None, prefix=24, gateway=None, save=True)
    payload.update(change)
    return service.save_settings(db_session, "sw-1", payload, "op")


def test_settings_keep_passwords_out_of_the_reply_and_review_needs_a_console_reading(db_session, kit):
    setup = save(db_session)
    assert setup["password_configured"] and PASSWORD not in str(setup)
    assert any("console cable first" in b for b in service.review(db_session, kit)["blockers"])
    answered_on_console(db_session, kit)
    reviewed = service.review(db_session, kit)
    assert reviewed["ready"] and reviewed["console_port"] == "COM5", reviewed["blockers"]
    assert PASSWORD not in str(reviewed) and "ip address dhcp" in "\n".join(reviewed["preview"])
    with pytest.raises(service.SwitchSetupError):
        save(db_session, mode="static", address="192.0.2.40", gateway="198.51.100.1")


def test_one_run_configures_over_the_console_then_verifies_over_ssh(db_session, kit, monkeypatch):
    save(db_session)
    answered_on_console(db_session, kit)
    switch = FakeSwitch()
    started = service.start(db_session, "kit", kit, "op", opener=lambda port, baud: switch)
    service._workers[started["run_id"]].join(10)
    assert switch.closed and switch.lines.count("configure terminal") == 1
    current = service.status(db_session, "kit", kit)
    assert current["phases"][0]["state"] == "ok" and current["address"] == "192.0.2.50"
    with pytest.raises(service.SwitchSetupError):
        service.start(db_session, "kit", kit, "op", opener=lambda port, baud: switch)  # never a second run while active
    monkeypatch.setattr(switch_access, "check", lambda session, device_id: {"status": "ok", "message": "lab-sw01 answered.", "hostname": "lab-sw01", "model": "C9300-48T", "version": "16.12.04", "serial": "FOC0000X000"})
    done = service.advance(db_session, "kit", kit, "op")
    assert done["state"] == "verified" and not done["active"]
    assert switch_access.read_access(db_session, kit)["host"] == "192.0.2.50"


def test_a_switch_with_no_dhcp_lease_says_so(db_session, kit):
    save(db_session)
    answered_on_console(db_session, kit)
    switch = FakeSwitch(address=None)
    started = service.start(db_session, "kit", kit, "op", opener=lambda port, baud: switch)
    service._workers[started["run_id"]].join(10)
    current = service.status(db_session, "kit", kit)
    assert current["state"] == "needs_attention" and "DHCP" in current["message"]
    assert service.close(db_session, "kit", kit, "op")["active"] is False


def test_unexpected_questions_are_cancelled_never_approved():
    switch = FakeSwitch(ask=("ip ssh version 2",))
    with pytest.raises(driver.SetupStopped) as stopped:
        run_driver(switch, plan())
    assert "\x03" in switch.lines and "write memory" not in switch.lines and stopped.value.sent


def test_control_characters_and_ipv6_are_refused_before_anything_is_sent():
    assert plan(password="Fixture\x1aPass1").problems()
    assert plan(password="Fixture Pass1").problems()
    assert plan(mode="static", address="2001:db8::5", prefix=64, gateway="2001:db8::1").problems()


def test_errors_never_carry_a_password():
    assert driver.scrub("% Invalid input near Fixture-Pass-1", PASSWORD) == "% Invalid input near ********"


def test_a_switch_without_its_setup_dialog_needs_explicit_replacement(db_session, kit):
    save(db_session)
    answered_on_console(db_session, kit, state="exec")
    reviewed = service.review(db_session, kit)
    assert reviewed["replace_needed"] and any("replaced" in note for note in reviewed["notes"])
    with pytest.raises(service.SwitchSetupError, match="replaced"):
        service.start(db_session, "kit", kit, "op", opener=lambda port, baud: pytest.fail("contacted"))
    switch = FakeSwitch(start="exec")
    started = service.start(db_session, "kit", kit, "op", replace_existing=True, opener=lambda port, baud: switch)
    service._workers[started["run_id"]].join(10)
    assert service.status(db_session, "kit", kit)["phases"][0]["state"] == "ok"


def test_ssh_from_a_different_device_does_not_verify(db_session, kit, monkeypatch):
    save(db_session)
    answered_on_console(db_session, kit)
    switch = FakeSwitch()
    started = service.start(db_session, "kit", kit, "op", opener=lambda port, baud: switch)
    service._workers[started["run_id"]].join(10)
    monkeypatch.setattr(switch_access, "check", lambda session, device_id: {"status": "ok", "message": "answered", "hostname": "other-sw", "serial": "FOC0000X000"})
    current = service.advance(db_session, "kit", kit, "op")
    assert current["state"] == "needs_attention" and "other-sw" in current["message"]


def test_a_management_vlan_other_than_1_is_put_on_the_one_cabled_port():
    switch = FakeSwitch()
    _, done, _ = run_driver(switch, plan(vlan=100))
    assert done["uplink"] == "Gi1/0/48"
    at = switch.lines.index("interface Gi1/0/48")
    assert switch.lines[at:at + 6] == ["interface Gi1/0/48", "description Lab Builder uplink", "switchport mode access",
                                       "switchport access vlan 100", "no shutdown", "exit"]
    assert switch.lines.index("interface Gi1/0/48") < switch.lines.index("interface Vlan100")


def test_vlan_1_on_auto_leaves_ports_alone():
    switch = FakeSwitch()
    _, done, _ = run_driver(switch, plan())
    assert done["uplink"] is None and "show interfaces status" not in switch.lines


def test_uplink_detection_stops_before_configuring_when_unclear():
    for connected, words in ((("Gi1/0/1", "Gi1/0/48"), "Several ports"), ((), "No port")):
        switch = FakeSwitch(connected=connected)
        with pytest.raises(driver.SetupStopped, match=words) as stopped:
            run_driver(switch, plan(vlan=100))
        assert stopped.value.sent is False and "configure terminal" not in switch.lines


def test_a_named_uplink_accepts_the_long_name_and_trunk_mode():
    switch = FakeSwitch(connected=("Gi1/0/1", "Gi1/0/48"))
    _, done, _ = run_driver(switch, plan(vlan=100, uplink="GigabitEthernet1/0/48", uplink_mode="trunk"))
    assert done["uplink"] == "Gi1/0/48" and "switchport mode trunk" in switch.lines
    assert plan(uplink="port 7").problems()


def test_the_running_config_is_captured_before_and_after_with_secrets_masked(db_session, kit, monkeypatch):
    save(db_session)
    answered_on_console(db_session, kit)
    switch = FakeSwitch()
    started = service.start(db_session, "kit", kit, "op", opener=lambda port, baud: switch)
    service._workers[started["run_id"]].join(10)
    from sqlalchemy import select

    from app.models import AuditEvent
    result = next(r.data_json for r in db_session.scalars(select(AuditEvent).where(AuditEvent.event_type == "kit.switch.result")) if r.data_json.get("phase") == "configure")
    assert "hostname Switch" in result["config_before"] and "hostname lab-sw01" in result["config_after"]
    assert "$9$" not in result["config_after"] and "secret 9 ********" in result["config_after"]
    from app.services.handover import switch_config
    recorded = switch_config(db_session, kit)
    assert recorded and any(line.startswith("+hostname lab-sw01") for line in recorded["diff"])


SECRET_SAMPLES = {
    "username a privilege 15 secret 9 $9$x": "$9$x",
    "username b password 7 0822455D0A16": "0822455D0A16",
    "enable secret 5 $1$y": "$1$y",
    "enable password 7 0822455D0A17": "0822455D0A17",
    " password 7 1511021F0725 extra": "1511021F0725",
    "snmp-server community public RO": "public",
    "snmp-server user bob grp v3 auth sha AuthPass1 priv aes 128 PrivPass2": "AuthPass1",
    "ntp authentication-key 1 md5 abcd 7": "abcd",
    "tacacs-server key 7 03075218050070": "03075218050070",
    " key 7 11584B5643475D": "11584B5643475D",
    " key-string 0 MyKeyString": "MyKeyString",
    " standby 1 authentication md5 key-string 7 Hsrp12345": "Hsrp12345",
    " ppp chap password 0 ChapPass": "ChapPass",
    "ip ftp password 7 FtpPass77": "FtpPass77",
    "crypto isakmp key IsakmpKey address 192.0.2.9": "IsakmpKey",
    "  pre-shared-key local 0 PskLocal": "PskLocal",
    "  wpa-psk ascii 0 WifiPass123": "WifiPass123",
    "  key-hash ssh-rsa 0A1B2C3D4E5F": "0A1B2C3D4E5F",
    " neighbor 192.0.2.2 password 7 BgpPass": "BgpPass",
    "   30820122 300D0609 2A864886 F70D0101": "30820122",
}


def test_sanitize_masks_every_secret_kind():
    text = "hostname sw1\n" + "\n".join(SECRET_SAMPLES) + "\nip ssh version 2\n login local\nservice password-encryption\nno aaa new-model\n"
    masked = driver.sanitize_config(text)
    for line, secret in SECRET_SAMPLES.items():
        assert secret not in masked, line
    for kept in ("hostname sw1", "ip ssh version 2", "login local", "service password-encryption", "no aaa new-model"):
        assert kept in masked
    assert "snmp-server user bob grp v3 auth sha ********" in masked and "PrivPass2" not in masked


def test_a_paged_running_config_is_read_to_the_end(db_session, kit):
    save(db_session)
    answered_on_console(db_session, kit)
    switch = FakeSwitch()
    switch.paged = True
    started = service.start(db_session, "kit", kit, "op", opener=lambda port, baud: switch)
    service._workers[started["run_id"]].join(10)
    from sqlalchemy import select

    from app.models import AuditEvent
    result = next(r.data_json for r in db_session.scalars(select(AuditEvent).where(AuditEvent.event_type == "kit.switch.result")) if r.data_json.get("phase") == "configure")
    assert result["config_after"].rstrip().endswith("end") and "--More--" not in result["config_after"] and switch.lines.count(" ") >= 2


def test_a_log_line_printed_after_the_prompt_does_not_stop_the_setup():
    switch = FakeSwitch()
    switch.late_syslog = True
    start, done, (address, _) = run_driver(switch, plan())
    assert done["saved"] and address == "192.0.2.50"
    assert switch.lines.count("write memory") == 1 and switch.lines.count("show ip ssh") == 1


def test_the_console_line_gets_logging_synchronous_first():
    shown = plan().preview()
    assert shown[1:4] == [" line console 0", " logging synchronous", " exit"]


def test_verify_is_not_marked_sent_when_the_console_phase_failed(db_session, kit, monkeypatch):
    save(db_session)
    answered_on_console(db_session, kit)
    switch = FakeSwitch(refuse=("ip ssh version",))
    started = service.start(db_session, "kit", kit, "op", opener=lambda port, baud: switch)
    service._workers[started["run_id"]].join(10)
    current = service.status(db_session, "kit", kit)
    assert [p["state"] for p in current["phases"]] == ["failed", "todo"]


def test_existing_ssh_keys_are_kept_and_the_setup_completes():
    switch = FakeSwitch()
    switch.keys_exist = True
    start, done, (address, _) = run_driver(switch, plan())
    assert done["saved"] and address == "192.0.2.50"
    assert "no" in switch.lines and "yes" not in switch.lines
    assert "no (keep the existing SSH keys)" in done["sent"]


def test_a_log_line_printed_into_the_running_config_is_removed_and_the_line_rejoined(db_session, kit):
    save(db_session)
    answered_on_console(db_session, kit)
    switch = FakeSwitch()
    switch.syslog_in_config = True
    started = service.start(db_session, "kit", kit, "op", opener=lambda port, baud: switch)
    service._workers[started["run_id"]].join(10)
    from sqlalchemy import select

    from app.models import AuditEvent
    result = next(r.data_json for r in db_session.scalars(select(AuditEvent).where(AuditEvent.event_type == "kit.switch.result")) if r.data_json.get("phase") == "configure")
    for config in (result["config_before"], result["config_after"]):
        assert "\n login\n" in config and "%CDP" not in config and "Oct 22" not in config


def test_strip_syslog_keeps_whole_lines_apart_and_rejoins_split_ones():
    from app.providers.cisco_console_setup import strip_syslog
    assert strip_syslog(" login lo\n*Oct 22 14:42:38.254: %CDP-4-NATIVE_VLAN_MISMATCH: mismatch on Gi1/0/2 (100), with Switch Gi1/0/14 (670).cal\n transport input ssh") == " login local\n transport input ssh"
    assert strip_syslog(" login local\n*Oct 22 14:42:40.000: %SYS-5-CONFIG_I: Configured from console by admin on console\n transport input ssh") == " login local\n transport input ssh"
    assert strip_syslog("hostname sw\n%LINK-3-UPDOWN: Interface Vlan100, changed state to up\nend") == "hostname sw\nend"
    assert strip_syslog("ip domain name lab.local\n") == "ip domain name lab.local\n"
