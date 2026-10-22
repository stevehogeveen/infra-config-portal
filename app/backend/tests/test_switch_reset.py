from contextlib import nullcontext
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.models import DeviceInventory
from app.providers import cisco_console_setup as driver
from app.services import switch_access
from app.services import switch_reset as service

ENABLE = "Fixture-Enable-1"
PORTS = [SimpleNamespace(device="COM5", description="USB serial", manufacturer="FTDI", hwid="USB VID:PID=0403:6001", product="",
                         interface="", serial_number=None, location=None, vid=None, pid=None)]


class SetUpSwitch:
    """A console on a switch this app set up: enable password, then the erase and restart prompts."""

    def __init__(self, serial="FOC0000X000", comes_back="wizard", enable=ENABLE, refuse_erase=False, odd_question=False, start="exec"):
        self.serial, self.comes_back, self.enable, self.refuse_erase, self.odd_question = serial, comes_back, enable, refuse_erase, odd_question
        self.start = start
        self.out, self.lines, self.mode, self.waiting, self.closed = b"", [], "exec", None, False

    @property
    def in_waiting(self):
        return len(self.out)

    def read(self, size=1):
        data, self.out = self.out[:size], self.out[size:]
        return data

    def _say(self, text):
        self.out += text.encode()

    def _prompt(self):
        self._say("\nlab-sw01" + {"exec": ">", "priv": "#", "config": "(config)#"}[self.mode])

    def write(self, data):
        line = data.decode().rstrip("\r")
        self.lines.append(line)
        waiting, self.waiting = self.waiting, None
        if waiting == "enable":
            if line == self.enable:
                self.mode = "priv"
            else:
                self._say("\n% Access denied\n")
            return self._prompt() or len(data)
        if waiting == "erase-confirm":
            self._say("[OK]\nErase of nvram: complete")
            return self._prompt() or len(data)
        if waiting == "delete-name":
            self.waiting = "delete-confirm"
            self._say("\nDelete flash:/vlan.dat? [confirm]")
            return len(data)
        if waiting == "delete-confirm":
            return self._prompt() or len(data)
        if waiting == "save":
            self.waiting = "reload-confirm"
            self._say("\nReload command is being issued on Active unit, this will reload the whole stack\nProceed with reload? [confirm]")
            return len(data)
        if waiting == "reload-confirm":
            self._say("\n\nInitializing Hardware...\nBooting Cisco IOS Software...\n\n")
            if self.comes_back == "wizard":
                self._say("         --- System Configuration Dialog ---\n\nWould you like to enter the initial configuration dialog? [yes/no]: ")
            elif self.comes_back == "prompt":
                self._say("\nPress RETURN to get started!\n")
                self.mode, self.comes_back = "exec", "configured"
            return len(data)
        if self.comes_back == "configured" and line == "":
            return self._prompt() or len(data)
        if line == "enable" and self.mode == "exec":
            self.waiting = "enable"
            self._say("\nPassword: ")
            return len(data)
        if line == "write erase":
            if self.refuse_erase:
                self._say("\n% Permission denied\n")
                return self._prompt() or len(data)
            self.waiting = "erase-confirm"
            self._say("\nErasing the nvram filesystem will remove all configuration files! Continue? [confirm]")
            return len(data)
        if line == "delete flash:vlan.dat":
            self.waiting = "delete-name"
            self._say("\nDelete filename [vlan.dat]? ")
            return len(data)
        if self.start == "wizard":
            self._say("\nWould you like to enter the initial configuration dialog? [yes/no]: ")
            return len(data)
        if line == "reload" and self.odd_question:
            self.waiting = "odd"
            self._say("\nDo you want to reload the whole stack and erase the boot variable? [yes/no]: ")
            return len(data)
        if line == "reload":
            self.waiting = "save"
            self._say("\n\nSystem configuration has been modified. Save? [yes/no]: ")
            return len(data)
        if line.startswith("show version | include"):
            self._say(f"\nSystem Serial Number               : {self.serial}")
        if line == "end":
            self.mode = "priv"
        self._prompt()
        return len(data)

    def close(self):
        self.closed = True


