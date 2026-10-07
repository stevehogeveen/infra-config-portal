import hashlib
import io
import json
import stat
from zipfile import ZipFile, ZipInfo

import pytest

from app.services.firmware_packages import FirmwarePackageError
from app.services.firmware_payload import inspect_ilo_payload


def metadata():
    return {
        "PackageFormat": "FWPKG-v2",
        "UpdatableBy": ["Bmc"],
        "Devices": {
            "Device": [
                {
                    "DeviceName": "iLO 5",
                    "Version": "3.19",
                    "Target": "fixture-target",
                    "FirmwareImages": [
                        {
                            "DirectFlashOk": True,
                            "Type": "Firmware",
                            "FileName": "ilo.bin",
                            "ServerPowerOff": False,
                            "SysPowerON": False,
                        }
                    ],
                }
            ]
        },
    }


def archive(data=None, extras=()):
    stream = io.BytesIO()
    with ZipFile(stream, "w") as z:
        z.writestr("payload.json", json.dumps(metadata() if data is None else data))
        z.writestr("ilo.bin", b"offline binary")
        for name, content in extras:
            z.writestr(name, content)
    stream.seek(0)
    return stream


def test_binary_identity_and_reset_scope():
    result = inspect_ilo_payload(archive(), "3.19")
    assert result["binary"]["sha256"] == hashlib.sha256(b"offline binary").hexdigest()
    assert result["ilo_reset_expected"] is True
    assert result["host_reboot_authorized"] is False
    assert result["signature_verified"] is False
    assert result["requires_target_match"] is True
    assert result["host_power_requirements_known"] is True


@pytest.mark.parametrize("value", [None, 0, "false", True])
def test_power_requirement_is_strict_boolean(value):
    data = metadata()
    data["Devices"]["Device"][0]["FirmwareImages"][0]["SysPowerON"] = value
    with pytest.raises(FirmwarePackageError):
        inspect_ilo_payload(archive(data), "3.19")


@pytest.mark.parametrize("name", ["../escape", "/absolute", "a/b", "C:drive", "ILO.BIN"])
def test_unsafe_and_duplicate_names(name):
    with pytest.raises(FirmwarePackageError):
        inspect_ilo_payload(archive(extras=[(name, b"bad")]), "3.19")


def test_symlink_rejected():
    link = ZipInfo("link")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(FirmwarePackageError):
        inspect_ilo_payload(archive(extras=[(link, b"ilo.bin")]), "3.19")


@pytest.mark.parametrize("change", ["agent", "version", "power", "direct", "missing"])
def test_inconsistent_or_unsupported_declarations(change):
    data = metadata()
    device = data["Devices"]["Device"][0]
    if change == "agent":
        data["UpdatableBy"] = ["RuntimeAgent"]
    elif change == "version":
        device["Version"] = "9.0"
    elif change == "power":
        device["FirmwareImages"][0]["ServerPowerOff"] = True
    elif change == "direct":
        device["FirmwareImages"][0]["DirectFlashOk"] = "true"
    else:
        device["FirmwareImages"][0]["FileName"] = "missing.bin"
    with pytest.raises(FirmwarePackageError):
        inspect_ilo_payload(archive(data), "3.19")


def test_metadata_limit(monkeypatch):
    monkeypatch.setattr("app.services.firmware_payload.MAX_METADATA_BYTES", 10)
    with pytest.raises(FirmwarePackageError, match="metadata exceeds"):
        inspect_ilo_payload(archive(), "3.19")
