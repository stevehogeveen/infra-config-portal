from __future__ import annotations

import importlib.util
import socket
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.providers.action_policy import REAL_CONTACT_MODES, current_lab_action_policy
from app.providers.base import ProviderAction, ProviderStatus
from app.providers.lab_safety import current_lab_safety
from app.providers.probe_cache import get_probe_result, record_probe_result
from app.providers.redaction import redact_sensitive
from app.services.path_utils import is_file
from app.services.provider_profile_defaults import active_server_network_defaults, first_configured

PROVIDER_ID = "esxi-readonly"
MAX_ATTEMPTS = 3
HTTPS_PORT = 443
SSH_PORT = 22
REPO_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class EsxiReadonlyConfig:
    host: str | None
    username: str | None
    password: str | None
    verify_tls: bool
    timeout_seconds: float
    ssh_timeout_seconds: float
    management_configured: bool = False

    @classmethod
    def from_settings(cls) -> "EsxiReadonlyConfig":
        profile_defaults = active_server_network_defaults()
        return cls(
            host=first_configured(profile_defaults.get("esxi_management"), settings.esxi_test_host),
            username=settings.esxi_test_username,
            password=settings.esxi_test_password,
            management_configured=settings.esxi_configured,
            verify_tls=settings.esxi_test_verify_tls,
            timeout_seconds=settings.esxi_test_timeout_seconds,
            ssh_timeout_seconds=settings.esxi_test_ssh_timeout_seconds,
        )

    @property
    def missing_fields(self) -> list[str]:
        return [] if self.host else ["ESXI_TEST_HOST"]


