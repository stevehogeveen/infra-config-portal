from types import SimpleNamespace

import pytest

from app.models import DeviceInventory, SwitchDeviceCredential
from app.services import kit_reset, switch_access, switch_reset


@pytest.fixture
def kit(db_session, monkeypatch, tmp_path):
    db_session.add(DeviceInventory(id="sw-1", device_type="cisco_switch", display_name="Cisco switch 1"))
    db_session.commit()
    switch_access.save_access(db_session, "sw-1", {"host": "192.0.2.50", "username": "admin", "password": "Fixture-Pass-1", "enable_password": "Fixture-Enable-1"})
    files = {name: tmp_path / name for name in ("root", "hash", "guest")}
    for path in files.values():
        path.write_text("secret", encoding="utf-8")
    monkeypatch.setattr(kit_reset, "_server_secrets", lambda device_id: [("ESXi root password", files["root"]),
                                                                          ("ESXi root password (installer copy)", files["hash"]),
                                                                          ("Windows administrator sign-in", files["guest"])])
    monkeypatch.setattr(kit_reset, "_kit", lambda session, profile_id: ([SimpleNamespace(device_id="srv-1", name="HPE DL360 3")],
                                                                        [SimpleNamespace(device_id="sw-1", name="Cisco switch 1")]))
    monkeypatch.setattr(switch_reset, "enabled", lambda: True)
    return files


def test_forget_needs_the_phrase_and_removes_only_kit_passwords(db_session, kit, monkeypatch):
    with pytest.raises(kit_reset.KitResetError):
        kit_reset.forget(db_session, "kit", "op", "forget")
    assert all(path.is_file() for path in kit.values())
    db_session.expire_all()
    monkeypatch.setattr(kit_reset, "summary", lambda session, profile_id: {})
    result = kit_reset.forget(db_session, "kit", "op", "FORGET SIGN-INS")
    assert not any(path.is_file() for path in kit.values())
    assert len(result["removed"]) == 5 and "secret" not in str(result)
    saved = db_session.get(SwitchDeviceCredential, "sw-1").credentials_json
    assert "password" not in saved and "enable_password" not in saved
    assert saved["host"] == "192.0.2.50" and saved["username"] == "admin"


def test_forget_is_refused_when_reset_is_turned_off(db_session, kit, monkeypatch):
    monkeypatch.setattr(switch_reset, "enabled", lambda: False)
    with pytest.raises(kit_reset.KitResetError, match="turned off"):
        kit_reset.forget(db_session, "kit", "op", "FORGET SIGN-INS")
    assert all(path.is_file() for path in kit.values())
