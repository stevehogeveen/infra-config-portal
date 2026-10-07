"""Narrow iLO binary upload transport used by the reviewed firmware adapter.

The guarded runner must commit its dispatch claim first. The caller supplies a
fresh authenticated session, discovered HttpPushUri and identity-bound approval.
There is deliberately no client factory, credential loader or retry loop here.
"""

import hashlib
import hmac
import re
from ipaddress import ip_address
from urllib.parse import urlsplit

import httpx
from app.services.ilo_upgrade_path import ilo_upgrade_blockers
from app.services.firmware_transport import exception_kind, response_facts

MAX_ILO_BINARY_BYTES = 64 * 1024**2


class FirmwareUploadError(ValueError):
    def __init__(self, message, *, facts=None):
        super().__init__(message)
        self.facts = facts or {}


def upload_ilo_binary(
    client: httpx.Client,
    *,
    host: str,
    http_push_uri: str,
    session_token: str,
    filename: str,
    binary: bytes,
    expected_sha256: str,
    installed_version: str,
    target_version: str,
) -> None:
    blockers = ilo_upgrade_blockers(installed_version, target_version, len(binary))
    if blockers:
        raise FirmwareUploadError(" ".join(blockers))
    try:
        address = ip_address(host)
    except ValueError:
        raise FirmwareUploadError("One exact iLO IP address is required.") from None
    parsed = urlsplit(http_push_uri)
    # Legacy iLO5 advertises the CGI endpoint. Permit only that known direct path.
    if (
        parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"/cgi-bin/uploadFile", "/cgi-bin/uploadFile/"}
    ):
        raise FirmwareUploadError("Unsupported direct-flash HttpPushUri.")
    if (
        not re.fullmatch(r"[A-Za-z0-9_-]+\.bin", filename)
        or not binary
        or len(binary) > MAX_ILO_BINARY_BYTES
    ):
        raise FirmwareUploadError("A bounded iLO BIN image is required.")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256) or not hmac.compare_digest(
        hashlib.sha256(binary).hexdigest(), expected_sha256
    ):
        raise FirmwareUploadError("Firmware binary changed since review.")
    if not re.fullmatch(r"[A-Za-z0-9._~-]{1,1024}", session_token):
        raise FirmwareUploadError("An authenticated iLO session token is required.")
    origin = "https://" + (f"[{address}]" if address.version == 6 else str(address))
    # No repository staging flags, force/TPM overrides, redirect or host reboot.
    try:
        response = client.post(
            origin + parsed.path,
            files={
                "sessionKey": (None, session_token),
                "file": (filename, binary, "application/octet-stream"),
            },
            headers={
                "X-Auth-Token": session_token,
                "Cookie": "sessionKey=" + session_token,
                "Accept": "application/json",
                "Expect": "",
                "OData-Version": "4.0",
            },
            auth=None,
            timeout=httpx.Timeout(300.0, connect=30.0, pool=30.0),
            follow_redirects=False,
        )
        if not 200 <= response.status_code < 300:
            raise FirmwareUploadError(
                "Firmware upload outcome is not confirmed; do not retry.",
                facts=response_facts(response),
            )
        if response.headers.get("content-type", "").lower().startswith("application/json"):
            body = response.json()
            if not isinstance(body, dict) or "error" in body:
                raise FirmwareUploadError(
                    "Firmware upload returned an unverified result; do not retry.",
                    facts=response_facts(response),
                )
    except FirmwareUploadError:
        raise
    except Exception as exc:
        # Raw HTTP exceptions can contain target URLs or session credentials.
        facts = response_facts(response) if "response" in locals() else {}
        raise FirmwareUploadError(
            "Firmware upload response was lost or invalid; do not retry.",
            facts={**facts, "reason": exception_kind(exc)},
        ) from None
    # Even a successful upload requires independent identity/version readback.
