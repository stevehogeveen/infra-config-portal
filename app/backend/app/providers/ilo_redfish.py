from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.providers.base import ProviderAction, ProviderStatus
from app.providers.lab_safety import current_lab_safety
from app.providers.probe_cache import get_probe_result, record_probe_result
from app.providers.redaction import redact_sensitive

PROVIDER_ID = "ilo-redfish"
MAX_GET_ATTEMPTS = 3
ENDPOINT_DETECTION_PATHS = (
    "/redfish/v1/",
    "/redfish/v1",
    "/",
    "/xmldata?item=All",
)
REDFISH_ROOT_PATHS = {"/redfish/v1/", "/redfish/v1"}
LEGACY_XML_PATH = "/xmldata?item=All"
WEB_ROOT_PATH = "/"


@dataclass(frozen=True)
class IloRedfishConfig:
    host: str | None
    username: str | None
    password: str | None
    verify_tls: bool
    timeout_seconds: float

    @classmethod
    def from_settings(cls) -> "IloRedfishConfig":
        return cls(
            host=settings.ilo_test_host,
            username=settings.ilo_test_username,
            password=settings.ilo_test_password,
            verify_tls=settings.ilo_test_verify_tls,
            timeout_seconds=settings.ilo_test_timeout_seconds,
        )

    @property
    def missing_fields(self) -> list[str]:
        missing = []
        if not self.host:
            missing.append("ILO_TEST_HOST")
        if not self.username:
            missing.append("ILO_TEST_USERNAME")
        if not self.password:
            missing.append("ILO_TEST_PASSWORD")
        return missing

    @property
    def configured(self) -> bool:
        return not self.missing_fields


