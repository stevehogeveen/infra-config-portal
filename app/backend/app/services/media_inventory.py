from __future__ import annotations

import re
from pathlib import Path

from app.core.config import settings
from app.schemas import MediaInventoryItemRead, MediaInventoryRead

MEDIA_INVENTORY_LIMIT = 200
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
        return MediaInventoryRead(
            mode="sample",
            configured_directories=[],
            items=SAMPLE_MEDIA_ITEMS,
            warnings=[
                "MEDIA_INVENTORY_DIRS is not configured; returning mock sample media metadata."
            ],
        )

    items: list[MediaInventoryItemRead] = []
    warnings: list[str] = []
    scanned_count = 0

    configured_directory_labels = [
        f"configured-directory-{index}"
        for index, _ in enumerate(configured_directories, start=1)
    ]

    for directory, source_label in zip(configured_directories, configured_directory_labels):
        path = Path(directory).expanduser()
        if not path.exists():
            warnings.append(f"{source_label} does not exist.")
            continue
        if not path.is_dir():
            warnings.append(f"{source_label} is not a directory.")
            continue

        try:
            entries = sorted(
                (entry for entry in path.rglob("*") if not entry.is_symlink() and entry.is_file()),
                key=lambda item: str(item.relative_to(path)).lower(),
            )
        except OSError:
            warnings.append(f"{source_label} could not be read.")
            continue

        scanned_count += 1
        for entry in entries:
            if len(items) >= MEDIA_INVENTORY_LIMIT:
                warnings.append(
                    f"Media inventory truncated at {MEDIA_INVENTORY_LIMIT} local files."
                )
                break
            items.append(_inventory_item(entry, len(items) + 1, source_label))

    return MediaInventoryRead(
        mode="local" if scanned_count else "unavailable",
        configured_directories=configured_directory_labels,
        items=items,
        warnings=warnings,
    )


def _inventory_item(path: Path, index: int, source_label: str) -> MediaInventoryItemRead:
    extension = _extension(path)
    category = _category_for_extension(extension)
    hints = _safe_media_hints(path.name)
    return MediaInventoryItemRead(
        placeholder_name=f"{category}-{index}{extension}",
        extension=extension,
        size_bytes=path.stat().st_size,
        category=category,
        source=source_label,
        actual_name_redacted=True,
        product_hints=hints["product_hints"],
        generation_hints=hints["generation_hints"],
        version_hint=hints["version_hint"],
    )


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
    if re.search(r"(?:^|[^a-z0-9])spp(?:[^a-z0-9]|$)", normalized):
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
