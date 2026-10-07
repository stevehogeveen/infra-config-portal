from types import SimpleNamespace
import hashlib
import io
import json

import pytest

from app.services.firmware_packages import FirmwarePackageError
from app.services import firmware_trust as trust


GOOD = b"""bridge.rpm:
    Header V4 RSA/SHA384 Signature, key ID 74c3a4a2: OK
    Header SHA256 digest: OK
    Payload SHA256 digest: OK
"""


def test_requires_signature_and_authenticated_payload():
    assert trust._signature_ok(SimpleNamespace(returncode=0, stdout=GOOD))


@pytest.mark.parametrize(
    "change", [None, "target", "version", "class", "power", "direct", "duplicate"]
)
def test_signed_declaration_scope(monkeypatch, change):
    image = {
        "FileName": "ilo5_148.bin",
        "DirectFlashOk": True,
        "ServerPowerOff": False,
        "SysPowerON": False,
        "ResetRequired": False,
        "Type": "Firmware",
    }
    device = {
        "DeviceName": "iLO 5",
        "Version": "1.48",
        "Target": "fixture-target",
        "FirmwareImages": [image],
    }
    metadata = {"DeviceClass": "fixture-class", "Devices": {"Device": [device]}}
    if change == "target":
        device["Target"] = "different"
    elif change == "version":
        device["Version"] = "2.78"
    elif change == "class":
        metadata["DeviceClass"] = ""
    elif change == "power":
        image["ServerPowerOff"] = True
    elif change == "direct":
        image["DirectFlashOk"] = "true"
    raw = json.dumps(metadata).encode()
    if change == "duplicate":
        raw = raw.replace(b'"Version": "1.48"', b'"Version": "1.37", "Version": "1.48"')
    monkeypatch.setattr(
        trust, "_member_identity", lambda *a, **k: {"content": raw, "sha256": "a" * 64}
    )
    if change:
        with pytest.raises((FirmwarePackageError, ValueError)):
            trust._authenticated_declaration(None, {"declared_targets": ["fixture-target"]})
    else:
        result = trust._authenticated_declaration(None, {"declared_targets": ["fixture-target"]})
        assert result["host_power_change_required"] is False
        assert result["ilo_reset_expected"] is True
        assert result["metadata_sha256"] == "a" * 64


@pytest.mark.parametrize(
    "output,code",
    [
        (GOOD, 1),
        (b"digests OK", 0),
        (GOOD.replace(b"74c3a4a2", b"deadbeef"), 0),
        (GOOD.replace(b"SHA384 Signature", b"SHA1 Signature"), 0),
        (GOOD.replace(b"Payload SHA256 digest: OK", b""), 0),
        (GOOD.replace(b"Header SHA256 digest: OK", b""), 0),
        (GOOD + b"BAD signature", 0),
        (GOOD + b"NOKEY", 0),
    ],
)
def test_rejects_missing_untrusted_or_failed_signature(output, code):
    assert not trust._signature_ok(SimpleNamespace(returncode=code, stdout=output))


def test_missing_or_changed_selection_never_reaches_tool(monkeypatch):
    monkeypatch.setattr(trust, "package_unchanged", lambda p: False)
    monkeypatch.setattr(trust, "_run", lambda args: pytest.fail("must not execute"))
    with pytest.raises(FirmwarePackageError, match="SPP changed"):
        trust.verify_bridge_from_spp({}, {})
    monkeypatch.setattr(trust, "package_unchanged", lambda p: True)
    monkeypatch.setattr(trust, "_current_selection", lambda p, s: {"sha256": "different"})
    with pytest.raises(FirmwarePackageError, match="bridge changed"):
        trust.verify_bridge_from_spp({}, {"sha256": "old"})


def test_unsupported_bridge_version_rejected(monkeypatch):
    monkeypatch.setattr(trust, "package_unchanged", lambda p: True)
    monkeypatch.setattr(
        trust,
        "_current_selection",
        lambda p, s: {
            "sha256": "same",
            "payload": {"declared_version": "2.78"},
        },
    )
    with pytest.raises(FirmwarePackageError, match="no supported installation adapter"):
        trust.verify_bridge_from_spp({}, {"sha256": "same"})