class IloRedfishAdapter:
    def __init__(
        self,
        provider_mode: str | None = None,
        config: IloRedfishConfig | None = None,
    ) -> None:
        self.provider_mode = provider_mode or settings.provider_mode
        self.config = config or IloRedfishConfig.from_settings()

    def health(self) -> ProviderStatus:
        last_result, last_time = get_probe_result(PROVIDER_ID)
        missing_fields = self.config.missing_fields
        safety = current_lab_safety()
        blockers = [
            f"Missing local iLO configuration: {', '.join(missing_fields)}."
        ] if missing_fields else []
        if self.provider_mode == "local-readonly":
            blockers.extend(safety.blockers)
        warnings: list[str] = []
        if self.provider_mode != "local-readonly":
            warnings.append("Provider mode is not local-readonly; Redfish probes are disabled.")

        status = "missing-config" if missing_fields else "ready"
        if not missing_fields and self.provider_mode != "local-readonly":
            status = "configured"
        if not missing_fields and self.provider_mode == "local-readonly" and not safety.readonly_allowed:
            status = "blocked"

        probe_enabled = (
            self.provider_mode == "local-readonly"
            and not missing_fields
            and safety.readonly_allowed
        )

        return ProviderStatus(
            id=PROVIDER_ID,
            name="HPE iLO / Redfish",
            kind="hardware-management",
            mode=self.provider_mode,
            status=status,
            capabilities=[
                "explicit-read-only-probe",
                "get-only-endpoint-detection",
                "redfish-service-root",
                "legacy-ilo-xml-detection",
                "redfish-manager-summary",
                "redfish-system-summary",
                "redfish-chassis-summary",
            ],
            message=(
                "Local iLO configuration is checked without contacting Redfish; "
                "the probe button performs explicit GET-only requests."
            ),
            configuration={
                "host_configured": bool(self.config.host),
                "username_configured": bool(self.config.username),
                "password_configured": bool(self.config.password),
                "tls_verify": self.config.verify_tls,
                "timeout_seconds": self.config.timeout_seconds,
                "missing_fields": missing_fields,
                **safety.as_flags(),
            },
            blockers=blockers,
            warnings=warnings,
            safe_actions=[
                ProviderAction(
                    id="probe-ilo-redfish",
                    label="GET-Only Endpoint Detection",
                    enabled=probe_enabled,
                    read_only=True,
                    reason=(
                        "Run GET-only endpoint detection and Redfish inventory checks."
                        if probe_enabled
                        else (
                            "Requires complete local config, LAB_CLOSED_LOOP_ACK=YES, "
                            "LAB_READONLY_ACK=YES, and PROVIDER_MODE=local-readonly."
                        )
                    ),
                    method="POST",
                    endpoint=f"/api/v1/providers/{PROVIDER_ID}/probe",
                )
            ],
            disabled_actions=_dangerous_actions(),
            last_probe_result=last_result,
            last_probe_time=last_time,
        )

    def probe(self) -> dict[str, Any]:
        if self.provider_mode != "local-readonly":
            return self._record_blocked(
                "Set PROVIDER_MODE=local-readonly before running iLO probes."
            )

        safety = current_lab_safety()
        if not safety.readonly_allowed:
            return self._record_blocked(
                "Set LAB_CLOSED_LOOP_ACK=YES and LAB_READONLY_ACK=YES before real lab probes.",
                safety=safety.as_flags(),
            )

        if self.config.missing_fields:
            return self._record_blocked(
                f"Missing local iLO configuration: {', '.join(self.config.missing_fields)}.",
                missing_fields=self.config.missing_fields,
            )

        assert self.config.host is not None
        assert self.config.username is not None
        assert self.config.password is not None

        base_url = _base_url(self.config.host)
        requests: list[dict[str, Any]] = []
        result: dict[str, Any] = {
            "provider_id": PROVIDER_ID,
            "status": "ok",
            "message": "Read-only Redfish probe completed.",
            "base_url": _redacted_base_url(base_url),
            "tls_verify": self.config.verify_tls,
            "timeout_seconds": self.config.timeout_seconds,
            "max_attempts": MAX_GET_ATTEMPTS,
            "requests": requests,
            "service_root": {},
            "managers": [],
            "systems": [],
            "chassis": [],
            "power": [],
            "thermal": [],
            "firmware": [],
            "endpoint_detection": {
                "classification": "not_checked",
                "message": "GET-only endpoint detection has not run.",
                "checks": [],
                "redfish_status": "not_checked",
                "legacy_status": "not_checked",
                "web_status": "not_checked",
                "next_safe_action": "Run explicit GET-only endpoint detection.",
            },
            "warnings": [],
            "blockers": [],
        }

        try:
            timeout = httpx.Timeout(self.config.timeout_seconds)
            with httpx.Client(
                auth=(self.config.username, self.config.password),
                follow_redirects=False,
                timeout=timeout,
                trust_env=False,
                verify=self.config.verify_tls,
            ) as client:
                detection = _detect_endpoints(client, base_url)
                result["endpoint_detection"] = detection
                requests.extend(detection["checks"])
                if detection["classification"] != "redfish_available":
                    result.update(
                        {
                            "status": "failed",
                            "message": detection["message"],
                            "blockers": [detection["next_safe_action"]],
                        }
                    )
                    return self._record_result(result)

                root = detection.get("redfish_root_payload")
                if not isinstance(root, dict):
                    root = _get_json(client, base_url, "/redfish/v1/", requests)
                result["service_root"] = _resource_summary(root)
                result["managers"] = _collection_summaries(
                    client,
                    base_url,
                    _odata_id(root.get("Managers")),
                    requests,
                )
                result["systems"] = _collection_summaries(
                    client,
                    base_url,
                    _odata_id(root.get("Systems")),
                    requests,
                )
                chassis = _collection_summaries(
                    client,
                    base_url,
                    _odata_id(root.get("Chassis")),
                    requests,
                    include_links=True,
                )
                result["chassis"] = [_strip_links(item) for item in chassis]
                result["power"] = _linked_summaries(client, base_url, chassis, "Power", requests)
                result["thermal"] = _linked_summaries(client, base_url, chassis, "Thermal", requests)
                result["firmware"] = _firmware_summaries(client, base_url, root, requests)
        except httpx.HTTPStatusError as exc:
            detection = result.get("endpoint_detection")
            endpoint_message = (
                detection.get("message")
                if isinstance(detection, dict) and detection.get("message")
                else f"Redfish GET returned HTTP {exc.response.status_code}."
            )
            result.update(
                {
                    "status": "failed",
                    "message": endpoint_message,
                    "blockers": [_http_status_next_safe_action(exc.response.status_code)],
                }
            )
        except httpx.HTTPError as exc:
            classification = _classify_http_error(exc)
            message = _endpoint_message(classification)
            result.update(
                {
                    "status": "failed",
                    "message": message,
                    "endpoint_detection": {
                        "classification": classification,
                        "message": message,
                        "checks": [],
                        "redfish_status": classification,
                        "legacy_status": "not_checked",
                        "web_status": "not_checked",
                        "next_safe_action": _endpoint_next_safe_action(classification),
                    },
                    "blockers": [_endpoint_next_safe_action(classification)],
                }
            )

        return self._record_result(result)

    def _record_blocked(self, message: str, **extra: Any) -> dict[str, Any]:
        return self._record_result(
            {
                "provider_id": PROVIDER_ID,
                "status": "blocked",
                "message": message,
                "warnings": [],
                "blockers": [message],
                **extra,
            }
        )

    def _record_result(self, result: dict[str, Any]) -> dict[str, Any]:
        redacted = redact_sensitive(result, self._redaction_values())
        return record_probe_result(PROVIDER_ID, redacted)

    def _redaction_values(self) -> list[str | None]:
        values: list[str | None] = [self.config.password, self.config.username, self.config.host]
        if self.config.host:
            base_url = _base_url(self.config.host)
            parsed = urlparse(base_url)
            values.extend([base_url, parsed.netloc, parsed.hostname])
        return values


