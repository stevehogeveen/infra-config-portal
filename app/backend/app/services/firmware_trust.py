"""Authenticate supported iLO BINs via HPE's signed SPP RPMs, offline.

The RPM signature and authenticated payload digest bind these bytes to HPE.
This does not validate the FWPKG wrapper or its embedded signature, nor establish
target applicability. No vendor executable is installed, imported or executed.
"""

import hashlib
import json
import os
import re
import select
import subprocess
import tempfile
import time
from pathlib import Path

import pycdlib

from app.services.firmware_packages import FirmwarePackageError, media_path, package_unchanged
from app.services.firmware_standalone import inspect_standalone
from app.services.firmware_payload import inspect_ilo_payload, _unique_object
from app.services.firmware_catalog import ilo_component

RPM_PATH = "/prerequisite/firmware-ilo5-1.48-3.1.x86_64.rpm"
BIN_MEMBER = "./usr/lib/x86_64-linux-gnu/firmware-ilo5-1.48-3.1/ilo5_148.bin"
KEY_HASHES = {
    "hpePublicKey2048_key1.pub": "3fe679e5ca629526e3927b7aa7d58bc58f173d49cb1c00f163eea761c39b718e",
    "hpePublicKey2048_key2.pub": "60888e9309eda5f45428605c80d7210fed5fe0999a774b1a480da8fafeceb902",
}
KEY_ROOT = Path(__file__).resolve().parents[1] / "data" / "hpe"
MAX_RPM_BYTES = 64 * 1024**2
MAX_BIN_BYTES = 64 * 1024**2


def inspect_spp_bridge(package: dict, version: str = "1.48") -> dict:
    component = ilo_component(version)
    if not package_unchanged(package):
        raise FirmwarePackageError("Selected SPP changed. Select it again.")
    iso = pycdlib.PyCdlib()
    location = component.package_path
    try:
        iso.open(str(media_path(package["path"])))
        record = iso.get_record(rr_path=location)
        if record.is_symlink() or not 0 < record.data_length <= MAX_RPM_BYTES:
            raise FirmwarePackageError("SPP bridge package is unsafe or too large.")
        digest = hashlib.sha256()
        count = 0
        with iso.open_file_from_iso(rr_path=location) as stream:
            while chunk := stream.read(1024**2):
                count += len(chunk)
                if count > MAX_RPM_BYTES:
                    raise FirmwarePackageError("SPP bridge exceeds the inspection limit.")
                digest.update(chunk)
            stream.seek(0)
            payload = inspect_ilo_payload(stream, version)
        if count != record.data_length or not package_unchanged(package):
            raise FirmwarePackageError("SPP changed during bridge inspection.")
        return {
            "source_kind": "spp-prerequisite" if version == "1.48" else "spp-component",
            "path": location,
            "sha256": digest.hexdigest(),
            "payload": payload,
            "size_bytes": count,
            "can_apply": False,
        }
    except FirmwarePackageError:
        raise
    except Exception:
        raise FirmwarePackageError("SPP bridge could not be inspected safely.") from None
    finally:
        try:
            iso.close()
        except Exception:
            pass


def _current_selection(package, selection):
    if selection.get("source_kind") == "spp-prerequisite":
        return inspect_spp_bridge(package)
    if selection.get("source_kind") == "spp-component":
        return inspect_spp_bridge(package, selection["payload"]["declared_version"])
    return inspect_standalone(selection["path"])


def _signature_ok(result) -> bool:
    output = result.stdout.decode("utf-8", errors="replace")
    return (
        result.returncode == 0
        and re.search(r"^\s*Header V4 RSA/SHA384 Signature, key ID 74c3a4a2: OK$", output, re.M)
        is not None
        and re.search(r"^\s*Header SHA256 digest: OK$", output, re.M) is not None
        and re.search(r"^\s*Payload SHA256 digest: OK$", output, re.M) is not None
        and not any(word in output.upper() for word in ("NOKEY", "NOT OK", "BAD", "NOTTRUSTED"))
    )


def _run(args):
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=30,
        check=False,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
    )


def _member_identity(rpm: Path, member: str, limit: int, capture: bool = False) -> dict:
    # Stream only the exact member; no archive filenames become filesystem paths.
    process = subprocess.Popen(
        ["/usr/bin/bsdtar", "-xOf", str(rpm), member],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
    )
    try:
        deadline = time.monotonic() + 30
        digest = hashlib.sha256()
        size = 0
        content = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([process.stdout], [], [], remaining)[0]:
                raise FirmwarePackageError("Signed RPM binary inspection timed out.")
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise FirmwarePackageError("Signed RPM binary exceeds the limit.")
            digest.update(chunk)
            if capture:
                content.extend(chunk)
        process.wait(timeout=max(0.01, deadline - time.monotonic()))
        if process.returncode or size <= 0:
            raise FirmwarePackageError("Signed RPM binary is missing or unreadable.")
        result = {"sha256": digest.hexdigest(), "size_bytes": size}
        if capture:
            result["content"] = bytes(content)
        return result
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        process.stdout.close()


def _binary_identity(rpm: Path, version: str = "1.48") -> dict:
    return _member_identity(rpm, ilo_component(version).binary_member, MAX_BIN_BYTES)


