"""LAN-only, read-only ISO delivery using Starlette's byte-range implementation."""

import threading
import time
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from starlette.responses import FileResponse

from app.services.firmware_packages import FirmwarePackageError

_lock = threading.Lock()
_server = None
_thread = None
_binding = None


def media_app(directory: Path) -> FastAPI:
    root = directory.resolve(strict=True)
    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None)

    @app.api_route("/{filename}", methods=["GET", "HEAD"])
    def iso(filename: str):
        path = root / filename
        if (
            Path(filename).name != filename
            or "\\" in filename
            or path.suffix.lower() != ".iso"
            or path.is_symlink()
            or not path.is_file()
            or path.resolve().parent != root
        ):
            raise HTTPException(404)
        return FileResponse(
            path,
            media_type="application/octet-stream",
            headers={"Cache-Control": "no-store", "X-SPP-Media": "byte-range-v1"},
        )

    return app


def ensure_media_server(directory: Path, port: int):
    global _server, _thread, _binding
    binding = (str(directory.resolve(strict=True)), port)
    with _lock:
        if _thread is not None and _thread.is_alive():
            if _binding != binding:
                raise FirmwarePackageError(
                    "The ISO service is already serving another media directory."
                )
        else:
            _server = uvicorn.Server(
                uvicorn.Config(
                    media_app(directory),
                    host="0.0.0.0",
                    port=port,
                    access_log=False,
                    log_level="error",
                )
            )
            _binding = binding
            _thread = threading.Thread(target=_server.run, name="spp-media", daemon=True)
            _thread.start()
        deadline = time.monotonic() + 5
        while not _server.started and _thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not _server.started or not _thread.is_alive():
            raise FirmwarePackageError("The ISO service could not start on its configured port.")
