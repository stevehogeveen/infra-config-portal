"""Read-only standalone firmware selection; never replaces the saved SPP."""

import hashlib
import os
import stat
from pathlib import Path

from app.services.firmware_packages import FirmwarePackageError, media_path, media_root
from app.services.firmware_payload import inspect_ilo_payload

MAX_PACKAGE_BYTES = 128 * 1024**2


def _path(relative: str) -> Path:
    if len(relative) > 512 or any(ord(char) < 32 for char in relative):
        raise FirmwarePackageError("Firmware path contains unsupported characters or is too long.")
    resolved = media_path(relative)
    current = media_root()
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise FirmwarePackageError("Firmware paths must not contain symbolic links.")
    return resolved


def browse_standalone(folder: str = "") -> dict:
    path = _path(folder)
    if not path.is_dir():
        raise FirmwarePackageError("Select an existing media folder.")
    folders, files = [], []
    truncated = False
    try:
        for count, entry in enumerate(path.iterdir()):
            if count >= 1000:
                truncated = True
                break
            if entry.is_symlink():
                continue
            relative = entry.relative_to(media_root()).as_posix()
            if entry.is_dir():
                folders.append({"name": entry.name, "path": relative})
            elif entry.is_file() and entry.suffix.lower() == ".fwpkg":
                files.append(
                    {"name": entry.name, "path": relative, "size_bytes": entry.stat().st_size}
                )
    except OSError:
        raise FirmwarePackageError("Firmware folder could not be read.") from None
    return {
        "folder": folder,
        "folders": sorted(folders, key=lambda x: x["name"]),
        "files": sorted(files, key=lambda x: x["name"]),
        "truncated": truncated,
    }


def _identity(value):
    # On Windows a path stat and a handle stat report different creation times for the same
    # file, so st_ctime is only part of the identity on POSIX (where it is the change time).
    ctime = None if os.name == "nt" else value.st_ctime_ns
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, ctime


def inspect_standalone(relative: str) -> dict:
    path = _path(relative)
    if path.suffix.lower() != ".fwpkg":
        raise FirmwarePackageError("Choose an iLO FWPKG file.")
    try:
        before = path.stat()
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_PACKAGE_BYTES:
            raise FirmwarePackageError("Firmware file is empty, too large or not a regular file.")
        with path.open("rb") as stream:
            if _identity(os.fstat(stream.fileno())) != _identity(before):
                raise FirmwarePackageError("Firmware changed before inspection.")
            digest = hashlib.sha256()
            count = 0
            while chunk := stream.read(1024**2):
                count += len(chunk)
                if count > MAX_PACKAGE_BYTES:
                    raise FirmwarePackageError("Firmware exceeds the inspection limit.")
                digest.update(chunk)
            stream.seek(0)
            payload = inspect_ilo_payload(stream)
            if (
                count != before.st_size
                or _identity(os.fstat(stream.fileno())) != _identity(before)
                or _identity(_path(relative).stat()) != _identity(before)
            ):
                raise FirmwarePackageError("Firmware changed during inspection.")
    except OSError:
        raise FirmwarePackageError("Firmware file could not be read.") from None
    return {
        "path": relative,
        "source_root": str(media_root()),
        "file_name": path.name,
        "size_bytes": before.st_size,
        "modified_ns": str(before.st_mtime_ns),
        "sha256": digest.hexdigest(),
        "payload": payload,
        "provenance": "local_package_bytes",
        "signature_verified": False,
        "can_apply": False,
        "blockers": [
            "Local bytes inspected; trusted HPE signature verification is still required.",
            "Exact-target applicability, power requirements and prerequisites need review.",
            "No hardware installation adapter is enabled.",
        ],
    }
