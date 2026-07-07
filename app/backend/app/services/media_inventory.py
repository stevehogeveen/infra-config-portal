from __future__ import annotations

import os
import re
from pathlib import Path

from app.core.config import settings
from app.schemas import MediaInventoryItemRead, MediaInventoryRead
from app.services.path_utils import directory_state, file_size, file_state, rglob_paths_or_none

MEDIA_INVENTORY_LIMIT = 200
REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_MEDIA_ROOT = REPO_ROOT / "artifacts" / "Media"
SAMPLE_MEDIA_ITEMS = [
    MediaInventoryItemRead(
        placeholder_name="sample-installer.iso",
        extension=".iso",
        size_bytes=0,
        category="iso",
        source="sample",
        actual_name_redacted=True,
    ),
    MediaInventoryItemRead(
        placeholder_name="sample-template.ova",
        extension=".ova",
        size_bytes=0,
        category="ova",
        source="sample",
        actual_name_redacted=True,
    ),
    MediaInventoryItemRead(
        placeholder_name="sample-firmware.fwpkg",
        extension=".fwpkg",
        size_bytes=0,
        category="firmware",
        source="sample",
        actual_name_redacted=True,
    ),
]


def get_media_inventory(
    directories: tuple[str, ...] | None = None,
) -> MediaInventoryRead:
    configured_directories = directories if directories is not None else settings.media_inventory_dirs
    if not configured_directories:
        if settings.provider_mode != "mock":
            return MediaInventoryRead(
                mode="unavailable",
                configured_directories=[],
                configured_directory_paths=[],
                items=[],
                warnings=[
                    "MEDIA_INVENTORY_DIRS is not configured; no real media inventory was returned."
                ],
            )
        return MediaInventoryRead(
            mode="sample",
            configured_directories=[],
            configured_directory_paths=[],
            items=SAMPLE_MEDIA_ITEMS,
            warnings=[
                "MEDIA_INVENTORY_DIRS is not configured; returning mock sample media metadata."
            ],
        )

    items: list[MediaInventoryItemRead] = []
    warnings: list[str] = []
    scanned_count = 0

    configured_directory_entries, duplicate_count = _configured_directory_entries(configured_directories)
    configured_directory_labels = [source_label for _path, source_label in configured_directory_entries]
    configured_directory_paths = [str(path) for path, _source_label in configured_directory_entries]
    if duplicate_count:
        warnings.append(f"{duplicate_count} duplicate configured media director{'y was' if duplicate_count == 1 else 'ies were'} ignored.")

    for path, source_label in configured_directory_entries:
        path_state = directory_state(path)
        if path_state == "missing":
            warnings.append(f"{source_label} does not exist.")
            continue
        if path_state == "not_directory":
            warnings.append(f"{source_label} is not a directory.")
            continue
        if path_state == "unreadable":
            warnings.append(f"{source_label} could not be read.")
            continue

        entries, unreadable_count = _media_file_entries(path)
        if entries is None:
            warnings.append(f"{source_label} could not be read.")
            continue
        if unreadable_count:
            warnings.append(
                f"{source_label} contained {unreadable_count} file{'s' if unreadable_count != 1 else ''} that could not be read."
            )

        scanned_count += 1
        for entry in entries:
            if len(items) >= MEDIA_INVENTORY_LIMIT:
                warnings.append(
                    f"Media inventory truncated at {MEDIA_INVENTORY_LIMIT} local files."
                )
                break
            item = _inventory_item(entry, len(items) + 1, source_label)
            if item is None:
                warnings.append(f"{source_label} contained a file that could not be read.")
                continue
            items.append(item)

    return MediaInventoryRead(
        mode="local" if scanned_count else "unavailable",
        configured_directories=configured_directory_labels,
        configured_directory_paths=configured_directory_paths,
        items=items,
        warnings=warnings,
    )