class EsxiReadonlyAdapter:
    def __init__(
        self,
        provider_mode: str | None = None,
        config: EsxiReadonlyConfig | None = None,
    ) -> None:
        self.provider_mode = provider_mode or settings.provider_mode
        self.config = config or EsxiReadonlyConfig.from_settings()

    def health(self) -> ProviderStatus:
        last_result, last_time = get_probe_result(PROVIDER_ID)
        missing_fields = self.config.missing_fields
        safety = current_lab_safety()
        policy = current_lab_action_policy(self.provider_mode)
        planned_target = bool(self.config.host)
        blockers: list[str] = []
        if self.config.management_configured and missing_fields:
            blockers.append(f"Missing local ESXi configuration: {', '.join(missing_fields)}.")
        if self.config.management_configured and self.provider_mode in REAL_CONTACT_MODES:
            blockers.extend(policy.readonly_blockers())

        warnings: list[str] = []
        if self.provider_mode not in REAL_CONTACT_MODES:
            warnings.append(
                "Provider mode is not local-readonly or local-lab-readwrite; ESXi probes are disabled."
            )
        if not self.config.management_configured:
            warnings.append(
                "ESXI_CONFIGURED is false; ESXi management network probes are skipped."
            )

        status = "planned-target" if planned_target else "not-configured"
        if self.config.management_configured:
            status = "missing-config" if missing_fields else "ready"
        if (
            self.config.management_configured
            and not missing_fields
            and self.provider_mode not in REAL_CONTACT_MODES
        ):
            status = "configured"
        if (
            self.config.management_configured
            and not missing_fields
            and self.provider_mode in REAL_CONTACT_MODES
            and not policy.readonly_allowed
        ):
            status = "blocked"

        probe_enabled = (
            self.provider_mode in REAL_CONTACT_MODES
            and self.config.management_configured
            and not missing_fields
            and policy.readonly_allowed
        )
        disabled_reason = "Install/configure ESXi management network before read-only probe."

        return ProviderStatus(
            id=PROVIDER_ID,
            name="ESXi Read-Only",
            kind="virtualization",
            mode=self.provider_mode,
            status=status,
            capabilities=[
                "explicit-read-only-probe",
                "https-api-reachability",
                "vim-service-version-summary",
                "ssh-reachability-check",
            ],
            message=(
                "Local ESXi target state is checked without contacting the host; "
                "the probe action is available only after ESXI_CONFIGURED=true and performs "
                "HTTPS GET and TCP reachability checks only."
            ),
            configuration={
                "management_configured": self.config.management_configured,
                "planned_target": planned_target,
                "host_configured": bool(self.config.host),
                "username_configured": bool(self.config.username),
                "password_configured": bool(self.config.password),
                "tls_verify": self.config.verify_tls,
                "timeout_seconds": self.config.timeout_seconds,
                "ssh_timeout_seconds": self.config.ssh_timeout_seconds,
                "missing_fields": missing_fields,
                "safe_next_action": (
                    "Run HTTPS GET and TCP reachability checks."
                    if probe_enabled
                    else disabled_reason
                ),
                **_tool_availability(),
                **safety.as_flags(),
            },
            blockers=blockers,
            warnings=warnings,
            safe_actions=[
                ProviderAction(
                    id="probe-esxi-readonly",
                    label="Read-Only Probe",
                    enabled=probe_enabled,
                    read_only=True,
                    reason=(
                        "Run HTTPS GET and TCP reachability checks."
                        if probe_enabled
                        else disabled_reason
                        if not self.config.management_configured
                        else (
                            "Requires ESXI_TEST_HOST, LAB_CLOSED_LOOP_ACK=YES, "
                            "LAB_READONLY_ACK=YES, and PROVIDER_MODE=local-readonly; or "
                            "complete local-lab-readwrite acknowledgements."
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
        if self.provider_mode not in REAL_CONTACT_MODES:
            return self._record_blocked(
                "Set PROVIDER_MODE=local-readonly or PROVIDER_MODE=local-lab-readwrite before running ESXi probes."
            )

        if not self.config.management_configured:
            return self._record_skipped(
                "ESXI_CONFIGURED is false; install/configure ESXi management network before "
                "read-only probe.",
                planned_target=bool(self.config.host),
            )

        policy = current_lab_action_policy(self.provider_mode)
        if not policy.readonly_allowed:
            return self._record_blocked(
                "Required lab acknowledgement flags are missing before real lab probes.",
                action_policy=policy.as_flags(),
            )

        if self.config.missing_fields:
            return self._record_blocked(
                f"Missing local ESXi configuration: {', '.join(self.config.missing_fields)}.",
                missing_fields=self.config.missing_fields,
            )

        assert self.config.host is not None
        base_url = _base_url(self.config.host)
        parsed = urlparse(base_url)
        hostname = parsed.hostname or self.config.host
        phases: list[dict[str, Any]] = []
        https_requests: list[dict[str, Any]] = []
        blockers: list[str] = []
        warnings: list[str] = []

        phases.append(
            {
                "tag": "DISCOVER",
                "message": "Checking ESXi HTTPS and SSH reachability with read-only methods.",
            }
        )

        https_reachability = _tcp_connect(hostname, HTTPS_PORT, self.config.timeout_seconds)
        ssh_reachability = _tcp_connect(hostname, SSH_PORT, self.config.ssh_timeout_seconds)
        if not https_reachability["reachable"]:
            blockers.append("ESXi HTTPS port is not reachable.")

        vim_versions: dict[str, Any] = {"available": False, "versions": []}
        if https_reachability["reachable"]:
            timeout = httpx.Timeout(self.config.timeout_seconds)
            try:
                with httpx.Client(
                    follow_redirects=False,
                    timeout=timeout,
                    trust_env=False,
                    verify=self.config.verify_tls,
                ) as client:
                    for path in ("/", "/ui/", "/sdk/vimServiceVersions.xml"):
                        response = _get_text(client, base_url, path, https_requests)
                        if path == "/sdk/vimServiceVersions.xml" and response["ok"]:
                            vim_versions = _parse_vim_service_versions(response["text"])
            except httpx.HTTPError as exc:
                blockers.append("ESXi HTTPS probe failed.")
                phases.append(
                    {
                        "tag": "BLOCKED",
                        "message": _normalized_http_error(exc),
                    }
                )
        else:
            phases.append(
                {
                    "tag": "BLOCKED",
                    "message": "HTTPS reachability failed; no ESXi API GETs were attempted.",
                }
            )

        if not ssh_reachability["reachable"]:
            warnings.append("ESXi SSH port is not reachable or not enabled.")

        if self.config.username and self.config.password:
            warnings.append(
                "ESXi credentials are configured, but this adapter does not run VM, datastore, "
                "network, or host configuration operations."
            )

        result_status = "ok" if https_reachability["reachable"] and not blockers else "failed"
        phases.append(
            {
                "tag": "VERIFY" if result_status == "ok" else "BLOCKED",
                "message": (
                    "ESXi read-only reachability checks completed."
                    if result_status == "ok"
                    else "ESXi read-only checks stopped with blockers."
                ),
            }
        )

        return self._record_result(
            {
                "provider_id": PROVIDER_ID,
                "status": result_status,
                "message": (
                    "Read-only ESXi probe completed."
                    if result_status == "ok"
                    else "Read-only ESXi probe could not complete."
                ),
                "base_url": _redacted_base_url(base_url),
                "tls_verify": self.config.verify_tls,
                "timeout_seconds": self.config.timeout_seconds,
                "max_attempts": MAX_ATTEMPTS,
                "phases": phases,
                "https_reachability": https_reachability,
                "ssh_reachability": ssh_reachability,
                "https_requests": https_requests,
                "vim_service_versions": vim_versions,
                "tool_availability": _tool_availability(),
                "not_attempted": [
                    "ESXi reinstall or reboot",
                    "network reconfiguration",
                    "datastore add/remove",
                    "VM create/delete/deploy/power operations",
                    "firewall or host configuration changes",
                ],
                "warnings": warnings,
                "blockers": blockers,
            }
        )

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

    def _record_skipped(self, message: str, **extra: Any) -> dict[str, Any]:
        return self._record_result(
            {
                "provider_id": PROVIDER_ID,
                "status": "skipped",
                "message": message,
                "warnings": [message],
                "blockers": [],
                "not_attempted": [
                    "HTTPS reachability check",
                    "SSH reachability check",
                    "ESXi API GET requests",
                ],
                **extra,
            }
        )

    def _record_result(self, result: dict[str, Any]) -> dict[str, Any]:
        return record_probe_result(PROVIDER_ID, redact_sensitive(result, self._redaction_values()))

    def _redaction_values(self) -> list[str | None]:
        values: list[str | None] = [
            self.config.host,
            self.config.username,
            self.config.password,
        ]
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


def _tcp_connect(host: str, port: int, timeout_seconds: float) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.monotonic()
        try:
            with socket.create_connection((host, port), timeout=timeout_seconds):
                attempts.append(
                    {
                        "attempt": attempt,
                        "status": "ok",
                        "elapsed_ms": int((time.monotonic() - started) * 1000),
                    }
                )
                return {"reachable": True, "port": port, "attempts": attempts}
        except OSError as exc:
            attempts.append(
                {
                    "attempt": attempt,
                    "status": "failed",
                    "error": exc.__class__.__name__,
                    "elapsed_ms": int((time.monotonic() - started) * 1000),
                }
            )
    return {"reachable": False, "port": port, "attempts": attempts}


def _get_text(
    client: httpx.Client,
    base_url: str,
    path: str,
    requests: list[dict[str, Any]],
) -> dict[str, Any]:
    last_error: httpx.HTTPError | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = client.get(_url(base_url, path))
            requests.append(
                {
                    "path": path,
                    "attempt": attempt,
                    "status_code": response.status_code,
                    "content_type": response.headers.get("content-type", ""),
                }
            )
            return {
                "ok": 200 <= response.status_code < 400,
                "status_code": response.status_code,
                "text": response.text,
            }
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            requests.append(
                {
                    "path": path,
                    "attempt": attempt,
                    "status": "retrying" if attempt < MAX_ATTEMPTS else "failed",
                    "error": _normalized_http_error(exc),
                }
            )
            if attempt == MAX_ATTEMPTS:
                raise

    if last_error is not None:
        raise last_error
    raise RuntimeError("ESXi GET retry loop exited without a response.")


def _url(base_url: str, path: str) -> str:
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base_url}{path}"


def _parse_vim_service_versions(xml_text: str) -> dict[str, Any]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {"available": False, "versions": [], "error": "unparseable-xml"}

    versions: list[str] = []
    for element in root.iter():
        if element.tag.endswith("version") and element.text:
            version = element.text.strip()
            if version and version not in versions:
                versions.append(version)
    return {"available": bool(versions), "versions": versions[:12]}


def _normalized_http_error(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if "CERTIFICATE_VERIFY_FAILED" in str(exc):
        return "tls-verification-failed"
    return exc.__class__.__name__


def _tool_availability() -> dict[str, bool]:
    return {
        "govc_available": _which("govc"),
        "powercli_available": _which("pwsh"),
        "pyvmomi_available": importlib.util.find_spec("pyVim") is not None,
    }


def _which(name: str) -> bool:
    from shutil import which

    if which(name) is not None:
        return True
    for directory in (Path(sys.executable).parent, REPO_ROOT / ".local" / "bin"):
        candidate = directory / name
        if is_file(candidate):
            return True
    return False


def _dangerous_actions() -> list[ProviderAction]:
    return [
        ProviderAction(
            id="esxi-reboot",
            label="Reboot Host",
            enabled=False,
            read_only=False,
            reason="ESXi reboot and restart operations are blocked.",
        ),
        ProviderAction(
            id="esxi-network-change",
            label="Change Network",
            enabled=False,
            read_only=False,
            reason="Management network, firewall, and vSwitch changes are disabled.",
        ),
        ProviderAction(
            id="esxi-datastore-change",
            label="Change Datastore",
            enabled=False,
            read_only=False,
            reason="Datastore add, remove, rescan, and format operations are disabled.",
        ),
        ProviderAction(
            id="esxi-vm-operation",
            label="VM Operation",
            enabled=False,
            read_only=False,
            reason="Create, delete, deploy, and power operations are blocked.",
        ),
    ]