def _base_url(host: str) -> str:
    host = host.strip().rstrip("/")
    if host.startswith("http://") or host.startswith("https://"):
        return host
    return f"https://{host}"


def _redacted_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    return f"{parsed.scheme}://REDACTED"


def _detect_endpoints(client: httpx.Client, base_url: str) -> dict[str, Any]:
    checks = [_endpoint_check(client, base_url, path) for path in ENDPOINT_DETECTION_PATHS]
    classification = _classify_endpoint_checks(checks)
    detection = {
        "classification": classification,
        "message": _endpoint_message(classification),
        "checks": checks,
        "redfish_status": _endpoint_status(checks, REDFISH_ROOT_PATHS),
        "legacy_status": _endpoint_status(checks, {LEGACY_XML_PATH}),
        "web_status": _endpoint_status(checks, {WEB_ROOT_PATH}),
        "next_safe_action": _endpoint_next_safe_action(classification),
        "diagnostic_hints": _endpoint_diagnostic_hints(classification),
    }

    redfish_check = next(
        (
            check
            for check in checks
            if check["path"] in REDFISH_ROOT_PATHS
            and check.get("classification") == "redfish_available"
        ),
        None,
    )
    if redfish_check and isinstance(redfish_check.get("_json_payload"), dict):
        detection["redfish_root_payload"] = redfish_check["_json_payload"]

    for check in checks:
        check.pop("_json_payload", None)
    return detection


def _endpoint_check(client: httpx.Client, base_url: str, path: str) -> dict[str, Any]:
    try:
        response = client.get(_redfish_url(base_url, path))
    except httpx.HTTPError as exc:
        return {
            "path": path,
            "error_class": exc.__class__.__name__,
            "classification": _classify_http_error(exc),
        }

    check: dict[str, Any] = {
        "path": path,
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", "-"),
        "classification": _classify_endpoint_response(path, response.status_code),
    }
    if response.status_code == 200 and path in REDFISH_ROOT_PATHS:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                check["_json_payload"] = payload
        except ValueError:
            check["classification"] = "redfish_http_error"
    return check


