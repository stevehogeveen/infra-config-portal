"""Read-only browsing and ISO metadata inspection within a mounted media root."""
import os
from pathlib import Path

import pycdlib

from app.services.media_inventory import DEFAULT_MEDIA_ROOT, _safe_media_hints

HPE_DOWNLOAD_URL = "https://support.hpe.com/hpesc/public/docDisplay?docId=c03190790&docLocale=en_US&page=GUID-BB4D055A-56A2-4D75-A949-197C4BDC7F2A.html"
HPE_DOCUMENTATION_URL = "https://support.hpe.com/hpesc/public/docDisplay?docId=c03190790"


class FirmwarePackageError(ValueError):
    pass


def media_root():
    return Path(os.getenv("FIRMWARE_MEDIA_ROOT") or DEFAULT_MEDIA_ROOT).resolve()


def media_path(relative: str) -> Path:
    root = media_root()
    requested = Path(relative)
    if requested.is_absolute() or "\\" in relative or ":" in relative or ".." in requested.parts:
        raise FirmwarePackageError("Choose a folder or ISO within the mounted media folder.")
    target = (root / requested).resolve()
    if not target.is_relative_to(root):
        raise FirmwarePackageError("The selected path is outside the mounted media folder.")
    return target


def browse_packages(folder: str = ""):
    root = media_root()
    path = media_path(folder)
    result = {"root": str(root), "host_root": os.getenv("FIRMWARE_MEDIA_HOST_PATH") or None,
              "folder": folder, "folders": [], "files": [], "warning": None,
              "download_url": HPE_DOWNLOAD_URL, "documentation_url": HPE_DOCUMENTATION_URL}
    if not path.exists():
        result["warning"] = "Folder not found. Create the media folder on the Docker host and place the downloaded ISO there."
        return result
    if not path.is_dir():
        raise FirmwarePackageError("Select a directory, not a file.")
    try:
        for count, entry in enumerate(path.iterdir()):
            if count >= 1000:
                result["warning"] = "Folder contains more than 1000 entries. Use a smaller subfolder."
                break
            if entry.is_symlink() or not entry.resolve().is_relative_to(root):
                continue
            relative = entry.relative_to(root).as_posix()
            if entry.is_dir():
                result["folders"].append({"name": entry.name, "path": relative})
            elif entry.is_file() and entry.suffix.lower() == ".iso":
                result["files"].append({"name": entry.name, "path": relative, "size_bytes": entry.stat().st_size})
    except OSError:
        raise FirmwarePackageError("The backend cannot read this folder. Check the Docker mount and folder permissions.") from None
    result["folders"].sort(key=lambda item: item["name"].lower())
    result["files"].sort(key=lambda item: item["name"].lower())
    return result


def inspect_package(relative: str):
    path = media_path(relative)
    if path.suffix.lower() != ".iso" or not path.is_file():
        raise FirmwarePackageError("Choose an existing ISO file from the mounted media folder.")
    before = path.stat()
    iso = pycdlib.PyCdlib()
    manifests = []
    baseline_found = False
    try:
        iso.open(str(path))
        label = iso.pvd.volume_identifier.decode("utf-8", errors="replace").strip()
        count = 0
        for directory, folders, files in iso.walk(iso_path="/"):
            count += len(folders) + len(files)
            if count > 20000:
                raise FirmwarePackageError("ISO directory listing is too large to inspect safely.")
            for name in files:
                clean = name.split(";")[0].lower()
                if clean.startswith("bp") and clean.endswith(".xml"):
                    baseline_found = True
                if (clean.startswith("bp") and clean.endswith(".xml")) or "manifest" in clean or "manifest" in directory.lower():
                    if len(manifests) < 100:
                        manifests.append(f"{directory.rstrip('/')}/{name}")
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise FirmwarePackageError("The ISO changed during inspection. Wait for the copy to finish and retry.")
    except FirmwarePackageError:
        raise
    except Exception:
        raise FirmwarePackageError("This file could not be read as an ISO image. Check that the download is complete and uncorrupted.") from None
    finally:
        try:
            iso.close()
        except Exception:
            pass
    hints = _safe_media_hints(path.name + " " + label)
    return {"path": relative, "source_root": str(media_root()), "file_name": path.name, "size_bytes": after.st_size,
            "modified_ns": str(after.st_mtime_ns), "volume_label": label,
            "release_hint": hints["version_hint"], "generation_hints": hints["generation_hints"],
            "manifest_files": manifests, "status": "ISO readable; compatibility unverified",
            "baseline_found": baseline_found,
            "validation_note": "ISO structure inspected only. Release and generation hints come from labels, not verified hardware support. Manifest presence does not validate component versions, HPE signatures or upgrade applicability. No installation is enabled."}


def package_unchanged(package: dict):
    try:
        path = media_path(package["path"])
        stat = path.stat()
        return (package.get("source_root") == str(media_root()) and stat.st_size == package["size_bytes"]
                and str(stat.st_mtime_ns) == package["modified_ns"])
    except (OSError, ValueError, KeyError):
        return False
