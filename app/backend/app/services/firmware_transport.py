"""Allowlisted transport facts; never retain response bodies, URLs or credentials."""

import httpx


def response_facts(response):
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in {
        "application/json",
        "text/html",
        "text/plain",
        "application/octet-stream",
    }:
        content_type = "other" if content_type else "missing"
    error_present = None
    if content_type == "application/json":
        try:
            body = response.json()
            error_present = isinstance(body, dict) and "error" in body
        except ValueError:
            pass
    return {
        "http_status": response.status_code,
        "content_type": content_type,
        "json_error_present": error_present,
    }


def exception_kind(exc):
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, httpx.TransportError):
        return "transport_error"
    return "invalid_response_or_configuration"


class FirmwareDispatchError(ValueError):
    def __init__(
        self, *, stage, upload_started, facts=None, reason="invalid_response_or_configuration"
    ):
        self.upload_started = upload_started
        self.facts = {
            "stage": stage,
            "upload_started": upload_started,
            "reason": reason,
            **(facts or {}),
        }
        super().__init__(
            "Firmware upload outcome is uncertain; verify before any new review."
            if upload_started
            else "Firmware upload was not started. Prepare a new review."
        )