def _classify_endpoint_response(path: str, status_code: int) -> str:
    if status_code in {401, 403}:
        return "auth_failed"
    if path in REDFISH_ROOT_PATHS:
        if status_code == 200:
            return "redfish_available"
        if status_code == 404:
            return "redfish_not_found"
        return "redfish_http_error"
    if path == LEGACY_XML_PATH:
        return "legacy_available" if status_code == 200 else "legacy_not_found"
    if path == WEB_ROOT_PATH:
        return "web_available" if status_code == 200 else "web_not_found"
    return "unknown_endpoint_state"


def _classify_endpoint_checks(checks: list[dict[str, Any]]) -> str:
    if any(check.get("classification") == "tls_failed" for check in checks):
        return "tls_failed"
    if any(check.get("classification") == "network_unreachable" for check in checks):
        return "network_unreachable"
    if any(
        check.get("path") in REDFISH_ROOT_PATHS
        and check.get("status_code") in {401, 403}
        for check in checks
    ):
        return "auth_failed"
    if any(
        check.get("path") in REDFISH_ROOT_PATHS
        and check.get("classification") == "redfish_available"
        for check in checks
    ):
        return "redfish_available"

    redfish_404 = any(
        check.get("path") in REDFISH_ROOT_PATHS and check.get("status_code") == 404
        for check in checks
    )
    legacy_200 = any(
        check.get("path") == LEGACY_XML_PATH and check.get("status_code") == 200
        for check in checks
    )
    web_200 = any(
        check.get("path") == WEB_ROOT_PATH and check.get("status_code") == 200
        for check in checks
    )
    if redfish_404 and legacy_200:
        return "legacy_available_redfish_not_found"
    if redfish_404 and web_200:
        return "web_available_redfish_not_found"
    if legacy_200:
        return "legacy_available"

    http_checks = [check for check in checks if "status_code" in check]
    if http_checks and all(check.get("status_code") == 404 for check in http_checks):
        return "endpoint_not_found_or_wrong_target"
    if any(
        check.get("path") in REDFISH_ROOT_PATHS
        and isinstance(check.get("status_code"), int)
        and check.get("status_code") not in {200, 401, 403, 404}
        for check in checks
    ):
        return "redfish_http_error"
    return "unknown_endpoint_state"


def _classify_http_error(exc: httpx.HTTPError) -> str:
    text = str(exc).lower()
    if any(token in text for token in ("certificate", "tls", "ssl")):
        return "tls_failed"
    if isinstance(exc, httpx.TimeoutException):
        return "network_unreachable"
    if isinstance(exc, httpx.TransportError):
        return "network_unreachable"
    return "unknown_endpoint_state"


def _endpoint_status(checks: list[dict[str, Any]], paths: set[str]) -> str:
    matching = [check for check in checks if check.get("path") in paths]
    if not matching:
        return "not_checked"
    if any(
        check.get("classification") in {"redfish_available", "legacy_available", "web_available"}
        for check in matching
    ):
        return "available"
    if any(check.get("status_code") in {401, 403} for check in matching):
        return "auth_failed"
    if any(check.get("classification") == "tls_failed" for check in matching):
        return "tls_failed"
    if any(check.get("classification") == "network_unreachable" for check in matching):
        return "network_unreachable"
    if all(check.get("status_code") == 404 for check in matching if "status_code" in check):
        return "not_found"
    if any("status_code" in check for check in matching):
        return "http_error"
    return "unknown_endpoint_state"


