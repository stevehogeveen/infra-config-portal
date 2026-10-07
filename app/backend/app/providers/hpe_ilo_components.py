"""iLO 5 component install, the way HPE's iLOrest `flashfwpkg`/`uploadcomp` does it.

* A FWPKG-v2 package is uploaded as-is (iLO 5 newer than 2.30 unpacks it) to the iLO's
  HttpPushUri with a session key and a parameters block. `UpdateTarget` asks the iLO to flash
  it now (packages the iLO installs itself); without it the package only lands in the iLO
  Repository.
* Packages the BIOS installs are queued with an `ApplyUpdate` task; the BIOS runs them at the
  next start.

Each function is one request (plus session setup). The caller owns ordering, dispatch leases,
recording and the rule that an unconfirmed send is never repeated.
"""

from __future__ import annotations

import json
import re
import secrets
from contextlib import contextmanager
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.providers.hpe_firmware_inventory import _resource_path
from app.providers.hpe_storage_rebuild import client_for
from app.services.esxi_boot_workflow import _base_url

UPDATE_SERVICE = "/redfish/v1/UpdateService/"
TASK_QUEUE = "/redfish/v1/UpdateService/UpdateTaskQueue/"
REPOSITORY = "/redfish/v1/UpdateService/ComponentRepository/"
PACKAGE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}\.fwpkg$")
MAX_PACKAGE_BYTES = 256 * 1024**2
BUSY = {"UPLOADING", "PROGRESSING", "VERIFYING", "WRITING", "UPDATING", "FLASHING", "AWAITINGUPLOAD"}


class ComponentError(RuntimeError):
    """A safe-to-show reason. `sent` says whether the request may have reached the iLO."""

    def __init__(self, message: str, *, sent: bool = False, refused: bool = False):
        super().__init__(message)
        # refused: the iLO answered with a definite rejection, so nothing was applied.
        self.sent = sent and not refused
        self.refused = refused


def _get(client: httpx.Client, base: str, path: str) -> dict[str, Any]:
    response = client.get(base + path, follow_redirects=False, timeout=60.0)
    if response.status_code != 200:
        raise ComponentError(f"The iLO did not return {path} (HTTP {response.status_code}).")
    body = response.json()
    if not isinstance(body, dict):
        raise ComponentError(f"The iLO returned an unexpected body for {path}.")
    return body


def _members(client: httpx.Client, base: str, path: str) -> list[dict[str, Any]]:
    listing = _get(client, base, path)
    items = []
    for member in (listing.get("Members") or [])[:128]:
        if isinstance(member, dict) and "@odata.id" in member and len(member) == 1:
            items.append(_get(client, base, _resource_path(member["@odata.id"])))
        elif isinstance(member, dict):
            items.append(member)
    return items


def update_service(config) -> dict[str, Any]:
    """{"state": "IDLE"|"COMPLETE"|"ERROR"|..., "result": message id or None, "push_uri", "busy"}."""
    with client_for(config) as client:
        body = _get(client, _base_url(config.host), UPDATE_SERVICE)
    hpe = (body.get("Oem") or {}).get("Hpe") or {}
    state = str(hpe.get("State") or "UNKNOWN").upper()
    result = hpe.get("Result") if isinstance(hpe.get("Result"), dict) else {}
    return {
        "state": state,
        "busy": state in BUSY,
        "result": result.get("MessageId"),
        "progress": hpe.get("FlashProgressPercent"),
        "push_uri": hpe.get("PushUpdateUri") or body.get("HttpPushUri"),
    }


def repository(config) -> list[dict[str, Any]]:
    with client_for(config) as client:
        items = _members(client, _base_url(config.host), REPOSITORY)
    return [
        {"filename": str(i.get("Filename") or ""), "version": i.get("Version"), "locked": bool(i.get("Locked"))}
        for i in items
    ]


def task_queue(config) -> list[dict[str, Any]]:
    with client_for(config) as client:
        items = _members(client, _base_url(config.host), TASK_QUEUE)
    tasks = []
    for item in items:
        result = item.get("Result") if isinstance(item.get("Result"), dict) else {}
        tasks.append({
            "name": str(item.get("Name") or ""),
            "filename": str(item.get("Filename") or ""),
            "state": str(item.get("State") or ""),
            "command": str(item.get("Command") or ""),
            "result": result.get("MessageId"),
        })
    return tasks