@pytest.fixture(params=["1.48", "3.19"])
def verified_fixture(monkeypatch, tmp_path, request):
    class ISO:
        def open(self, path):
            pass

        def close(self):
            pass

        def get_record(self, **kwargs):
            return SimpleNamespace(data_length=7, is_symlink=lambda: False)

        def open_file_from_iso(self, **kwargs):
            return io.BytesIO(b"fixture")

    binary = {"sha256": "a" * 64, "size_bytes": 12}
    selection = {
        "path": "bridge.fwpkg",
        "sha256": "b" * 64,
        "payload": {"declared_version": request.param, "binary": binary},
    }
    monkeypatch.setattr(trust.pycdlib, "PyCdlib", ISO)
    monkeypatch.setattr(trust, "package_unchanged", lambda p: True)
    monkeypatch.setattr(trust, "media_path", lambda p: tmp_path / p)
    monkeypatch.setattr(trust, "_current_selection", lambda p, s: selection)
    monkeypatch.setattr(trust, "_run", lambda args: SimpleNamespace(returncode=0, stdout=GOOD))
    monkeypatch.setattr(trust, "_binary_identity", lambda path, *args: binary)
    monkeypatch.setattr(
        trust, "_authenticated_declaration", lambda path, selected: {"fixture": True}
    )
    return {"path": "fixture.iso"}, selection


def test_verifies_exact_binary_not_wrapper_or_applicability(verified_fixture):
    result = trust.verify_bridge_from_spp(*verified_fixture)
    assert result["binary_authenticated"] is True
    assert result["rpm_sha256"] == hashlib.sha256(b"fixture").hexdigest()
    assert result["fwpkg_signature_verified"] is False
    assert result["metadata_authenticated"] is False
    assert result["applicability_verified"] is False
    assert result["can_apply"] is False


def test_binary_mismatch_fails_even_with_same_version(verified_fixture, monkeypatch):
    monkeypatch.setattr(
        trust, "_binary_identity", lambda path, *args: {"sha256": "c" * 64, "size_bytes": 12}
    )
    with pytest.raises(FirmwarePackageError, match="differs"):
        trust.verify_bridge_from_spp(*verified_fixture)


def test_key_tamper_prevents_signature_tool(verified_fixture, monkeypatch, tmp_path):
    monkeypatch.setattr(trust, "KEY_ROOT", tmp_path)
    for name in trust.KEY_HASHES:
        (tmp_path / name).write_bytes(b"untrusted key")
    monkeypatch.setattr(trust, "_run", lambda args: pytest.fail("must not execute"))
    with pytest.raises(FirmwarePackageError, match="pinned key"):
        trust.verify_bridge_from_spp(*verified_fixture)


def test_signature_failure_never_extracts_binary(verified_fixture, monkeypatch):
    def command(args):
        return SimpleNamespace(returncode=0, stdout=b"digests OK" if "--checksig" in args else b"")

    monkeypatch.setattr(trust, "_run", command)
    monkeypatch.setattr(trust, "_binary_identity", lambda p: pytest.fail("must not extract"))
    with pytest.raises(FirmwarePackageError, match="signature"):
        trust.verify_bridge_from_spp(*verified_fixture)


def test_media_changed_after_verification_fails(verified_fixture, monkeypatch):
    results = iter([True, False])
    monkeypatch.setattr(trust, "package_unchanged", lambda p: next(results))
    with pytest.raises(FirmwarePackageError, match="changed during"):
        trust.verify_bridge_from_spp(*verified_fixture)


@pytest.mark.parametrize(
    "change",
    [None, "duplicate-target", "wrong-version", "wrong-file", "host-reset", "missing-target"],
)
def test_319_all_signed_targets_must_declare_same_image(monkeypatch, change):
    targets = ["target-a", "target-b", "target-c"]
    devices = [
        {
            "DeviceName": "iLO 5",
            "Version": "3.19",
            "Target": target,
            "FirmwareImages": [
                {
                    "FileName": "ilo5_319.bin",
                    "Type": "Firmware",
                    "DirectFlashOk": True,
                    "ServerPowerOff": False,
                    "SysPowerON": False,
                    "ResetRequired": False,
                }
            ],
        }
        for target in targets
    ]
    if change == "duplicate-target":
        devices[2]["Target"] = "target-a"
    elif change == "wrong-version":
        devices[2]["Version"] = "1.48"
    elif change == "wrong-file":
        devices[2]["FirmwareImages"][0]["FileName"] = "ilo5_148.bin"
    elif change == "host-reset":
        devices[2]["FirmwareImages"][0]["ResetRequired"] = True
    elif change == "missing-target":
        devices.pop()
    raw = json.dumps({"DeviceClass": "fixture-class", "Devices": {"Device": devices}}).encode()

    def member(rpm, path, *args, **kwargs):
        assert path == "./usr/lib/x86_64-linux-gnu/firmware-ilo5-3.19-1.1/payload.json"
        return {"content": raw, "sha256": "a" * 64}

    monkeypatch.setattr(trust, "_member_identity", member)
    selected = {"declared_version": "3.19", "declared_targets": targets}
    if change:
        with pytest.raises(FirmwarePackageError):
            trust._authenticated_declaration(None, selected)
    else:
        declaration = trust._authenticated_declaration(None, selected)
        assert declaration["targets"] == targets
        assert declaration["version"] == "3.19"
