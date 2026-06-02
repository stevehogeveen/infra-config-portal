from __future__ import annotations

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

    for directory in configured_directories:
        path = Path(directory).expanduser()
        if not path.exists():
            warnings.append("Configured media inventory directory does not exist.")
            continue
        if not path.is_dir():
            warnings.append("Configured media inventory path is not a directory.")
            continue

        scanned_count += 1
        try:
            entries = sorted(path.iterdir(), key=lambda item: item.name.lower())
        except OSError:
            warnings.append("Configured media inventory directory could not be read.")
            continue

        for entry in entries:
            if len(items) >= MEDIA_INVENTORY_LIMIT:
                warnings.append(
                    f"Media inventory truncated at {MEDIA_INVENTORY_LIMIT} local files."
                )
                break
            if entry.is_symlink() or not entry.is_file():
                continue
            items.append(_inventory_item(entry, len(items) + 1))

    return MediaInventoryRead(
        mode="local" if scanned_count else "unavailable",
        configured_directories=["redacted" for _ in configured_directories],
        items=items,
        warnings=warnings,
    )


def _inventory_item(path: Path, index: int) -> MediaInventoryItemRead:
    extension = path.suffix.lower()
    category = _category_for_extension(extension)
    return MediaInventoryItemRead(
        placeholder_name=f"{category}-{index}{extension}",
        extension=extension,
        size_bytes=path.stat().st_size,
        category=category,
        source="configured-directory",
        actual_name_redacted=True,
    )


def _category_for_extension(extension: str) -> str:
    if extension == ".iso":
        return "iso"
    if extension == ".ovf":
        return "ovf"
    if extension == ".ova":
        return "ova"
    if extension == ".vmdk":
        return "vmdk"
    if extension in {".bin", ".rom", ".fw", ".fwpkg", ".scexe", ".firmware"}:
        return "firmware"
    return "other"
