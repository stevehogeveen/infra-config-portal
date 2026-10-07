"""Bounded streaming upload; publish complete files without replacing existing media."""
import os
import shutil
from pathlib import Path
from uuid import uuid4

import anyio
from fastapi import HTTPException

from app.services.firmware_packages import media_path, FirmwarePackageError


# "iso": installer and SPP images. "vm": VM exports (Windows OVA/OVF) for the ESXi host.
KINDS = {
    "iso": ((".iso",), 20 * 1024**3, "Choose an ISO file between 1 byte and 20 GB with a valid filename."),
    "vm": ((".ova", ".ovf", ".vmdk", ".mf", ".nvram", ".cert"), 128 * 1024**3,
           "Choose an .ova, or an .ovf export's files (.ovf, .vmdk, .nvram, .mf, .cert), up to 128 GB each."),
}


async def receive_iso(chunks, name: str, size: int, folder: str = "", kind: str = "iso"):
    suffixes, limit, problem = KINDS.get(kind, KINDS["iso"])
    if (Path(name).name != name or any(char in name for char in '/\\:<>"|?*')
            or any(ord(char) < 32 for char in name) or not name.lower().endswith(suffixes)
            or name.startswith(".") or size <= 0 or size > limit):
        raise HTTPException(422, problem)
    try:
        directory = media_path(folder)
    except FirmwarePackageError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not directory.is_dir():
        raise HTTPException(422, "Destination folder does not exist. Scan or choose the media folder first.")
    target = directory / name
    if target.exists():
        raise HTTPException(409, "This filename is already in the media folder. Scan and select the existing file; nothing was overwritten.")
    temporary = directory / f".upload-{uuid4().hex}.partial"
    try:
        if shutil.disk_usage(directory).free < size + 256 * 1024**2:
            raise HTTPException(507, "Not enough free disk space for this file. Free space or use another media folder.")
        received = 0
        async with await anyio.open_file(temporary, "xb") as output:
            async for chunk in chunks:
                received += len(chunk)
                if received > size:
                    raise HTTPException(413, "Upload exceeded its declared size.")
                await output.write(chunk)
        if received != size:
            raise HTTPException(422, "Upload was incomplete. Please retry.")
        # Hard-link publication is atomic and fails if another upload won the name.
        # Unsupported filesystems fail closed instead of overwriting existing media.
        try:
            os.link(temporary, target)
        except FileExistsError:
            raise HTTPException(409, "This filename was uploaded elsewhere. Nothing was overwritten.") from None
    except OSError:
        raise HTTPException(507, "The media folder could not accept the upload. Check free space, write permissions and filesystem support.") from None
    finally:
        temporary.unlink(missing_ok=True)
    return {"name": name, "path": f"{folder.rstrip('/')}/{name}".lstrip("/"), "size_bytes": received}
