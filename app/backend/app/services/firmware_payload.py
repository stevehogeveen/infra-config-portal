"""Inspect FWPKG ZIP members without extracting or executing vendor code."""

import hashlib
import json
import stat
from pathlib import PurePosixPath
from zipfile import ZipFile

from app.services.firmware_packages import FirmwarePackageError

MAX_MEMBERS = 64
MAX_EXPANDED_BYTES = 256 * 1024**2
MAX_METADATA_BYTES = 1024**2


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise FirmwarePackageError("Duplicate firmware metadata key.")
        result[key] = value
    return result


def inspect_ilo_payload(stream, expected_version: str | None = None) -> dict:
    try:
        with ZipFile(stream) as archive:
            members = archive.infolist()
            if len(members) > MAX_MEMBERS or sum(m.file_size for m in members) > MAX_EXPANDED_BYTES:
                raise FirmwarePackageError("Firmware archive exceeds inspection limits.")
            names = set()
            for member in members:
                name = member.filename
                if (
                    not name
                    or PurePosixPath(name).name != name
                    or name in {".", ".."}
                    or any(c in name for c in ("\\", ":", "\x00"))
                    or name.casefold() in names
                    or member.flag_bits & 1
                    or stat.S_ISLNK(member.external_attr >> 16)
                    or member.file_size > max(1, member.compress_size) * 200
                ):
                    raise FirmwarePackageError("Unsafe, duplicate or unsupported archive member.")
                names.add(name.casefold())
            metadata_member = archive.getinfo("payload.json")
            if metadata_member.file_size > MAX_METADATA_BYTES:
                raise FirmwarePackageError("Firmware metadata exceeds inspection limits.")
            raw = archive.read(metadata_member)
            metadata = json.loads(raw, object_pairs_hook=_unique_object)
            if metadata.get("PackageFormat") != "FWPKG-v2" or metadata.get("UpdatableBy") != [
                "Bmc"
            ]:
                raise FirmwarePackageError("Unsupported package format or update agent.")
            devices = metadata["Devices"]["Device"]
            if not isinstance(devices, list) or not 1 <= len(devices) <= 16:
                raise FirmwarePackageError("Firmware target list is missing or ambiguous.")
            targets = []
            filenames = set()
            power_requirements_known = True
            for device in devices:
                if expected_version is None:
                    expected_version = device.get("Version")
                if (
                    not isinstance(expected_version, str)
                    or not expected_version
                    or len(expected_version) > 64
                ):
                    raise FirmwarePackageError("Firmware version declaration is missing.")
                if (
                    device.get("DeviceName") != "iLO 5"
                    or device.get("Version") != expected_version
                    or not isinstance(device.get("Target"), str)
                    or not device["Target"]
                    or device["Target"] in targets
                ):
                    raise FirmwarePackageError(
                        "Firmware target/version declaration is inconsistent."
                    )
                images = device.get("FirmwareImages")
                if not isinstance(images, list) or len(images) != 1:
                    raise FirmwarePackageError("One direct-flash image per target is required.")
                image = images[0]
                if (
                    image.get("DirectFlashOk") is not True
                    or image.get("Type") != "Firmware"
                    or any(
                        key in image and image[key] is not False
                        for key in ("ServerPowerOff", "SysPowerON")
                    )
                ):
                    raise FirmwarePackageError(
                        "Image is not a supported direct iLO flash declaration."
                    )
                power_requirements_known = power_requirements_known and all(
                    key in image for key in ("ServerPowerOff", "SysPowerON")
                )
                filename = image.get("FileName")
                if not isinstance(filename, str) or not filename.lower().endswith(".bin"):
                    raise FirmwarePackageError("An explicit BIN image is required.")
                filenames.add(filename)
                targets.append(device["Target"])
            if len(filenames) != 1:
                raise FirmwarePackageError("Targets refer to different binary images.")
            filename = next(iter(filenames))
            member = archive.getinfo(filename)
            if member.file_size <= 0:
                raise FirmwarePackageError("Firmware binary is empty.")
            digest = hashlib.sha256()
            count = 0
            with archive.open(member) as binary:
                while chunk := binary.read(1024**2):
                    count += len(chunk)
                    if count > MAX_EXPANDED_BYTES:
                        raise FirmwarePackageError("Firmware binary exceeds inspection limits.")
                    digest.update(chunk)
            if count != member.file_size:
                raise FirmwarePackageError("Firmware binary is truncated.")
            return {
                "package_format": metadata["PackageFormat"],
                "update_agents": ["Bmc"],
                "declared_targets": sorted(targets),
                "declared_version": expected_version,
                "metadata_sha256": hashlib.sha256(raw).hexdigest(),
                "binary": {"name": filename, "size_bytes": count, "sha256": digest.hexdigest()},
                "provenance": "package_declaration_not_hardware_proof",
                "signature_verified": False,
                "requires_target_match": True,
                "host_power_requirements_known": power_requirements_known,
                "ilo_reset_expected": True,
                "host_reboot_authorized": False,
            }
    except FirmwarePackageError:
        raise
    except Exception:
        raise FirmwarePackageError(
            "Firmware archive or metadata could not be inspected safely."
        ) from None