def _endpoint_message(classification: str) -> str:
    messages = {
        "redfish_available": "Redfish root is available. GET-only inventory discovery can continue.",
        "redfish_http_error": "Redfish root returned an unexpected HTTP error.",
        "legacy_available": "Legacy iLO endpoint is available.",
        "legacy_available_redfish_not_found": "Legacy iLO endpoint is available, but Redfish root was not found.",
        "web_available_redfish_not_found": (
            "The web root responded, but Redfish root was not found. HTTP web "
            "reachability alone does not prove this target supports Redfish. Verify "
            "the address is iLO, check for a legacy iLO generation, confirm Redfish is "
            "available, and rule out an unrelated web server."
        ),
        "endpoint_not_found_or_wrong_target": "All checked iLO endpoint paths returned 404; verify the target address.",
        "auth_failed": "iLO authentication failed; review configured credentials or iLO permissions.",
        "tls_failed": "TLS verification failed; lab/self-signed iLO may require ILO_TEST_VERIFY_TLS=false.",
        "network_unreachable": "iLO target is unreachable; review routing, firewall, address, and connectivity.",
        "not_checked": "GET-only endpoint detection has not run.",
        "unknown_endpoint_state": "iLO endpoint state could not be classified from GET-only checks.",
    }
    return messages.get(classification, messages["unknown_endpoint_state"])


def _endpoint_next_safe_action(classification: str) -> str:
    actions = {
        "redfish_available": "Continue with GET-only Redfish inventory discovery. No settings were changed.",
        "redfish_http_error": "Review iLO Redfish support and endpoint status before retrying GET-only detection.",
        "legacy_available": "Use a dedicated read-only legacy iLO discovery path if Redfish is unavailable.",
        "legacy_available_redfish_not_found": "Use legacy read-only discovery context or verify whether this iLO supports Redfish.",
        "web_available_redfish_not_found": (
            "Verify target identity in trusted records or the web UI, confirm iLO "
            "generation and Redfish support, then retry GET-only endpoint detection. "
            "No settings were changed."
        ),
        "endpoint_not_found_or_wrong_target": "Verify target identity/address and retry GET-only endpoint detection.",
        "auth_failed": "Review credentials or iLO permissions locally, without printing secrets.",
        "tls_failed": "For lab/self-signed iLO, set ILO_TEST_VERIFY_TLS=false locally and retry.",
        "network_unreachable": "Check network reachability, routing, firewall, and target power/network state.",
        "not_checked": "Run explicit GET-only endpoint detection from Provider Status.",
        "unknown_endpoint_state": "Review sanitized endpoint matrix and retry GET-only detection.",
    }
    return actions.get(classification, actions["unknown_endpoint_state"])


def _endpoint_diagnostic_hints(classification: str) -> list[str]:
    hints = {
        "web_available_redfish_not_found": [
            "Wrong IP: the responding web server may be a server OS, proxy, or another device.",
            "Legacy iLO: older generations may not expose Redfish at /redfish/v1.",
            "Redfish unavailable: the management UI may be reachable while the API is disabled or unsupported.",
            "Non-iLO web server: the root page responds, but iLO-specific probes did not.",
            "Keep using GET-only endpoint detection until target identity and Redfish support are confirmed.",
        ],
        "legacy_available_redfish_not_found": [
            "Legacy iLO XML responded, so use read-only legacy discovery context if Redfish is unavailable.",
            "Verify whether this iLO generation and firmware level support Redfish before planning Redfish inventory.",
        ],
        "endpoint_not_found_or_wrong_target": [
            "Verify the configured address is the iLO management interface.",
            "Confirm the device is reachable on HTTPS and retry GET-only endpoint detection.",
        ],
        "auth_failed": [
            "Review the configured credentials or iLO permissions locally without printing secrets.",
        ],
        "tls_failed": [
            "For lab or self-signed iLO certificates, disable TLS verification only in local configuration.",
        ],
        "network_unreachable": [
            "Check routing, firewall, target power, and iLO network connectivity.",
        ],
    }
    return hints.get(classification, [])


def _http_status_next_safe_action(status_code: int) -> str:
    if status_code in {401, 403}:
        return _endpoint_next_safe_action("auth_failed")
    if status_code == 404:
        return _endpoint_next_safe_action("endpoint_not_found_or_wrong_target")
    return _endpoint_next_safe_action("redfish_http_error")


