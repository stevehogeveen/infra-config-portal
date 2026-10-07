"""Bounded, read-only inspection of exact SPP component bytes."""
import hashlib
import json
from pathlib import PurePosixPath

import pycdlib

from app.services.firmware_packages import FirmwarePackageError, media_path, package_unchanged
from app.services.spp_assessment import read_catalog
from app.services.firmware_payload import inspect_ilo_payload

MAX_COMPONENT_BYTES = 512 * 1024**2
MAX_COMPONENT_FILES = 16
MAX_ENTRIES = 20000


def inspect_component(package: dict, component_id: str) -> dict:
    if not package_unchanged(package):
        raise FirmwarePackageError("Selected ISO changed or is missing. Select it again.")
    path = media_path(package["path"])
    before = path.stat()
    # Execution preparation must not reuse the version-comparison metadata cache.
    catalog = read_catalog.__wrapped__(str(path), before.st_size, before.st_mtime_ns)
    matches = [c for c in catalog["components"] if c["id"] == component_id]
    if len(matches) != 1:
        raise FirmwarePackageError("Select one unambiguous manifest component.")
    component = matches[0]
    names = component["files"]
    if not names or len(names) > MAX_COMPONENT_FILES or len({n.casefold() for n in names}) != len(names):
        raise FirmwarePackageError("Component file list is empty, duplicated or too large.")
    for name in names:
        if (not name or PurePosixPath(name).name != name or name in {".", ".."}
                or any(c in name for c in ("\\", ":", "\x00"))):
            raise FirmwarePackageError("Component manifest contains an unsafe file name.")
    iso = pycdlib.PyCdlib()
    files = []
    total = 0
    payloads = []
    try:
        iso.open(str(path))
        namespace = "rr_path" if iso.has_rock_ridge() else "joliet_path" if iso.has_joliet() else "iso_path"
        found = {name.casefold(): [] for name in names}
        entries = 0
        for directory, folders, filenames in iso.walk(**{namespace: "/"}):
            entries += len(folders) + len(filenames)
            if entries > MAX_ENTRIES:
                raise FirmwarePackageError("ISO listing exceeds the inspection limit.")
            if directory.casefold() != "/packages":
                continue
            for name in filenames:
                key = name.split(";")[0].casefold() if namespace == "iso_path" else name.casefold()
                if key in found:
                    found[key].append(directory.rstrip("/") + "/" + name)
        for name in names:
            candidates = found[name.casefold()]
            if len(candidates) != 1:
                raise FirmwarePackageError("Component file is missing or ambiguous within /packages.")
            location = {namespace: candidates[0]}
            record = iso.get_record(**location)
            if record.is_symlink():
                raise FirmwarePackageError("Component files must not be symbolic links.")
            size = record.data_length
            total += size
            if size <= 0 or total > MAX_COMPONENT_BYTES:
                raise FirmwarePackageError("Component payload exceeds the inspection size limit or is empty.")
            digest = hashlib.sha256()
            read = 0
            with iso.open_file_from_iso(**location) as stream:
                while chunk := stream.read(min(1024**2, size - read + 1)):
                    read += len(chunk)
                    if read > size:
                        raise FirmwarePackageError("Component length changed during inspection.")
                    digest.update(chunk)
            if read != size:
                raise FirmwarePackageError("Component payload is truncated.")
            files.append({"name": name, "size_bytes": size, "sha256": digest.hexdigest()})
            if component["kind"] == "universal-fw-ilo" and name.lower().endswith(".fwpkg"):
                try:
                    with iso.open_file_from_iso(**location) as stream:
                        payloads.append({"file": name, **inspect_ilo_payload(stream, component["version"])})
                except FirmwarePackageError as exc:
                    payloads.append({"file": name, "inspection_error": str(exc)})
    except FirmwarePackageError:
        raise
    except Exception:
        raise FirmwarePackageError("Component bytes could not be inspected safely.") from None
    finally:
        try:
            iso.close()
        except Exception:
            pass
    after = path.stat()
    if ((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
            or not package_unchanged(package)):
        raise FirmwarePackageError("ISO changed during inspection. Select it again.")
    identity = {"metadata_sha256": catalog["metadata_sha256"], "component_id": component_id,
                "files": sorted(files, key=lambda f: f["name"])}
    component_hash = hashlib.sha256(json.dumps(
        identity, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    return {
        **identity, "component_hash": component_hash, "name": component["name"],
        "version": component["version"], "kind": component["kind"],
        "payloads": payloads,
        "upgrade_constraints": (
            ["For iLO 5 older than 1.48, this workflow requires a separately reviewed "
             "1.48 bridge before 3.19; it does not require an intermediate 2.78 update. "
             "Exact-target prerequisites still require review. Each update needs its own approval."]
            if any(p.get("declared_version") == "3.19" for p in payloads)
            else []
        ),
        "provenance": "local_package_bytes", "signature_verified": False,
        "applicability_verified": False, "dependencies_verified": False,
        "can_apply": False,
        "blockers": [
            "Package byte identity is recorded; HPE signature validation is not established.",
            "Exact-target applicability and upgrade prerequisites still require verification.",
            "No hardware installation adapter is enabled.",
        ],
    }