def _authenticated_declaration(rpm: Path, selected: dict) -> dict:
    component = ilo_component(selected.get("declared_version", "1.48"))
    member = component.binary_member.rsplit("/", 1)[0] + "/payload.json"
    result = _member_identity(rpm, member, 1024**2, capture=True)
    metadata = json.loads(result["content"], object_pairs_hook=_unique_object)
    devices = metadata.get("Devices", {}).get("Device", [])
    if not isinstance(devices, list) or not 1 <= len(devices) <= 16:
        raise FirmwarePackageError("Signed bridge target declaration is ambiguous.")
    targets = []
    for device in devices:
        images = device.get("FirmwareImages", [])
        target = device.get("Target")
        if (
            device.get("DeviceName") != "iLO 5"
            or device.get("Version") != component.version
            or not isinstance(target, str)
            or not target
            or target in targets
            or not isinstance(images, list)
            or len(images) != 1
        ):
            raise FirmwarePackageError(
                "Signed bridge target/version differs from the selected package."
            )
        targets.append(target)
        image = images[0]
        if (
            image.get("FileName") != component.filename
            or image.get("DirectFlashOk") is not True
            or image.get("ServerPowerOff") is not False
            or image.get("SysPowerON") is not False
            or image.get("ResetRequired") is not False
            or image.get("Type") != "Firmware"
        ):
            raise FirmwarePackageError(
                "Signed bridge does not declare the supported direct-flash scope."
            )
    if sorted(targets) != selected.get("declared_targets"):
        raise FirmwarePackageError(
            "Signed bridge target/version differs from the selected package."
        )
    if not isinstance(metadata.get("DeviceClass"), str) or not metadata["DeviceClass"]:
        raise FirmwarePackageError("Signed firmware device class is missing.")
    return {
        "metadata_sha256": result["sha256"],
        "targets": sorted(targets),
        "device_class": metadata["DeviceClass"],
        "version": component.version,
        "direct_flash": True,
        "host_power_change_required": False,
        "ilo_reset_expected": True,
    }


def verify_bridge_from_spp(package: dict, selection: dict) -> dict:
    if not package_unchanged(package):
        raise FirmwarePackageError("Selected SPP changed. Select it again.")
    current = _current_selection(package, selection)
    if current["sha256"] != selection.get("sha256"):
        raise FirmwarePackageError("Selected bridge changed. Select it again.")
    component = ilo_component(current["payload"]["declared_version"])
    try:
        with tempfile.TemporaryDirectory(prefix="firmware-trust-") as directory:
            root = Path(directory)
            rpm = root / "bridge.rpm"
            iso = pycdlib.PyCdlib()
            try:
                iso.open(str(media_path(package["path"])))
                record = iso.get_record(rr_path=component.rpm_path)
                if record.is_symlink() or not 0 < record.data_length <= MAX_RPM_BYTES:
                    raise FirmwarePackageError("SPP prerequisite RPM is unsafe or too large.")
                with (
                    iso.open_file_from_iso(rr_path=component.rpm_path) as source,
                    rpm.open("wb") as destination,
                ):
                    count = 0
                    while chunk := source.read(1024**2):
                        count += len(chunk)
                        if count > MAX_RPM_BYTES:
                            raise FirmwarePackageError("SPP prerequisite RPM exceeds the limit.")
                        destination.write(chunk)
                if count != record.data_length:
                    raise FirmwarePackageError("SPP prerequisite RPM is truncated.")
            finally:
                iso.close()
            for name, expected in KEY_HASHES.items():
                key = KEY_ROOT / name
                if hashlib.sha256(key.read_bytes()).hexdigest() != expected:
                    raise FirmwarePackageError(
                        "Bundled HPE public key does not match the pinned key."
                    )
                if _run(
                    ["/usr/bin/rpmkeys", "--dbpath", str(root / "db"), "--import", str(key)]
                ).returncode:
                    raise FirmwarePackageError("HPE public key import failed.")
            checked = _run(
                [
                    "/usr/bin/rpmkeys",
                    "--dbpath",
                    str(root / "db"),
                    "--checksig",
                    "--verbose",
                    str(rpm),
                ]
            )
            if not _signature_ok(checked):
                raise FirmwarePackageError(
                    "HPE RPM signature or authenticated payload digest did not verify."
                )
            binary = (
                _binary_identity(rpm)
                if component.version == "1.48"
                else _binary_identity(rpm, component.version)
            )
            selected = current["payload"]["binary"]
            if any(binary[key] != selected[key] for key in ("sha256", "size_bytes")):
                raise FirmwarePackageError(
                    "Selected binary differs from the HPE-signed bridge RPM."
                )
            declaration = _authenticated_declaration(rpm, current["payload"])
            rpm_digest = hashlib.sha256(rpm.read_bytes()).hexdigest()
    except FirmwarePackageError:
        raise
    except Exception:
        raise FirmwarePackageError(
            "Offline HPE trust verification is unavailable or failed safely."
        ) from None
    if (
        not package_unchanged(package)
        or _current_selection(package, selection)["sha256"] != current["sha256"]
    ):
        raise FirmwarePackageError("Selected media changed during verification.")
    return {
        "binary_authenticated": True,
        "authentication_method": "hpe_signed_rpm_exact_binary_match",
        "rpm_path": component.rpm_path,
        "rpm_sha256": rpm_digest,
        "signing_key_id": "74c3a4a2",
        "binary": binary,
        "component_sha256": current["sha256"],
        "fwpkg_signature_verified": False,
        "metadata_authenticated": False,
        "authenticated_declaration": declaration,
        "applicability_verified": False,
        "can_apply": False,
    }