def _get_json(
    client: httpx.Client,
    base_url: str,
    path: str,
    requests: list[dict[str, Any]],
) -> dict[str, Any]:
    last_error: httpx.HTTPError | None = None
    for attempt in range(1, MAX_GET_ATTEMPTS + 1):
        try:
            response = client.get(_redfish_url(base_url, path))
            requests.append(
                {
                    "path": path,
                    "attempt": attempt,
                    "status_code": response.status_code,
                }
            )
            response.raise_for_status()
            payload = response.json()
            return payload if isinstance(payload, dict) else {"value": payload}
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            requests.append(
                {
                    "path": path,
                    "attempt": attempt,
                    "status": "retrying" if attempt < MAX_GET_ATTEMPTS else "failed",
                    "error": _normalized_http_error(exc),
                }
            )
            if attempt == MAX_GET_ATTEMPTS:
                raise

    if last_error is not None:
        raise last_error
    raise RuntimeError("Redfish GET retry loop exited without a response.")


def _normalized_http_error(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    return exc.__class__.__name__


def _redfish_url(base_url: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base_url}{path}"


def _odata_id(value: Any) -> str | None:
    if isinstance(value, dict) and isinstance(value.get("@odata.id"), str):
        return value["@odata.id"]
    return None


def _collection_summaries(
    client: httpx.Client,
    base_url: str,
    collection_path: str | None,
    requests: list[dict[str, Any]],
    include_links: bool = False,
) -> list[dict[str, Any]]:
    if not collection_path:
        return []
    collection = _get_json(client, base_url, collection_path, requests)
    members = collection.get("Members", [])
    if not isinstance(members, list):
        return []

    summaries = []
    for member in members[:3]:
        path = _odata_id(member)
        if not path:
            continue
        payload = _get_json(client, base_url, path, requests)
        summary = _resource_summary(payload)
        if include_links:
            summary["_links"] = payload
        summaries.append(summary)
    return summaries


def _linked_summaries(
    client: httpx.Client,
    base_url: str,
    summaries: list[dict[str, Any]],
    link_name: str,
    requests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    linked = []
    for summary in summaries:
        links = summary.get("_links")
        path = _odata_id(links.get(link_name)) if isinstance(links, dict) else None
        if path:
            linked.append(_resource_summary(_get_json(client, base_url, path, requests)))
    return linked


def _firmware_summaries(
    client: httpx.Client,
    base_url: str,
    root: dict[str, Any],
    requests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    update_service_path = _odata_id(root.get("UpdateService"))
    if not update_service_path:
        return []
    update_service = _get_json(client, base_url, update_service_path, requests)
    firmware_path = _odata_id(update_service.get("FirmwareInventory"))
    return _collection_summaries(client, base_url, firmware_path, requests)


def _resource_summary(payload: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "@odata.id",
        "Id",
        "Name",
        "Description",
        "Manufacturer",
        "Model",
        "ProductName",
        "SerialNumber",
        "FirmwareVersion",
        "PowerState",
        "Status",
    )
    return {key: payload[key] for key in keys if key in payload}


def _strip_links(summary: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in summary.items() if key != "_links"}


def _dangerous_actions() -> list[ProviderAction]:
    return [
        ProviderAction(
            id="ilo-power-action",
            label="Power Action",
            enabled=False,
            read_only=False,
            reason="Power on, power off, and reset actions are disabled.",
        ),
        ProviderAction(
            id="ilo-virtual-media",
            label="Virtual Media",
            enabled=False,
            read_only=False,
            reason="Mounting or ejecting virtual media is not exposed.",
        ),
        ProviderAction(
            id="ilo-firmware-update",
            label="Firmware Update",
            enabled=False,
            read_only=False,
            reason="Firmware update actions are blocked in this preview.",
        ),
        ProviderAction(
            id="ilo-user-change",
            label="User Changes",
            enabled=False,
            read_only=False,
            reason="iLO account changes are blocked.",
        ),
    ]