def _configured_directory_entries(configured_directories: tuple[str, ...]) -> tuple[list[tuple[Path, str]], int]:
    entries: list[tuple[Path, str]] = []
    seen: set[str] = set()
    duplicate_count = 0
    for directory in configured_directories:
        path = Path(directory).expanduser()
        key = _directory_identity(path)
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        entries.append((path, f"configured-directory-{len(entries) + 1}"))
    return entries, duplicate_count


def _media_file_entries(path: Path) -> tuple[list[Path] | None, int]:
    entries: list[Path] = []
    unreadable_count = 0
    candidates = rglob_paths_or_none(path, "*")
    if candidates is None:
        return None, 0
    for entry in candidates:
        try:
            if entry.is_symlink():
                continue
        except OSError:
            unreadable_count += 1
            continue
        entry_state = file_state(entry)
        if entry_state == "file":
            entries.append(entry)
        elif entry_state == "unreadable":
            unreadable_count += 1
    return sorted(entries, key=lambda item: str(item.relative_to(path)).lower()), unreadable_count


def _directory_identity(path: Path) -> str:
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        resolved = path.absolute()
    return os.path.normcase(os.path.normpath(str(resolved)))


def _inventory_item(path: Path, index: int, source_label: str) -> MediaInventoryItemRead | None:
    extension = _extension(path)
    category = _category_for_extension(extension)
    hints = _safe_media_hints(path.name)
    exact_metadata = _repo_media_metadata(path, hints)
    size_bytes = file_size(path)
    if size_bytes is None:
        return None
    return MediaInventoryItemRead(
        placeholder_name=f"{category}-{index}{extension}",
        extension=extension,
        size_bytes=size_bytes,
        category=category,
        source=source_label,
        actual_name_redacted=not bool(exact_metadata),
        product_hints=hints["product_hints"],
        generation_hints=hints["generation_hints"],
        version_hint=hints["version_hint"],
        **exact_metadata,
    )


def _repo_media_metadata(path: Path, hints: dict[str, list[str] | str | None]) -> dict[str, str | None]:
    try:
        resolved = path.resolve()
        media_root = DEFAULT_MEDIA_ROOT.resolve()
        resolved.relative_to(media_root)
    except (OSError, ValueError):
        return {}

    product_hints = [str(item) for item in hints["product_hints"] if item]
    return {
        "file_name": path.name,
        "file_path": str(resolved),
        "detected_vendor": _detected_vendor(product_hints),
        "detected_product": product_hints[0] if product_hints else None,
        "detected_version": str(hints["version_hint"]) if hints["version_hint"] else None,
        "confidence": "high" if product_hints or hints["version_hint"] else "medium",
    }


def _detected_vendor(product_hints: list[str]) -> str | None:
    text = " ".join(product_hints).lower()
    if "cisco" in text:
        return "Cisco"
    if "hpe" in text or "ilo" in text:
        return "HPE"
    if "netapp" in text or "ontap" in text:
        return "NetApp"
    if "vmware" in text or "esxi" in text or "vcenter" in text:
        return "VMware"
    return None


def _extension(path: Path) -> str:
    name = path.name.lower()
    if name.endswith(".tar.gz"):
        return ".tar.gz"
    return path.suffix.lower()


def _category_for_extension(extension: str) -> str:
    if extension == ".iso":
        return "iso"
    if extension == ".ovf":
        return "ovf"
    if extension == ".ova":
        return "ova"
    if extension == ".vmdk":
        return "vmdk"
    if extension in {
        ".bin",
        ".rom",
        ".fw",
        ".fwpkg",
        ".scexe",
        ".firmware",
        ".tgz",
        ".tar",
        ".tar.gz",
        ".zip",
        ".pkg",
        ".image",
    }:
        return "firmware"
    return "other"


