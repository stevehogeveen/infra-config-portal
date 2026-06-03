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
                "redfish-service-root",
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
                    label="Read-Only Probe",
                    enabled=probe_enabled,
                    read_only=True,
                    reason=(
                        "Run GET-only Redfish inventory checks."
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
            result.update(
                {
                    "status": "failed",
                    "message": f"Redfish GET returned HTTP {exc.response.status_code}.",
                    "blockers": ["Redfish endpoint returned an HTTP error."],
                }
            )
        except httpx.HTTPError as exc:
            result.update(
                {
                    "status": "failed",
                    "message": f"Redfish read-only probe failed: {exc}",
                    "blockers": ["Redfish endpoint could not be reached or read."],
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