def erase(switch, enable=ENABLE):
    console = driver.Console(switch)
    driver.wake_for_reset(console, enable)
    return driver.factory_erase(console, boot_timeout=5)


def test_erase_answers_each_prompt_once_and_waits_for_the_setup_dialog():
    switch = SetUpSwitch()
    done = erase(switch)
    assert done["factory"] is True
    assert [line for line in switch.lines if line in {"write erase", "delete flash:vlan.dat", "reload"}] == ["write erase", "delete flash:vlan.dat", "reload"]
    assert "no" in switch.lines and "yes" not in switch.lines  # running settings never saved
    assert ENABLE not in "\n".join(done["sent"])


def test_a_switch_that_comes_back_configured_is_not_called_factory():
    assert erase(SetUpSwitch(comes_back="prompt"))["factory"] is False


def test_a_refused_erase_never_restarts_the_switch():
    switch = SetUpSwitch(refuse_erase=True)
    with pytest.raises(driver.SetupStopped) as stopped:
        erase(switch)
    assert stopped.value.sent and "reload" not in switch.lines


def test_an_unexpected_question_is_cancelled_never_answered():
    switch = SetUpSwitch(odd_question=True)
    with pytest.raises(driver.SetupStopped, match="unexpected question"):
        erase(switch)
    after = switch.lines[switch.lines.index("reload") + 1:]
    assert after == ["\x03"]


def test_waking_never_starts_with_enter_and_a_factory_switch_is_left_alone():
    switch = SetUpSwitch(start="wizard")
    with pytest.raises(driver.SetupStopped, match="nothing to erase|no settings to erase") as stopped:
        erase(switch)
    assert switch.lines[0] == "\x03" and not stopped.value.sent
    assert "write erase" not in switch.lines and "no" not in switch.lines


def test_a_wrong_enable_password_stops_before_anything_is_sent():
    switch = SetUpSwitch()
    with pytest.raises(driver.SetupStopped) as stopped:
        erase(switch, enable="Wrong-Enable-9")
    assert not stopped.value.sent and "write erase" not in switch.lines


# ---------------------------------------------------------------- service