def etag_for(filename: str) -> str:
    """iLOrest's ETag: 'sum' + the file name without dots, dashes and underscores."""
    return "sum" + re.sub(r"[._-]", "", filename)


@contextmanager
def _session(client: httpx.Client, base: str, config):
    login = client.post(
        base + "/redfish/v1/SessionService/Sessions/",
        json={"UserName": config.username, "Password": config.password},
        follow_redirects=False,
        timeout=60.0,
    )
    token = login.headers.get("X-Auth-Token", "")
    if login.status_code != 201 or not re.fullmatch(r"[A-Za-z0-9._~-]{1,1024}", token):
        raise ComponentError("The iLO did not open an upload session; nothing was uploaded.")
    location = login.headers.get("Location", "")
    try:
        yield token
    finally:
        try:
            path = _resource_path(location)
            if path.startswith("/redfish/v1/SessionService/Sessions/"):
                client.delete(base + path, headers={"X-Auth-Token": token}, follow_redirects=False, timeout=30.0)
        except Exception:
            pass


def upload_package(config, *, filename: str, data: bytes, flash_now: bool) -> None:
    """Upload one FWPKG-v2 package. flash_now=True: the iLO installs it (UpdateTarget).
    Raises ComponentError(sent=True) once the upload request may have reached the iLO."""
    if not PACKAGE.fullmatch(filename) or not data or len(data) > MAX_PACKAGE_BYTES:
        raise ComponentError("A bounded .fwpkg package is required.")
    base = _base_url(config.host)
    with client_for(config) as client:
        service = _get(client, base, UPDATE_SERVICE)
        hpe = (service.get("Oem") or {}).get("Hpe") or {}
        if str(hpe.get("State") or "").upper() in BUSY:
            raise ComponentError("The iLO is busy with another update; nothing was uploaded.")
        push = urlsplit(str(hpe.get("PushUpdateUri") or service.get("HttpPushUri") or ""))
        if push.scheme or push.netloc or push.query or push.path not in {"/cgi-bin/uploadFile", "/cgi-bin/uploadFile/"}:
            raise ComponentError("The iLO did not offer its known upload endpoint; nothing was uploaded.")
        parameters = {
            "UpdateRepository": True,
            "UpdateTarget": bool(flash_now),
            "ETag": etag_for(filename),
            "Section": 0,
            "UpdateRecoverySet": False,
            "TPMOverride": False,
        }
        with _session(client, base, config) as token:
            try:
                response = client.post(
                    base + push.path,
                    files=[
                        ("sessionKey", (None, token)),
                        ("parameters", (None, json.dumps(parameters))),
                        ("file", (filename, data, "application/octet-stream")),
                    ],
                    headers={"Cookie": "sessionKey=" + token, "X-Auth-Token": token, "Expect": ""},
                    timeout=httpx.Timeout(900.0, connect=30.0, pool=30.0),
                    follow_redirects=False,
                )
            except httpx.HTTPError:
                raise ComponentError("The upload did not get a reply; its outcome is unknown.", sent=True) from None
            if response.status_code != 200:
                # The body may already have reached the iLO: never treat this as "not applied".
                raise ComponentError(f"The iLO answered the upload with HTTP {response.status_code}; its outcome is unknown.", sent=True)


def queue_bios_update(config, *, filename: str) -> str:
    """Queue a package that is already in the iLO Repository for the BIOS to apply at next start."""
    if not PACKAGE.fullmatch(filename):
        raise ComponentError("A .fwpkg file name is required.")
    name = f"Update-{secrets.randbelow(1_000_000)}-{filename}"[:64]
    body = {"Name": name, "Command": "ApplyUpdate", "Filename": filename, "UpdatableBy": ["Uefi"], "TPMOverride": False}
    with client_for(config) as client:
        try:
            response = client.post(_base_url(config.host) + TASK_QUEUE, json=body, follow_redirects=False, timeout=60.0)
        except httpx.HTTPError:
            raise ComponentError("Queuing the update got no reply; its outcome is unknown.", sent=True) from None
    if response.status_code not in {200, 201}:
        raise ComponentError(f"The iLO refused to queue {filename} (HTTP {response.status_code}).", refused=True)
    return name