def _safe_media_hints(name: str) -> dict[str, list[str] | str | None]:
    normalized = name.lower()
    product_hints: list[str] = []
    generation_hints: list[str] = []

    if re.search(r"(?:^|[^a-z0-9])hpe(?:[^a-z0-9]|$)", normalized):
        product_hints.append("hpe")
    if re.search(r"(?:^|[^a-z0-9])(?:sum|smart[\s._-]?update)(?:[^a-z0-9]|$)", normalized):
        _append_unique(product_hints, "hpe-sum")
    if re.search(r"(?:^|[^a-z0-9])spp(?:[^a-z0-9]|$)", normalized) or re.search(
        r"(?:^|[^a-z0-9])gen\d{1,2}spp|spp\d{8,}",
        normalized,
    ) or re.search(
        r"service[\s._-]?pack.*proliant|proliant.*service[\s._-]?pack",
        normalized,
    ):
        _append_unique(product_hints, "hpe-spp")
    if re.search(r"(?:^|[^a-z0-9])(?:netapp|ontap)(?:[^a-z0-9]|$)", normalized) or _ontap_q_image_version(normalized):
        _append_unique(product_hints, "netapp-ontap")
    if re.search(r"(?:^|[^a-z0-9])(?:vcsa|vcenter|vcenter[\s._-]?server[\s._-]?appliance)(?:[^a-z0-9]|$)", normalized):
        _append_unique(product_hints, "vmware-vcenter")
    if re.search(r"(?:^|[^a-z0-9])(?:esxi|vmvisor|hypervisor)(?:[^a-z0-9]|$)", normalized):
        _append_unique(product_hints, "vmware-esxi")
    if re.search(r"(?:^|[^a-z0-9])(?:cisco|iosxe|ios[\s._-]?xe|cat9k)(?:[^a-z0-9]|$)", normalized):
        _append_unique(product_hints, "cisco-ios-xe")

    for match in re.finditer(r"(?:^|[^a-z0-9])ilo[\s._-]?([456])(?:[^a-z0-9]|$)", normalized):
        _append_unique(product_hints, "hpe-ilo")
        _append_unique(generation_hints, f"ilo{match.group(1)}")

    for match in re.finditer(r"(?:^|[^a-z0-9])gen[\s._-]?(\d{1,2})(?:[^a-z0-9]|$)", normalized):
        _append_unique(generation_hints, f"gen{match.group(1)}")
    for match in re.finditer(r"(?:^|[^a-z0-9])gen(\d{1,2})spp", normalized):
        _append_unique(generation_hints, f"gen{match.group(1)}")

    return {
        "product_hints": product_hints,
        "generation_hints": generation_hints,
        "version_hint": _version_hint(normalized),
    }


def _version_hint(normalized_name: str) -> str | None:
    ontap_q_image = _ontap_q_image_version(normalized_name)
    if ontap_q_image:
        return ontap_q_image

    ilo_compact = re.search(
        r"(?:^|[^a-z0-9])ilo[\s._-]?[456][\s._-]*v?(\d{1,2})(\d{2})(?:[^a-z0-9]|$)",
        normalized_name,
    )
    if ilo_compact:
        return f"{int(ilo_compact.group(1))}.{ilo_compact.group(2)}"

    spp_version = re.search(
        r"(?:spp|service[\s._-]?pack).*?(\d{4})[._-](\d{1,2})(?:[._-](\d{1,2}))?",
        normalized_name,
    )
    if spp_version:
        return ".".join(str(int(part)) for part in spp_version.groups() if part is not None)

    dotted = re.search(
        r"(?:^|[^a-z0-9])v?(\d{1,3})[._-](\d{1,3})(?:[._-](\d{1,3}))?(?:[^a-z0-9]|$)",
        normalized_name,
    )
    if not dotted:
        return None
    parts = [str(int(part)) for part in dotted.groups() if part is not None]
    return ".".join(parts)


def _ontap_q_image_version(normalized_name: str) -> str | None:
    match = re.search(
        r"(?:^|[^a-z0-9])(?P<major>\d)(?P<minor>\d{2})(?P<patch>\d)(?:p(?P<patch_release>\d+))?_q_image(?:[^a-z0-9]|$)",
        normalized_name,
    )
    if not match:
        return None
    version = f"{int(match.group('major'))}.{int(match.group('minor'))}.{int(match.group('patch'))}"
    if match.group("patch_release"):
        version += f"P{int(match.group('patch_release'))}"
    return version


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