@pytest.fixture
def kit(db_session, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from app.providers.probe_cache import record_probe_result

    db_session.add(DeviceInventory(id="sw-1", device_type="cisco_switch", display_name="Cisco switch 1"))
    db_session.commit()
    monkeypatch.setattr(service, "_session_factory", lambda: sessionmaker(bind=db_session.get_bind()))
    monkeypatch.setattr(service, "_policy_blockers", lambda: [])
    monkeypatch.setattr(service, "enabled", lambda: True)
    monkeypatch.setattr(service, "_known_serial", lambda session, device_id: "FOC0000X000")
    monkeypatch.setattr("app.services.runtime_write_scope.dispatch_lease", lambda action: nullcontext())
    monkeypatch.setattr("app.providers.console_bridge.list_ports", lambda: PORTS)
    record_probe_result(switch_access.CONSOLE_PROVIDER, {"port": "COM5", "baud": 9600, "answered": True, "prompt_state": "exec",
                                                         "checked_at": datetime.now(UTC).isoformat()}, scope="sw-1")
    switch_access._remember_console(db_session, "sw-1", "COM5", 9600)
    switch_access.save_access(db_session, "sw-1", {"host": "192.0.2.50", "username": "admin", "password": "Fixture-Pass-1", "enable_password": ENABLE})
    return "sw-1"


def test_reset_needs_the_typed_name_then_erases_once_and_verifies(db_session, kit):
    reviewed = service.review(db_session, kit)
    assert reviewed["ready"] and reviewed["phrase"] == "ERASE Cisco switch 1", reviewed["blockers"]
    switch = SetUpSwitch()
    with pytest.raises(service.SwitchResetError, match="ERASE Cisco switch 1"):
        service.start(db_session, "kit", kit, "op", "erase", opener=lambda port, baud: switch)
    assert switch.lines == []
    started = service.start(db_session, "kit", kit, "op", "ERASE Cisco switch 1", opener=lambda port, baud: switch)
    service._workers[started["run_id"]].join(10)
    assert switch.closed and switch.lines.count("write erase") == 1
    done = service.advance(db_session, "kit", kit, "op")
    assert done["state"] == "verified" and not done["active"]
    with pytest.raises(service.SwitchResetError):  # already factory: nothing to erase
        db_session.expire_all()
        from app.providers.probe_cache import record_probe_result
        record_probe_result(switch_access.CONSOLE_PROVIDER, {"port": "COM5", "baud": 9600, "answered": True, "prompt_state": "setup-wizard",
                                                             "checked_at": datetime.now(UTC).isoformat()}, scope=kit)
        service.start(db_session, "kit", kit, "op", "ERASE Cisco switch 1", opener=lambda port, baud: switch)


def test_a_different_switch_on_the_cable_is_not_erased(db_session, kit, monkeypatch):
    monkeypatch.setattr(service, "_known_serial", lambda session, device_id: "FOC1111Y111")
    switch = SetUpSwitch(serial="FOC0000X000")
    started = service.start(db_session, "kit", kit, "op", "ERASE Cisco switch 1", opener=lambda port, baud: switch)
    service._workers[started["run_id"]].join(10)
    current = service.status(db_session, "kit", kit)
    assert current["state"] == "needs_attention" and "not the one" in current["message"]
    assert "write erase" not in switch.lines


def test_reset_is_refused_when_the_lab_has_it_turned_off(db_session, kit, monkeypatch):
    monkeypatch.setattr(service, "enabled", lambda: False)
    with pytest.raises(service.SwitchResetError, match="turned off"):
        service.start(db_session, "kit", kit, "op", "ERASE Cisco switch 1", opener=lambda port, baud: SetUpSwitch())


def test_the_typed_scope_phrase_is_never_handed_out(db_session):
    from app.services import runtime_write_scope

    preview = runtime_write_scope.preview(db_session, "op", "switch_reset_only")
    assert preview["confirmation_phrase"] == "" and preview["typed_phrase"] is True
    assert any("turned off" in b or "local-lab-readwrite" in b for b in preview["blockers"])


def test_a_switch_without_a_recorded_serial_cannot_be_reset(db_session, kit, monkeypatch):
    monkeypatch.setattr(service, "_known_serial", lambda session, device_id: None)
    reviewed = service.review(db_session, kit)
    assert not reviewed["ready"] and any("serial" in b for b in reviewed["blockers"])


def test_start_needs_exactly_the_switch_reset_permission(db_session, kit, monkeypatch):
    monkeypatch.undo()
    from sqlalchemy.orm import sessionmaker
    monkeypatch.setattr(service, "_session_factory", lambda: sessionmaker(bind=db_session.get_bind()))
    monkeypatch.setattr(service, "enabled", lambda: True)
    monkeypatch.setattr(service, "_known_serial", lambda session, device_id: "FOC0000X000")
    monkeypatch.setattr("app.providers.console_bridge.list_ports", lambda: PORTS)
    monkeypatch.setattr("app.services.runtime_write_scope.runtime_override", lambda: "vm_deploy_only")
    switch = SetUpSwitch()
    reviewed = service.review(db_session, kit)
    assert not any("scope" in b for b in reviewed["permission"])  # the dialog acquires it
    with pytest.raises(service.SwitchResetError):
        service.start(db_session, "kit", kit, "op", "ERASE Cisco switch 1", opener=lambda port, baud: switch)
    assert switch.lines == []
