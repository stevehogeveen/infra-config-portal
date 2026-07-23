from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx

from app.core.config import settings
from app.providers.action_policy import (
    ActionCategory,
    LOCAL_LAB_MODE,
    LOCAL_READONLY_MODE,
    REAL_CONTACT_MODES,
    current_lab_action_policy,
)
from app.providers.base import ProviderAction, ProviderStatus
from app.providers.probe_cache import get_probe_result, record_probe_result
from app.providers.redaction import redact_sensitive
from app.services.list_utils import unique_preserving_order

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
INVENTORY_COLLECTION_AUTH_NEXT_ACTION = (
    "Review iLO account permissions or Redfish authentication method. No settings were changed."
)


class RedfishJsonDecodeError(RuntimeError):
    def __init__(self, path: str, status_code: int) -> None:
        super().__init__(f"Redfish GET {path} returned HTTP {status_code} with invalid JSON.")
        self.path = path
        self.status_code = status_code


@dataclass(frozen=True)
class IloRedfishConfig:
    host: str | None
    username: str | None
    password: str | None
    verify_tls: bool
    timeout_seconds: float
    host_source: str = "runtime_env"
    fallback_hosts: tuple[str, ...] = ()
    fallback_host_sources: tuple[str, ...] = ()

    @classmethod
    def from_settings(cls) -> "IloRedfishConfig":
        host, host_source, fallback_hosts, fallback_host_sources = _configured_ilo_targets()
        return cls(
            host=host,
            username=settings.ilo_test_username,
            password=settings.ilo_test_password,
            verify_tls=settings.ilo_test_verify_tls,
            timeout_seconds=settings.ilo_test_timeout_seconds,
            host_source=host_source,
            fallback_hosts=fallback_hosts,
            fallback_host_sources=fallback_host_sources,
        )

    @property
    def missing_fields(self) -> list[str]:
        missing = []
        if not self.target_candidates:
            missing.append("ILO_TEST_HOST")
        if not self.username:
            missing.append("ILO_TEST_USERNAME")
        if not self.password:
            missing.append("ILO_TEST_PASSWORD")
        return missing

    @property
    def configured(self) -> bool:
        return not self.missing_fields

    @property
    def target_candidates(self) -> list[dict[str, str]]:
        candidates: list[dict[str, str]] = []
        seen: set[str] = set()
        raw_candidates: list[tuple[str | None, str]] = [(self.host, self.host_source)]
        raw_candidates.extend(
            (
                host,
                self.fallback_host_sources[index]
                if index < len(self.fallback_host_sources)
                else "fallback",
            )
            for index, host in enumerate(self.fallback_hosts)
        )
        for host, source in raw_candidates:
            if not host:
                continue
            clean_host = host.strip()
            dedupe_key = clean_host.casefold()
            if not clean_host or dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            candidates.append({"host": clean_host, "source": source})
        return candidates


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
        last_probe_status = _probe_status(last_result)
        last_probe_target_matches_candidates = _probe_target_matches_candidates(
            last_result,
            self.config.target_candidates,
        )
        last_probe_target_matches_active_profile = _probe_target_matches_host(
            last_result,
            _active_saved_profile_ilo_host(),
        )
        last_probe_target_matches_runtime_host = _probe_target_matches_host(
            last_result,
            settings.ilo_test_host,
        )
        policy = current_lab_action_policy(self.provider_mode)
        blockers = [
            f"Missing local iLO configuration: {', '.join(missing_fields)}."
        ] if missing_fields else []
        if self.provider_mode in REAL_CONTACT_MODES:
            blockers.extend(policy.readonly_blockers())
        warnings: list[str] = []
        if self.provider_mode not in REAL_CONTACT_MODES:
            warnings.append(
                "Provider mode is not local-readonly or local-lab-readwrite; Redfish probes are disabled."
            )
        if self.provider_mode == LOCAL_LAB_MODE:
            warnings.append(
                "local-lab-readwrite permits explicitly allowlisted real-lab workflow categories only."
            )

        status = "missing-config" if missing_fields else "not_checked"
        if not missing_fields and self.provider_mode not in REAL_CONTACT_MODES:
            status = "configured"
        elif not missing_fields and self.provider_mode in REAL_CONTACT_MODES and blockers:
            status = "blocked"
        elif not missing_fields and self.provider_mode in REAL_CONTACT_MODES:
            status = _health_status_from_probe(last_result, last_probe_target_matches_candidates)

        if status in {"blocked", "failed"} and isinstance(last_result, dict):
            probe_blockers = [
                str(item)
                for item in last_result.get("blockers", [])
                if isinstance(item, str) and item.strip()
            ]
            blockers.extend(item for item in probe_blockers if item not in blockers)

        probe_enabled = (
            self.provider_mode in REAL_CONTACT_MODES
            and not missing_fields
            and not policy.readonly_blockers()
        )
        requirement_reason = _probe_requirement_reason(self.provider_mode)

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
            message=_health_message_from_probe(status, last_result),
            configuration={
                "host_configured": bool(self.config.host),
                "host_source": self.config.host_source,
                "fallback_hosts_configured": len(self.config.fallback_hosts),
                "target_candidate_count": len(self.config.target_candidates),
                "target_candidate_sources": [
                    candidate["source"] for candidate in self.config.target_candidates
                ],
                "username_configured": bool(self.config.username),
                "password_configured": bool(self.config.password),
                "tls_verify": self.config.verify_tls,
                "timeout_seconds": self.config.timeout_seconds,
                "missing_fields": missing_fields,
                "lab_policy": policy.status_summary(),
                "last_probe_status": last_probe_status or "not_checked",
                "last_probe_target_source": (
                    last_result.get("target_source")
                    if isinstance(last_result, dict)
                    else None
                ),
                "last_probe_target_fingerprint_present": bool(
                    isinstance(last_result, dict) and last_result.get("target_fingerprint")
                ),
                "last_probe_target_matches_configured_candidates": last_probe_target_matches_candidates,
                "last_probe_target_matches_active_profile": last_probe_target_matches_active_profile,
                "last_probe_target_matches_runtime_host": last_probe_target_matches_runtime_host,
            },
            blockers=blockers,
            warnings=warnings,
            safe_actions=[
                ProviderAction(
                    id="probe-ilo-redfish",
                    label="Read-Only Redfish Inventory",
                    enabled=probe_enabled,
                    read_only=True,
                    reason=(
                        "Run read-only endpoint detection, authentication, and Redfish inventory checks."
                        if probe_enabled
                        else requirement_reason
                    ),
                    method="POST",
                    endpoint=f"/api/v1/providers/{PROVIDER_ID}/probe",
                )
            ],
            disabled_actions=_dangerous_actions(policy),
            last_probe_result=last_result,
            last_probe_time=last_time,
        )

    def probe(self) -> dict[str, Any]:
        if self.provider_mode not in REAL_CONTACT_MODES:
            return self._record_blocked(
                "Set PROVIDER_MODE=local-readonly or PROVIDER_MODE=local-lab-readwrite before running iLO probes."
            )

        policy = current_lab_action_policy(self.provider_mode)
        policy_blockers = policy.readonly_blockers()
        if policy_blockers:
            return self._record_blocked(
                "iLO read-only probe is blocked by lab acknowledgement policy.",
                blockers=policy_blockers,
                action_policy=policy.status_summary(),
            )

        if self.config.missing_fields:
            return self._record_blocked(
                f"Missing local iLO configuration: {', '.join(self.config.missing_fields)}.",
                missing_fields=self.config.missing_fields,
            )

        assert self.config.username is not None
        assert self.config.password is not None

        candidates = self.config.target_candidates
        candidate_attempts: list[dict[str, Any]] = []
        last_result: dict[str, Any] | None = None
        for index, candidate in enumerate(candidates, start=1):
            result = self._probe_target(
                str(candidate["host"]),
                str(candidate["source"]),
                policy,
                candidate_index=index,
                candidate_count=len(candidates),
            )
            candidate_attempts.append(_candidate_probe_summary(result))
            last_result = result
            if result.get("status") == "ok" or not _try_next_ilo_candidate(result):
                if len(candidates) > 1:
                    result["candidate_attempts"] = candidate_attempts
                return self._record_result(result)

        if last_result is None:
            return self._record_blocked(
                "Missing local iLO configuration: ILO_TEST_HOST.",
                missing_fields=["ILO_TEST_HOST"],
            )
        if len(candidates) > 1:
            last_result["candidate_attempts"] = candidate_attempts
        return self._record_result(last_result)

    def _probe_target(
        self,
        host: str,
        host_source: str,
        policy: Any,
        *,
        candidate_index: int,
        candidate_count: int,
    ) -> dict[str, Any]:
        assert self.config.username is not None
        assert self.config.password is not None

        base_url = _base_url(host)
        requests: list[dict[str, Any]] = []
        result: dict[str, Any] = {
            "provider_id": PROVIDER_ID,
            "status": "ok",
            "message": "Read-only Redfish probe completed.",
            "base_url": _redacted_base_url(base_url),
            "target_source": host_source,
            "target_fingerprint": ilo_target_fingerprint(host),
            "candidate_index": candidate_index,
            "target_candidate_count": candidate_count,
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
            "network_adapters": [],
            "network_identity": {"status": "not_checked"},
            "time_and_dns": {"status": "not_checked"},
            "licenses": [],
            "storage": {
                "status": "not_checked",
                "controllers": [],
                "physical_drives": [],
                "logical_drives": [],
                "warnings": [],
            },
            "legacy_identity": {},
            "authentication_method": "basic",
            "redfish_auth": {
                "status": "not_attempted",
                "method": "redfish_session_token",
                "reason": "Basic authentication was sufficient or inventory collection access has not been checked.",
            },
            "endpoint_detection": {
                "classification": "not_checked",
                "message": "GET-only endpoint detection has not run.",
                "checks": [],
                "redfish_status": "not_checked",
                "legacy_status": "not_checked",
                "web_status": "not_checked",
                "inventory_collection_status": "not_checked",
                "inventory_collection_classification": "not_checked",
                "inventory_collection_checks": [],
                "auth_failure_classification": "not_checked",
                "auth_recovery_hint": "not_checked",
                "next_safe_action": "Run explicit GET-only endpoint detection.",
            },
            "warnings": [],
            "blockers": [],
            "action_policy": {
                "provider_mode": self.provider_mode,
                "readonly": "allowed" if policy.readonly_allowed else "blocked",
                "local_state_write": _local_state_write_status(policy, self.provider_mode),
                "device_writes": "policy-gated",
            },
            "not_attempted": _not_attempted_actions(),
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
                result["legacy_identity"] = detection.get("legacy_identity", {})
                requests.extend(detection["checks"])
                if detection["classification"] != "redfish_available":
                    result.update(
                        {
                            "status": "failed",
                            "message": detection["message"],
                            "blockers": [detection["next_safe_action"]],
                        }
                    )
                    return result

                root = detection.get("redfish_root_payload")
                if not isinstance(root, dict):
                    root = _get_json(client, base_url, "/redfish/v1/", requests)
                collection_checks = _inventory_collection_access_checks(
                    client,
                    base_url,
                    root,
                    requests,
                )
                unauthorized_collection = next(
                    (
                        check
                        for check in collection_checks
                        if check.get("status_code") in {401, 403}
                    ),
                    None,
                )
                if unauthorized_collection is not None:
                    session_client = _open_redfish_session_client(
                        base_url,
                        root,
                        requests,
                        self.config,
                    )
                    result["redfish_auth"] = session_client["summary"]
                    if session_client.get("client") is not None:
                        with session_client["client"] as token_client:
                            try:
                                collection_checks = _inventory_collection_access_checks(
                                    token_client,
                                    base_url,
                                    root,
                                    requests,
                                )
                                unauthorized_collection = next(
                                    (
                                        check
                                        for check in collection_checks
                                        if check.get("status_code") in {401, 403}
                                    ),
                                    None,
                                )
                                if unauthorized_collection is None:
                                    result["authentication_method"] = "redfish_session_token"
                                    detection = _mark_inventory_collection_authorized(
                                        detection,
                                        collection_checks,
                                        auth_method="redfish_session_token",
                                    )
                                    result["endpoint_detection"] = detection
                                    _populate_inventory_result(result, token_client, base_url, root, requests)
                                    return result
                            finally:
                                _close_redfish_session(
                                    token_client,
                                    base_url,
                                    str(session_client.get("location") or ""),
                                    requests,
                                    result["redfish_auth"],
                                )

                    detection = _classify_inventory_auth_failure(
                        detection,
                        int(unauthorized_collection["status_code"]),
                        collection_checks=collection_checks,
                    )
                    result.update(
                        {
                            "status": "failed",
                            "endpoint_detection": detection,
                            "message": detection["message"],
                            "blockers": [detection["next_safe_action"]],
                        }
                    )
                    return result
                result["endpoint_detection"] = _mark_inventory_collection_authorized(
                    detection,
                    collection_checks,
                    auth_method="basic",
                )
                _populate_inventory_result(result, client, base_url, root, requests)
        except RedfishJsonDecodeError as exc:
            classification = "redfish_invalid_json"
            message = _endpoint_message(classification)
            result.update(
                {
                    "status": "failed",
                    "message": message,
                    "endpoint_detection": {
                        "classification": classification,
                        "message": message,
                        "checks": requests,
                        "redfish_status": "invalid_json",
                        "legacy_status": "not_checked",
                        "web_status": "not_checked",
                        "inventory_collection_status": "failed",
                        "inventory_collection_classification": classification,
                        "inventory_collection_checks": [],
                        "auth_failure_classification": "not_checked",
                        "auth_recovery_hint": "not_checked",
                        "failed_path": exc.path,
                        "failed_status_code": exc.status_code,
                        "next_safe_action": _endpoint_next_safe_action(classification),
                    },
                    "blockers": [_endpoint_next_safe_action(classification)],
                }
            )
        except httpx.HTTPStatusError as exc:
            detection = _classify_inventory_auth_failure(
                result.get("endpoint_detection"),
                exc.response.status_code,
            )
            endpoint_message = str(
                detection.get("message")
                or f"Redfish GET returned HTTP {exc.response.status_code}."
            )
            result.update(
                {
                    "status": "failed",
                    "endpoint_detection": detection,
                    "message": endpoint_message,
                    "blockers": [
                        str(
                            detection.get("next_safe_action")
                            or _http_status_next_safe_action(exc.response.status_code)
                        )
                    ],
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
                        "inventory_collection_status": "not_checked",
                        "inventory_collection_classification": "not_checked",
                        "inventory_collection_checks": [],
                        "auth_failure_classification": "not_checked",
                        "auth_recovery_hint": "not_checked",
                        "next_safe_action": _endpoint_next_safe_action(classification),
                    },
                    "blockers": [_endpoint_next_safe_action(classification)],
                }
            )

        return result

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
        result = _attach_write_target_evidence(result)
        redacted = redact_sensitive(result, self._redaction_values())
        previous_result, previous_checked_at = get_probe_result(PROVIDER_ID)
        redacted = _preserve_legacy_identity(redacted, previous_result, previous_checked_at)
        return record_probe_result(PROVIDER_ID, redacted)

    def _redaction_values(self) -> list[str | None]:
        return ilo_redfish_redaction_values(self.config)


def _candidate_probe_summary(result: dict[str, Any]) -> dict[str, Any]:
    requests = result.get("requests")
    return {
        "candidate_index": result.get("candidate_index"),
        "target_source": result.get("target_source"),
        "target_fingerprint": result.get("target_fingerprint"),
        "status": result.get("status"),
        "classification": _probe_classification(result),
        "request_count": len(requests) if isinstance(requests, list) else 0,
        "message": result.get("message"),
    }


def _preserve_legacy_identity(
    result: dict[str, Any],
    previous_result: dict[str, Any] | None,
    previous_checked_at: str | None,
) -> dict[str, Any]:
    legacy_identity = result.get("legacy_identity")
    if isinstance(legacy_identity, dict) and legacy_identity.get("current_firmware"):
        return result
    if not isinstance(previous_result, dict):
        return result
    previous_identity = previous_result.get("legacy_identity")
    if not isinstance(previous_identity, dict) or not previous_identity.get("current_firmware"):
        return result

    preserved = dict(result)
    preserved["legacy_identity"] = {
        **previous_identity,
        "source": previous_identity.get("source") or LEGACY_XML_PATH,
        "preserved_from_previous_probe": True,
        "previous_checked_at": previous_checked_at,
    }
    detection = preserved.get("endpoint_detection")
    if isinstance(detection, dict):
        preserved["endpoint_detection"] = {
            **detection,
            "legacy_identity": preserved["legacy_identity"],
        }
    warnings = list(preserved.get("warnings") or [])
    warnings.append(
        "Preserved previous legacy iLO identity after the current Redfish inventory probe returned no legacy identity."
    )
    preserved["warnings"] = warnings
    return preserved


def _probe_status(result: dict[str, Any] | None) -> str:
    if not isinstance(result, dict):
        return ""
    return str(result.get("status") or "").strip().lower()


def _health_status_from_probe(
    result: dict[str, Any] | None,
    target_matches_candidates: bool,
) -> str:
    status = _probe_status(result)
    if not status:
        return "not_checked"
    if status == "ok":
        return "ready" if target_matches_candidates else "target_mismatch"
    if status in {"blocked", "failed"}:
        return status
    return status


def _health_message_from_probe(status: str, result: dict[str, Any] | None) -> str:
    result_message = str(result.get("message") or "").strip() if isinstance(result, dict) else ""
    if status == "ready":
        return result_message or "Last read-only iLO Redfish probe proved the current target."
    if status == "target_mismatch":
        return "Last iLO proof is not bound to the current target. Run Check this iLO IP again."
    if status in {"blocked", "failed"}:
        return f"Last iLO read-only check {status}: {result_message or 'review blockers.'}"
    if status == "not_checked":
        return "iLO access is configured, but no read-only Redfish probe has proved this target yet."
    if status == "missing-config":
        return "Enter iLO host, username, and password before running the read-only Redfish check."
    if status == "configured":
        return (
            "Local iLO configuration is present without contacting Redfish; "
            "run an explicit read-only check before trusting the map."
        )
    return result_message or "Run an explicit read-only iLO check before trusting the map."


def _probe_target_matches_candidates(
    result: dict[str, Any] | None,
    candidates: list[dict[str, str]],
) -> bool:
    target_fingerprint = str(result.get("target_fingerprint") or "") if isinstance(result, dict) else ""
    if not target_fingerprint:
        return False
    return target_fingerprint in {
        fingerprint
        for candidate in candidates
        if (fingerprint := ilo_target_fingerprint(candidate.get("host")))
    }


def _probe_target_matches_host(result: dict[str, Any] | None, host: str | None) -> bool:
    target_fingerprint = str(result.get("target_fingerprint") or "") if isinstance(result, dict) else ""
    host_fingerprint = ilo_target_fingerprint(host)
    return bool(target_fingerprint and host_fingerprint and target_fingerprint == host_fingerprint)


def ilo_target_fingerprint(host: str | None) -> str | None:
    clean_host = _clean_target_host(host)
    if not clean_host:
        return None
    return hashlib.sha256(clean_host.casefold().encode("utf-8")).hexdigest()[:16]


def _try_next_ilo_candidate(result: dict[str, Any]) -> bool:
    return _probe_classification(result) in {
        "network_unreachable",
        "endpoint_not_found_or_wrong_target",
        "web_available_redfish_not_found",
        "legacy_available_redfish_not_found",
        "redfish_http_error",
        "unknown_endpoint_state",
    }


def _probe_classification(result: dict[str, Any]) -> str:
    detection = result.get("endpoint_detection")
    if isinstance(detection, dict) and detection.get("classification"):
        return str(detection["classification"])
    return "unknown_endpoint_state"


def _configured_ilo_targets() -> tuple[str | None, str, tuple[str, ...], tuple[str, ...]]:
    profile_host = _active_saved_profile_ilo_host()
    first_access_host = _saved_ilo_first_access_host()
    initial_profile_host = _active_saved_profile_ilo_initial_host()
    if profile_host:
        fallback_hosts, fallback_sources = _fallback_ilo_targets(
            profile_host,
            [
                (first_access_host, "control_access_original_dhcp_ip"),
                (initial_profile_host, "active_lab_profile_initial_ilo"),
            ],
        )
        return profile_host, "active_lab_profile", fallback_hosts, fallback_sources

    runtime_host = _clean_target_host(settings.ilo_test_host)
    if runtime_host:
        fallback_hosts, fallback_sources = _fallback_ilo_targets(
            runtime_host,
            [
                (first_access_host, "control_access_original_dhcp_ip"),
                (initial_profile_host, "active_lab_profile_initial_ilo"),
            ],
        )
        return runtime_host, "runtime_env", fallback_hosts, fallback_sources

    if first_access_host:
        fallback_hosts, fallback_sources = _fallback_ilo_targets(
            first_access_host,
            [(initial_profile_host, "active_lab_profile_initial_ilo")],
        )
        return first_access_host, "control_access_original_dhcp_ip", fallback_hosts, fallback_sources
    if initial_profile_host:
        return initial_profile_host, "active_lab_profile_initial_ilo", (), ()
    return None, "runtime_env", (), ()


def _configured_ilo_host() -> tuple[str | None, str]:
    host, host_source, _fallback_hosts, _fallback_sources = _configured_ilo_targets()
    return host, host_source


def _fallback_ilo_targets(
    primary_host: str,
    candidates: list[tuple[str | None, str]],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    fallback_hosts: list[str] = []
    fallback_sources: list[str] = []
    seen = {primary_host}
    for host, source in candidates:
        clean_host = _clean_target_host(host)
        if not clean_host or clean_host in seen:
            continue
        seen.add(clean_host)
        fallback_hosts.append(clean_host)
        fallback_sources.append(source)
    return tuple(fallback_hosts), tuple(fallback_sources)


def _active_saved_profile_ilo_host() -> str | None:
    try:
        from app.services.lab_profiles import active_lab_profile_context

        context = active_lab_profile_context()
    except Exception:
        return None

    active = context.get("active_profile") if isinstance(context, dict) else {}
    if not isinstance(active, dict) or active.get("source") != "saved":
        return None
    plan = context.get("resolved_address_plan") if isinstance(context, dict) else {}
    if not isinstance(plan, dict):
        return None
    return _clean_target_host(plan.get("ilo"))


def _active_saved_profile_ilo_initial_host() -> str | None:
    try:
        from app.services.lab_profiles import active_lab_profile_context

        context = active_lab_profile_context()
    except Exception:
        return None

    active = context.get("active_profile") if isinstance(context, dict) else {}
    if not isinstance(active, dict) or active.get("source") != "saved":
        return None
    plan = context.get("resolved_address_plan") if isinstance(context, dict) else {}
    if not isinstance(plan, dict):
        return None
    return _clean_target_host(plan.get("ilo_initial"))


def _saved_ilo_first_access_host() -> str | None:
    try:
        from app.services.control_access import control_access_configs
        from app.services.lab_profiles import active_lab_profile_context

        context = active_lab_profile_context()
    except Exception:
        return None

    active = context.get("active_profile") if isinstance(context, dict) else {}
    if not isinstance(active, dict) or active.get("source") != "saved":
        return None
    try:
        configs = control_access_configs(active)
    except Exception:
        return None
    ilo_config = configs.get("ilo") if isinstance(configs, dict) else {}
    if not isinstance(ilo_config, dict):
        return None
    return _clean_target_host(ilo_config.get("original_dhcp_ip"))


def _clean_target_host(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    host = value.strip()
    return host or None


def ilo_redfish_redaction_values(config: IloRedfishConfig | None = None) -> list[str | None]:
    config = config or IloRedfishConfig.from_settings()
    values: list[str | None] = [
        settings.ilo_test_host,
        settings.ilo_test_username,
        settings.ilo_test_password,
        config.host,
        config.username,
        config.password,
    ]
    values.extend(config.fallback_hosts)
    for candidate in config.target_candidates:
        values.append(candidate.get("host"))
    for host in (settings.ilo_test_host, config.host, *config.fallback_hosts):
        if not host:
            continue
        base_url = _base_url(host)
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
        "inventory_collection_status": "not_checked",
        "inventory_collection_classification": "not_checked",
        "inventory_collection_checks": [],
        "auth_failure_classification": "not_checked",
        "auth_recovery_hint": "not_checked",
        "next_safe_action": _endpoint_next_safe_action(classification),
        "diagnostic_hints": _endpoint_diagnostic_hints(classification),
    }

    redfish_check = next(
        (
            check
            for check in checks
            if check["path"] in REDFISH_ROOT_PATHS
            and check.get("classification") == "redfish_root_available"
        ),
        None,
    )
    if redfish_check and isinstance(redfish_check.get("_json_payload"), dict):
        detection["redfish_root_payload"] = redfish_check["_json_payload"]

    legacy_check = next(
        (
            check
            for check in checks
            if check["path"] == LEGACY_XML_PATH
            and check.get("classification") == "legacy_available"
        ),
        None,
    )
    if legacy_check and isinstance(legacy_check.get("_legacy_identity"), dict):
        detection["legacy_identity"] = legacy_check["_legacy_identity"]

    for check in checks:
        check.pop("_json_payload", None)
        check.pop("_legacy_identity", None)
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
            check["classification"] = "redfish_invalid_json"
    if response.status_code == 200 and path == LEGACY_XML_PATH:
        identity = _legacy_xml_identity(response.text)
        if identity:
            check["_legacy_identity"] = identity
    return check


def _legacy_xml_identity(xml_text: str) -> dict[str, Any]:
    if not xml_text.strip():
        return {}
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return {}

    values: dict[str, str] = {}
    for element in root.iter():
        key = _xml_tag_name(element.tag)
        text = (element.text or "").strip()
        if key and text:
            values.setdefault(key.upper(), text)

    model = _first_xml_value(
        values,
        "SPN",
        "PRODUCTNAME",
        "PRODUCT_NAME",
        "SERVERNAME",
        "SERVER_NAME",
        "MODEL",
    )
    management_product = _first_xml_value(values, "PN", "MPN", "MANAGEMENTPROCESSOR")
    firmware = _first_xml_value(values, "FWRI", "FIRMWAREVERSION", "FIRMWARE_VERSION")
    generation = (
        _legacy_ilo_generation(management_product)
        or _legacy_ilo_generation(model)
        or _first_legacy_generation(values.values())
    )
    serial_present = bool(
        _first_xml_value(values, "SBSN", "SERIALNUMBER", "SERIAL_NUMBER", "SERIAL")
    )

    identity: dict[str, Any] = {
        "source": LEGACY_XML_PATH,
        "serial_present": serial_present,
    }
    if model:
        identity["model"] = model
    if firmware:
        identity["current_firmware"] = firmware
    if generation:
        identity["ilo_generation"] = generation
    if management_product:
        identity["management_product"] = management_product
    return identity


def _xml_tag_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _first_xml_value(values: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        value = values.get(key.upper())
        if value:
            return value
    return None


def _legacy_ilo_generation(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.lower().replace("-", " ")
    for generation in (
        "ilo 6",
        "ilo6",
        "lights out 6",
        "ilo 5",
        "ilo5",
        "lights out 5",
        "ilo 4",
        "ilo4",
        "lights out 4",
        "ilo 3",
        "ilo3",
        "lights out 3",
    ):
        if generation in normalized:
            version = generation.rsplit(" ", 1)[-1]
            return f"ilo{version}"
    return None


def _first_legacy_generation(values: Any) -> str | None:
    for value in values:
        generation = _legacy_ilo_generation(value)
        if generation:
            return generation
    return None


def _classify_inventory_auth_failure(
    detection_value: Any,
    status_code: int,
    *,
    collection_checks: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if not isinstance(detection_value, dict):
        detection: dict[str, Any] = {}
    else:
        detection = dict(detection_value)

    if status_code not in {401, 403}:
        detection.setdefault("classification", "redfish_http_error")
        detection.setdefault("message", _endpoint_message(str(detection["classification"])))
        detection.setdefault("next_safe_action", _http_status_next_safe_action(status_code))
        detection.setdefault(
            "diagnostic_hints",
            _endpoint_diagnostic_hints(str(detection["classification"])),
        )
        return detection

    detection.update(
        {
            "classification": "redfish_inventory_auth_failed",
            "message": (
                "Redfish root is available, but inventory collections returned "
                f"HTTP {status_code}. Inventory discovery cannot continue with the current "
                "account or authentication method."
            ),
            "redfish_status": detection.get("redfish_status") or "available",
            "inventory_collection_status": "unauthorized",
            "inventory_collection_classification": "redfish_collection_unauthorized",
            "inventory_collection_checks": collection_checks
            if collection_checks is not None
            else detection.get("inventory_collection_checks", []),
            "auth_failure_classification": "basic_auth_rejected_or_insufficient_privilege",
            "auth_recovery_hint": "session_auth_may_be_required",
            "next_safe_action": INVENTORY_COLLECTION_AUTH_NEXT_ACTION,
            "diagnostic_hints": _endpoint_diagnostic_hints("redfish_inventory_auth_failed"),
        }
    )
    return detection


def _mark_inventory_collection_authorized(
    detection_value: Any,
    collection_checks: list[dict[str, Any]],
    *,
    auth_method: str,
) -> dict[str, Any]:
    detection = dict(detection_value) if isinstance(detection_value, dict) else {}
    available = any(check.get("status_code") == 200 for check in collection_checks)
    detection.update(
        {
            "inventory_collection_status": "available" if available else "checked",
            "inventory_collection_classification": "redfish_collection_available"
            if available
            else "redfish_collection_checked",
            "inventory_collection_checks": collection_checks,
        }
    )
    if auth_method == "redfish_session_token":
        detection["auth_failure_classification"] = "basic_auth_recovered_with_session_token"
        detection["auth_recovery_hint"] = "session_auth_used"
        hints = list(detection.get("diagnostic_hints") or [])
        hints.append("Basic auth was insufficient for inventory collections; Redfish session auth succeeded.")
        detection["diagnostic_hints"] = hints
    return detection


def _open_redfish_session_client(
    base_url: str,
    root: dict[str, Any],
    requests: list[dict[str, Any]],
    config: IloRedfishConfig,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "status": "blocked",
        "method": "redfish_session_token",
        "login_collection_path": None,
        "auth_header_received": False,
        "location_present": False,
        "message": "Redfish session authentication did not run.",
    }
    session_path = _session_collection_path(base_url, root, requests, config)
    summary["login_collection_path"] = session_path
    if not session_path:
        summary["message"] = "Redfish session collection path was not found."
        return {"summary": summary, "client": None, "location": None}
    if not config.username or not config.password:
        summary["message"] = "iLO username/password are not configured for session authentication."
        return {"summary": summary, "client": None, "location": None}

    response: httpx.Response | None = None
    try:
        with httpx.Client(
            follow_redirects=False,
            timeout=httpx.Timeout(config.timeout_seconds),
            trust_env=False,
            verify=config.verify_tls,
        ) as auth_client:
            response = auth_client.post(
                _redfish_url(base_url, session_path),
                json={"UserName": config.username, "Password": config.password},
            )
    except httpx.HTTPError as exc:
        requests.append(
            {
                "method": "POST",
                "path": session_path,
                "status": "failed",
                "error": _normalized_http_error(exc),
                "classification": _classify_http_error(exc),
            }
        )
        summary["message"] = "Redfish session authentication failed before a response was returned."
        return {"summary": summary, "client": None, "location": None}

    token = response.headers.get("X-Auth-Token")
    location = response.headers.get("Location")
    token_received = bool(token)
    requests.append(
        {
            "method": "POST",
            "path": session_path,
            "status_code": response.status_code,
            "classification": "redfish_session_created"
            if response.status_code in {200, 201} and token_received
            else "redfish_session_failed",
            "auth_header_received": token_received,
            "location_present": bool(location),
        }
    )
    summary.update(
        {
            "status": "ready" if response.status_code in {200, 201} and token_received else "blocked",
            "auth_header_received": token_received,
            "location_present": bool(location),
            "message": "Redfish session token acquired."
            if response.status_code in {200, 201} and token_received
            else f"Redfish session authentication returned HTTP {response.status_code}.",
        }
    )
    if summary["status"] != "ready" or not token:
        return {"summary": summary, "client": None, "location": None}

    return {
        "summary": summary,
        "client": httpx.Client(
            headers={"X-Auth-Token": token},
            follow_redirects=False,
            timeout=httpx.Timeout(config.timeout_seconds),
            trust_env=False,
            verify=config.verify_tls,
        ),
        "location": location,
    }


def _session_collection_path(
    base_url: str,
    root: dict[str, Any],
    requests: list[dict[str, Any]],
    config: IloRedfishConfig,
) -> str | None:
    links = root.get("Links") if isinstance(root.get("Links"), dict) else {}
    sessions_path = _odata_id(links.get("Sessions"))
    if sessions_path:
        return sessions_path

    session_service_path = _odata_id(root.get("SessionService"))
    if session_service_path:
        try:
            with httpx.Client(
                auth=(config.username, config.password),
                follow_redirects=False,
                timeout=httpx.Timeout(config.timeout_seconds),
                trust_env=False,
                verify=config.verify_tls,
            ) as client:
                service = _get_json(client, base_url, session_service_path, requests)
            sessions_path = _odata_id(service.get("Sessions"))
            if sessions_path:
                return sessions_path
        except httpx.HTTPError:
            return f"{session_service_path.rstrip('/')}/Sessions/"
    return "/redfish/v1/SessionService/Sessions/"


def _close_redfish_session(
    client: httpx.Client,
    base_url: str,
    location: str,
    requests: list[dict[str, Any]],
    summary: dict[str, Any],
) -> None:
    if not location:
        summary["cleanup_status"] = "not_attempted"
        summary["cleanup_reason"] = "No session location was returned."
        return
    try:
        response = client.delete(_redfish_url(base_url, location))
        requests.append(
            {
                "method": "DELETE",
                "path": location,
                "status_code": response.status_code,
                "classification": "redfish_session_closed"
                if response.status_code in {200, 202, 204}
                else "redfish_session_close_failed",
            }
        )
        summary["cleanup_status"] = "completed" if response.status_code in {200, 202, 204} else "warning"
    except httpx.HTTPError as exc:
        requests.append(
            {
                "method": "DELETE",
                "path": location,
                "status": "failed",
                "error": _normalized_http_error(exc),
                "classification": _classify_http_error(exc),
            }
        )
        summary["cleanup_status"] = "warning"
        summary["cleanup_error"] = _normalized_http_error(exc)


def _populate_inventory_result(
    result: dict[str, Any],
    client: httpx.Client,
    base_url: str,
    root: dict[str, Any],
    requests: list[dict[str, Any]],
) -> None:
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
    result["network_adapters"] = _network_adapter_summaries(
        client,
        base_url,
        result["systems"],
        requests,
    )
    result["storage"] = _storage_discovery(
        client,
        base_url,
        result["systems"],
        requests,
    )
    result["network_identity"] = _manager_network_identity(client, base_url, root, requests)
    result["time_and_dns"] = _manager_time_and_dns_settings(client, base_url, root, requests)
    result["licenses"] = _manager_license_summaries(client, base_url, root, requests)


def _manager_time_and_dns_settings(
    client: httpx.Client,
    base_url: str,
    root: dict[str, Any],
    requests: list[dict[str, Any]],
) -> dict[str, Any]:
    managers_path = _odata_id(root.get("Managers"))
    if not managers_path:
        return {"status": "not_supported", "message": "Service root does not expose Managers."}
    try:
        collection = _get_json(client, base_url, managers_path, requests)
        members = collection.get("Members", [])
        manager_path = _odata_id(members[0]) if isinstance(members, list) and members else None
        if not manager_path:
            return {"status": "not_available", "message": "No manager resource was found."}
        manager = _get_json(client, base_url, manager_path, requests)

        oem = manager.get("Oem") if isinstance(manager.get("Oem"), dict) else {}
        hpe_oem = oem.get("Hpe") if isinstance(oem.get("Hpe"), dict) else {}
        time_zone = hpe_oem.get("TimeZone") if isinstance(hpe_oem.get("TimeZone"), dict) else {}
        timezone = time_zone.get("Name")

        ntp_servers: list[str] = []
        ntp_protocol_enabled: bool | None = None
        domain_name: str | None = None
        dns_servers: list[str] = []

        network_protocol_path = _odata_id(manager.get("NetworkProtocol"))
        if network_protocol_path:
            network_protocol = _get_json(client, base_url, network_protocol_path, requests)
            ntp = (
                network_protocol.get("NTP") if isinstance(network_protocol.get("NTP"), dict) else {}
            )
            raw_servers = ntp.get("NTPServers")
            ntp_servers = raw_servers if isinstance(raw_servers, list) else []
            raw_enabled = ntp.get("ProtocolEnabled")
            ntp_protocol_enabled = raw_enabled if isinstance(raw_enabled, bool) else None
            domain_name = _derive_domain_name(
                network_protocol.get("HostName"),
                network_protocol.get("FQDN"),
            )
            np_oem = (
                network_protocol.get("Oem") if isinstance(network_protocol.get("Oem"), dict) else {}
            )
            np_hpe = np_oem.get("Hpe") if isinstance(np_oem.get("Hpe"), dict) else {}
            raw_dns = np_hpe.get("DNSServers")
            dns_servers = raw_dns if isinstance(raw_dns, list) else []
            snmp = (
                network_protocol.get("SNMP") if isinstance(network_protocol.get("SNMP"), dict) else {}
            )
            raw_snmp_enabled = snmp.get("ProtocolEnabled")
            snmp_protocol_enabled = raw_snmp_enabled if isinstance(raw_snmp_enabled, bool) else None
        else:
            snmp_protocol_enabled = None

        return {
            "status": "ok",
            "timezone": timezone,
            "ntp_servers": ntp_servers,
            "ntp_protocol_enabled": ntp_protocol_enabled,
            "domain_name": domain_name,
            "dns_servers": dns_servers,
            "snmp_protocol_enabled": snmp_protocol_enabled,
        }
    except (RedfishJsonDecodeError, httpx.HTTPError) as exc:
        return {"status": "unavailable", "message": f"Time/DNS settings read failed: {exc}"}


def _derive_domain_name(hostname: Any, fqdn: Any) -> str | None:
    if not isinstance(fqdn, str) or not fqdn:
        return None
    if isinstance(hostname, str) and hostname and fqdn.startswith(f"{hostname}."):
        return fqdn[len(hostname) + 1 :]
    if "." in fqdn:
        return fqdn.split(".", 1)[1]
    return None


def _manager_network_identity(
    client: httpx.Client,
    base_url: str,
    root: dict[str, Any],
    requests: list[dict[str, Any]],
) -> dict[str, Any]:
    managers_path = _odata_id(root.get("Managers"))
    if not managers_path:
        return {"status": "not_supported", "message": "Service root does not expose Managers."}
    try:
        collection = _get_json(client, base_url, managers_path, requests)
        members = collection.get("Members", [])
        manager_path = _odata_id(members[0]) if isinstance(members, list) and members else None
        if not manager_path:
            return {"status": "not_available", "message": "No manager resource was found."}
        manager = _get_json(client, base_url, manager_path, requests)
        eth_path = _odata_id(manager.get("EthernetInterfaces"))
        if not eth_path:
            return {
                "status": "not_supported",
                "message": "Manager resource does not expose EthernetInterfaces.",
            }
        eth_collection = _get_json(client, base_url, eth_path, requests)
        eth_members = eth_collection.get("Members", [])
        iface_path = (
            _odata_id(eth_members[0]) if isinstance(eth_members, list) and eth_members else None
        )
        if not iface_path:
            return {
                "status": "not_available",
                "message": "Manager EthernetInterfaces collection has no members.",
            }
        iface = _get_json(client, base_url, iface_path, requests)
    except (RedfishJsonDecodeError, httpx.HTTPError) as exc:
        return {"status": "unavailable", "message": f"Network identity read failed: {exc}"}

    ipv4_addresses = iface.get("IPv4Addresses")
    first_ipv4 = (
        ipv4_addresses[0] if isinstance(ipv4_addresses, list) and ipv4_addresses else {}
    )
    dhcpv4 = iface.get("DHCPv4") if isinstance(iface.get("DHCPv4"), dict) else {}
    vlan = iface.get("VLAN") if isinstance(iface.get("VLAN"), dict) else {}
    name_servers = iface.get("NameServers")
    return {
        "status": "ok",
        "@odata.id": iface_path,
        "dns_name": iface.get("HostName"),
        "fqdn_value": iface.get("FQDN"),
        "dhcp_enabled": dhcpv4.get("DHCPEnabled") if isinstance(dhcpv4, dict) else None,
        "ip_address": first_ipv4.get("Address") if isinstance(first_ipv4, dict) else None,
        "subnet_mask": first_ipv4.get("SubnetMask") if isinstance(first_ipv4, dict) else None,
        "gateway": first_ipv4.get("Gateway") if isinstance(first_ipv4, dict) else None,
        "vlan_enabled": vlan.get("VLANEnable") if isinstance(vlan, dict) else None,
        "vlan_id": vlan.get("VLANId") if isinstance(vlan, dict) else None,
        "name_servers": name_servers if isinstance(name_servers, list) else [],
    }


def _manager_license_summaries(
    client: httpx.Client,
    base_url: str,
    root: dict[str, Any],
    requests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    license_service_path = _odata_id(root.get("LicenseService"))
    if not license_service_path:
        return []
    try:
        service = _get_json(client, base_url, license_service_path, requests)
        licenses_path = _odata_id(service.get("Licenses"))
        if not licenses_path:
            return []
        collection = _get_json(client, base_url, licenses_path, requests)
        members = collection.get("Members", [])
        if not isinstance(members, list):
            return []
        summaries: list[dict[str, Any]] = []
        for member in members[:5]:
            path = _odata_id(member)
            if not path:
                continue
            payload = _get_json(client, base_url, path, requests)
            status = payload.get("Status") if isinstance(payload.get("Status"), dict) else {}
            summaries.append(
                {
                    "@odata.id": path,
                    "name": payload.get("Name"),
                    "product_type": payload.get("LicenseType"),
                    "status_state": status.get("State"),
                }
            )
        return summaries
    except (RedfishJsonDecodeError, httpx.HTTPError):
        return []


def _inventory_collection_access_checks(
    client: httpx.Client,
    base_url: str,
    root: dict[str, Any],
    requests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for name, path in _inventory_collection_paths(root):
        check = _collection_access_check(client, base_url, name, path)
        checks.append(check)
        requests.append(
            {
                "path": path,
                "status_code": check.get("status_code"),
                "error": check.get("error_class"),
                "classification": check.get("classification"),
            }
        )
    return checks


def _inventory_collection_paths(root: dict[str, Any]) -> list[tuple[str, str]]:
    paths: list[tuple[str, str]] = []
    for name in ("Managers", "Systems", "Chassis", "UpdateService"):
        path = _odata_id(root.get(name))
        if path:
            paths.append((name, path))
    return _unique_named_paths(paths)


def _collection_access_check(
    client: httpx.Client,
    base_url: str,
    name: str,
    path: str,
) -> dict[str, Any]:
    try:
        response = client.get(_redfish_url(base_url, path))
    except httpx.HTTPError as exc:
        return {
            "name": name,
            "path": path,
            "error_class": exc.__class__.__name__,
            "classification": _classify_http_error(exc),
        }

    return {
        "name": name,
        "path": path,
        "status_code": response.status_code,
        "content_type": response.headers.get("content-type", "-"),
        "classification": _classify_collection_access_response(response.status_code),
    }


def _classify_collection_access_response(status_code: int) -> str:
    if status_code in {401, 403}:
        return "redfish_collection_unauthorized"
    if status_code == 200:
        return "redfish_collection_available"
    if status_code == 404:
        return "redfish_collection_not_found"
    return "redfish_http_error"


def _classify_endpoint_response(path: str, status_code: int) -> str:
    if status_code in {401, 403}:
        return "auth_failed"
    if path in REDFISH_ROOT_PATHS:
        if status_code == 200:
            return "redfish_root_available"
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
    if any(
        check.get("path") in REDFISH_ROOT_PATHS
        and check.get("status_code") in {401, 403}
        for check in checks
    ):
        return "auth_failed"
    if any(
        check.get("path") in REDFISH_ROOT_PATHS
        and check.get("classification") == "redfish_root_available"
        for check in checks
    ):
        return "redfish_available"
    if any(check.get("classification") == "redfish_invalid_json" for check in checks):
        return "redfish_invalid_json"
    if any(check.get("classification") == "network_unreachable" for check in checks):
        return "network_unreachable"

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
        check.get("classification")
        in {"redfish_available", "redfish_root_available", "legacy_available", "web_available"}
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
        "redfish_root_available": "Redfish root is available.",
        "redfish_inventory_auth_failed": (
            "Redfish root is available, but inventory collections are unauthorized."
        ),
        "redfish_collection_unauthorized": "Redfish inventory collection GET returned unauthorized.",
        "basic_auth_rejected_or_insufficient_privilege": (
            "Basic authentication was rejected or lacks sufficient inventory privilege."
        ),
        "session_auth_may_be_required": "Session authentication may be required for inventory collection.",
        "redfish_invalid_json": "Redfish endpoint returned HTTP 200 with a non-JSON or malformed JSON body.",
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
        "redfish_root_available": "Continue only after inventory collection authorization is confirmed.",
        "redfish_inventory_auth_failed": INVENTORY_COLLECTION_AUTH_NEXT_ACTION,
        "redfish_collection_unauthorized": INVENTORY_COLLECTION_AUTH_NEXT_ACTION,
        "basic_auth_rejected_or_insufficient_privilege": INVENTORY_COLLECTION_AUTH_NEXT_ACTION,
        "session_auth_may_be_required": INVENTORY_COLLECTION_AUTH_NEXT_ACTION,
        "redfish_invalid_json": (
            "Verify the target is iLO Redfish and retry GET-only detection after endpoint health is corrected."
        ),
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
        "redfish_inventory_auth_failed": [
            "Redfish root responded, so endpoint detection is only partial.",
            "Inventory collections require additional permission or a different Redfish authentication method.",
            "Do not continue inventory discovery until authorization is resolved.",
        ],
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
            try:
                payload = response.json()
            except ValueError as exc:
                requests.append(
                    {
                        "path": path,
                        "attempt": attempt,
                        "status": "failed",
                        "status_code": response.status_code,
                        "error": "invalid_json",
                    }
                )
                raise RedfishJsonDecodeError(path, response.status_code) from exc
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
        summary.setdefault("@odata.id", path)
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


def _network_adapter_summaries(
    client: httpx.Client,
    base_url: str,
    systems: list[dict[str, Any]],
    requests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    adapters: list[dict[str, Any]] = []
    for system in systems:
        system_path = system.get("@odata.id")
        if not isinstance(system_path, str):
            continue
        system_payload = _get_json(client, base_url, system_path, requests)
        paths = _network_collection_paths(system_payload, system_path)
        for path in paths:
            adapters.extend(_network_collection_members(client, base_url, path, requests))
    return adapters


def _network_collection_paths(system_payload: dict[str, Any], system_path: str) -> list[str]:
    paths: list[str] = []
    for key in ("NetworkAdapters", "EthernetInterfaces"):
        path = _odata_id(system_payload.get(key))
        if path:
            paths.append(path)
    for suffix in ("NetworkAdapters", "EthernetInterfaces"):
        paths.append(f"{system_path.rstrip('/')}/{suffix}/")
    return _unique_paths(paths)


def _network_collection_members(
    client: httpx.Client,
    base_url: str,
    path: str,
    requests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    try:
        collection = _get_json(client, base_url, path, requests)
    except httpx.HTTPStatusError as exc:
        if 400 <= exc.response.status_code < 500:
            return []
        raise
    members = collection.get("Members", [])
    if not isinstance(members, list):
        return []
    results: list[dict[str, Any]] = []
    for member_path in _member_paths(members, limit=16):
        try:
            payload = _get_json(client, base_url, member_path, requests)
        except httpx.HTTPStatusError as exc:
            if 400 <= exc.response.status_code < 500:
                continue
            raise
        results.append(_network_summary(payload))
    return results


def _member_paths(members: list[Any], *, limit: int) -> list[str]:
    paths: list[str] = []
    for member in members[:limit]:
        member_path = _odata_id(member)
        if member_path:
            paths.append(member_path)
    return _unique_paths(paths)


def _network_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _resource_summary(payload)
    summary["mac_address_present"] = bool(
        payload.get("MACAddress") or payload.get("PermanentMACAddress")
    )
    for key in (
        "SpeedMbps",
        "FullDuplex",
        "LinkStatus",
        "InterfaceEnabled",
        "PhysicalPortNumber",
    ):
        if key in payload:
            summary[key] = payload[key]
    ports = payload.get("NetworkPorts") or payload.get("Ports")
    port_path = _odata_id(ports)
    if port_path:
        summary["ports_path"] = port_path
    return summary


def _storage_discovery(
    client: httpx.Client,
    base_url: str,
    systems: list[dict[str, Any]],
    requests: list[dict[str, Any]],
) -> dict[str, Any]:
    discovery: dict[str, Any] = {
        "status": "not_available",
        "controllers": [],
        "physical_drives": [],
        "logical_drives": [],
        "warnings": [],
    }
    for system in systems:
        system_path = system.get("@odata.id")
        if not isinstance(system_path, str):
            continue
        system_payload = _get_json(client, base_url, system_path, requests)
        for path in _storage_collection_paths(system_payload, system_path):
            _merge_storage_discovery(
                discovery,
                _discover_storage_path(client, base_url, path, requests),
            )

    if discovery["controllers"] or discovery["physical_drives"] or discovery["logical_drives"]:
        discovery["status"] = "available"
    return discovery


def _storage_collection_paths(system_payload: dict[str, Any], system_path: str) -> list[str]:
    paths: list[str] = []
    storage_path = _odata_id(system_payload.get("Storage"))
    if storage_path:
        paths.append(storage_path)
    smart_storage = _odata_id(system_payload.get("SmartStorage"))
    if smart_storage:
        paths.append(smart_storage)
    for suffix in ("Storage", "SmartStorage"):
        paths.append(f"{system_path.rstrip('/')}/{suffix}/")
    return _unique_paths(paths)


def _discover_storage_path(
    client: httpx.Client,
    base_url: str,
    path: str,
    requests: list[dict[str, Any]],
) -> dict[str, Any]:
    discovery = {
        "controllers": [],
        "physical_drives": [],
        "logical_drives": [],
        "warnings": [],
    }
    try:
        payload = _get_json(client, base_url, path, requests)
    except httpx.HTTPStatusError as exc:
        if 400 <= exc.response.status_code < 500:
            discovery["warnings"].append(
                f"Storage path returned HTTP {exc.response.status_code}: {path}"
            )
            return discovery
        raise

    members = payload.get("Members")
    if isinstance(members, list):
        for member_path in _member_paths(members, limit=16):
            _merge_storage_discovery(
                discovery,
                _discover_storage_member(client, base_url, member_path, requests),
            )
        return discovery

    _merge_storage_discovery(
        discovery,
        _discover_storage_member(client, base_url, path, requests, payload=payload),
    )
    return discovery


def _discover_storage_member(
    client: httpx.Client,
    base_url: str,
    path: str,
    requests: list[dict[str, Any]],
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = payload or _get_json(client, base_url, path, requests)
    discovery = {
        "controllers": [],
        "physical_drives": [],
        "logical_drives": [],
        "warnings": [],
    }
    controller_collections = _storage_controller_collection_paths(payload)
    for collection_path in controller_collections:
        for controller in _storage_controller_collection(
            client,
            base_url,
            collection_path,
            requests,
        ):
            _merge_storage_discovery(discovery, controller)

    if _looks_like_storage_controller(payload) or not controller_collections:
        discovery["controllers"].append(_storage_controller_summary(payload))

    links = payload.get("Links") if isinstance(payload.get("Links"), dict) else {}

    for key in ("Drives", "DiskDrives", "PhysicalDrives", "UnconfiguredDrives"):
        drives = payload.get(key) or links.get(key)
        if isinstance(drives, list):
            for drive in drives[:64]:
                drive_path = _odata_id(drive)
                if drive_path:
                    discovery["physical_drives"].append(
                        _drive_summary(_get_json(client, base_url, drive_path, requests))
                    )
                elif isinstance(drive, dict):
                    discovery["physical_drives"].append(_drive_summary(drive))
        else:
            collection_path = _odata_id(drives)
            if collection_path:
                discovery["physical_drives"].extend(
                    _storage_collection_summaries(
                        client,
                        base_url,
                        collection_path,
                        requests,
                        _drive_summary,
                    )
                )

    for key in ("Volumes", "LogicalDrives"):
        collection_path = _odata_id(payload.get(key)) or _odata_id(links.get(key))
        if collection_path:
            discovery["logical_drives"].extend(
                _storage_collection_summaries(
                    client,
                    base_url,
                    collection_path,
                    requests,
                    _logical_drive_summary,
                )
            )
    return discovery


def _storage_controller_collection_paths(payload: dict[str, Any]) -> list[str]:
    paths = []
    links = payload.get("Links") if isinstance(payload.get("Links"), dict) else {}
    for key in ("ArrayControllers", "StorageControllers", "Controllers"):
        path = _odata_id(payload.get(key))
        if not path:
            path = _odata_id(links.get(key))
        if path:
            paths.append(path)
    return _unique_paths(paths)


def _unique_paths(paths: list[str]) -> list[str]:
    return unique_preserving_order(
        (path for path in paths if _path_dedupe_key(path)),
        key=_path_dedupe_key,
    )


def _unique_named_paths(paths: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return unique_preserving_order(
        ((name, path) for name, path in paths if _path_dedupe_key(path)),
        key=lambda item: _path_dedupe_key(item[1]),
    )


def _path_dedupe_key(path: str) -> str:
    text = path.strip()
    if text in {"", "/"}:
        return text
    return text.rstrip("/")


def _storage_controller_collection(
    client: httpx.Client,
    base_url: str,
    collection_path: str,
    requests: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    try:
        collection = _get_json(client, base_url, collection_path, requests)
    except httpx.HTTPStatusError as exc:
        if 400 <= exc.response.status_code < 500:
            return []
        raise
    members = collection.get("Members", [])
    if not isinstance(members, list):
        return []
    controllers = []
    for member_path in _member_paths(members, limit=16):
        controllers.append(_discover_storage_member(client, base_url, member_path, requests))
    return controllers


def _looks_like_storage_controller(payload: dict[str, Any]) -> bool:
    text = " ".join(
        str(payload.get(key) or "")
        for key in ("Id", "Name", "Description", "Model", "@odata.type")
    ).lower()
    if "smartstorage" in text and "arraycontroller" not in text:
        return False
    return any(
        token in text
        for token in (
            "array controller",
            "arraycontroller",
            "smart array",
            "storage controller",
            "raid",
        )
    )


def _storage_collection_summaries(
    client: httpx.Client,
    base_url: str,
    collection_path: str,
    requests: list[dict[str, Any]],
    summarizer: Any,
) -> list[dict[str, Any]]:
    try:
        collection = _get_json(client, base_url, collection_path, requests)
    except httpx.HTTPStatusError as exc:
        if 400 <= exc.response.status_code < 500:
            return []
        raise
    members = collection.get("Members", [])
    if not isinstance(members, list):
        return []
    summaries = []
    for member_path in _member_paths(members, limit=64):
        summaries.append(summarizer(_get_json(client, base_url, member_path, requests)))
    return summaries


def _storage_controller_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _resource_summary(payload)
    for key in (
        "ControllerProtocol",
        "AdapterType",
        "CurrentOperatingMode",
        "BackupPowerSourceStatus",
        "CacheMemorySizeMiB",
        "PartNumber",
        "ControllerPartNumber",
        "SKU",
        "Location",
        "SupportedRAIDTypes",
        "Identifiers",
    ):
        if key in payload:
            summary[key] = payload[key]
    return summary


def _drive_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _resource_summary(payload)
    for key in (
        "Bay",
        "Location",
        "LocationFormat",
        "CapacityBytes",
        "CapacityGB",
        "CapacityMiB",
        "MediaType",
        "InterfaceType",
        "Protocol",
        "FirmwareVersion",
        "Status",
        "BlockSizeBytes",
        "PredictedMediaLifeLeftPercent",
    ):
        if key in payload:
            summary[key] = payload[key]
    summary["serial_number_present"] = bool(payload.get("SerialNumber"))
    if "CapacityBytes" not in summary:
        capacity = payload.get("CapacityMiB")
        if isinstance(capacity, int):
            summary["CapacityBytes"] = capacity * 1024 * 1024
    return summary


def _logical_drive_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _resource_summary(payload)
    for key in (
        "RAIDType",
        "Raid",
        "VolumeType",
        "CapacityBytes",
        "CapacityGB",
        "CapacityMiB",
        "Encrypted",
        "LogicalDriveEncryption",
        "OptimumIOSizeBytes",
        "StripeSizeBytes",
        "Bootable",
        "LogicalDriveName",
        "LogicalDriveNumber",
        "LogicalDriveType",
        "InterfaceType",
        "MediaType",
        "DataDrives",
        "Status",
        "Links",
    ):
        if key in payload:
            summary[key] = payload[key]
    if "RAIDType" not in summary and payload.get("Raid"):
        summary["RAIDType"] = f"RAID{payload['Raid']}"
    if "RAIDType" not in summary and "VolumeType" in summary:
        summary["RAIDType"] = payload["VolumeType"]
    if "CapacityBytes" not in summary:
        capacity = payload.get("CapacityMiB")
        if isinstance(capacity, int):
            summary["CapacityBytes"] = capacity * 1024 * 1024
    return summary


def _merge_storage_discovery(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in ("controllers", "physical_drives", "logical_drives", "warnings"):
        existing = target.setdefault(key, [])
        for item in source.get(key, []):
            if item not in existing:
                existing.append(item)


def _resource_summary(payload: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "@odata.id",
        "Id",
        "Name",
        "Description",
        "Manufacturer",
        "Model",
        "ProductName",
        "FirmwareVersion",
        "BiosVersion",
        "BIOSVersion",
        "ManagerType",
        "PowerState",
        "Status",
    )
    summary = {key: payload[key] for key in keys if key in payload}
    if "SerialNumber" in payload:
        summary["serial_number_present"] = bool(payload["SerialNumber"])
    identity_values = {
        key: payload.get(key)
        for key in (
            "@odata.id",
            "Id",
            "UUID",
            "SerialNumber",
            "Manufacturer",
            "Model",
            "ManagerType",
        )
        if payload.get(key) not in {None, ""}
    }
    if identity_values:
        summary["identity_fingerprint_sha256"] = hashlib.sha256(
            json.dumps(
                identity_values,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
    hardware_identity_values = {
        key: payload.get(key)
        for key in ("UUID", "SerialNumber")
        if payload.get(key) not in {None, ""}
    }
    if hardware_identity_values:
        summary["hardware_identity_fingerprint_sha256"] = hashlib.sha256(
            json.dumps(
                hardware_identity_values,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
    return summary


def _attach_write_target_evidence(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") != "ok":
        return result

    managers = result.get("managers") if isinstance(result.get("managers"), list) else []
    systems = result.get("systems") if isinstance(result.get("systems"), list) else []
    chassis = result.get("chassis") if isinstance(result.get("chassis"), list) else []
    manager_fingerprints = _identity_fingerprints(managers)
    system_fingerprints = _identity_fingerprints(systems)
    chassis_fingerprints = _identity_fingerprints(chassis)
    system_hardware_fingerprints = _hardware_identity_fingerprints(systems)
    identity_verified = bool(
        manager_fingerprints
        and system_fingerprints
        and system_hardware_fingerprints
    )
    identity_payload = {
        "managers": manager_fingerprints,
        "systems": system_fingerprints,
        "system_hardware": system_hardware_fingerprints,
        "chassis": chassis_fingerprints,
    }
    identity_fingerprint = (
        hashlib.sha256(
            json.dumps(
                identity_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        if identity_verified
        else None
    )
    evidence: dict[str, Any] = {
        "source": "live-ilo-redfish-inventory",
        "collected_at": datetime.now(UTC).isoformat(),
        "target_source": result.get("target_source"),
        "target_fingerprint": result.get("target_fingerprint"),
        "identity_fingerprint_sha256": identity_fingerprint,
        "candidate_index": result.get("candidate_index"),
        "target_candidate_count": result.get("target_candidate_count"),
        "exact_target_only": (
            result.get("candidate_index") == 1
            and result.get("target_candidate_count") == 1
        ),
        "authenticated": True,
        "read_only_collection": True,
        "inventory_complete": identity_verified,
        "identity_verified": identity_verified,
    }
    evidence["evidence_digest_sha256"] = hashlib.sha256(
        json.dumps(
            evidence,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    return {**result, "write_target_evidence": evidence}


def _identity_fingerprints(items: list[Any]) -> list[str]:
    return sorted(
        {
            fingerprint
            for item in items
            if isinstance(item, dict)
            and isinstance(
                fingerprint := item.get("identity_fingerprint_sha256"),
                str,
            )
            and re.fullmatch(r"[0-9a-f]{64}", fingerprint)
        }
    )


def _hardware_identity_fingerprints(items: list[Any]) -> list[str]:
    return sorted(
        {
            fingerprint
            for item in items
            if isinstance(item, dict)
            and isinstance(
                fingerprint := item.get("hardware_identity_fingerprint_sha256"),
                str,
            )
            and re.fullmatch(r"[0-9a-f]{64}", fingerprint)
        }
    )


def _strip_links(summary: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in summary.items() if key != "_links"}


def _probe_requirement_reason(provider_mode: str) -> str:
    if provider_mode == LOCAL_READONLY_MODE:
        return (
            "Requires complete local config, LAB_CLOSED_LOOP_ACK=YES, "
            "LAB_READONLY_ACK=YES, and PROVIDER_MODE=local-readonly."
        )
    if provider_mode == LOCAL_LAB_MODE:
        return (
            "Requires complete local config, PROVIDER_MODE=local-lab-readwrite, "
            "LAB_ENVIRONMENT=isolated-real-lab, LAB_ACKNOWLEDGE_REAL_HARDWARE=true, "
            "LAB_ACKNOWLEDGE_DEVICE_RECONFIGURATION=true, "
            "LAB_ACKNOWLEDGE_DATA_LOSS_RISK=true, and LAB_ACKNOWLEDGE_LAB_ONLY=true."
        )
    return "Requires PROVIDER_MODE=local-readonly or PROVIDER_MODE=local-lab-readwrite."


def _not_attempted_actions() -> list[str]:
    return [
        "firmware update",
        "power on/off/reset",
        "virtual media mount",
        "boot order change",
        "BIOS change",
        "user/password change",
        "iLO network change",
        "factory reset",
        "device POST/PATCH/PUT/DELETE",
    ]


def _local_state_write_status(policy: Any, provider_mode: str) -> str:
    if provider_mode != LOCAL_LAB_MODE:
        return "allowed"
    return (
        "allowed"
        if not policy.action_blockers(
            "ilo-redfish.record-readonly-inventory",
            ActionCategory.APP_STATE_WRITE,
        )
        else "blocked"
    )


def _dangerous_actions(policy: Any) -> list[ProviderAction]:
    return [
        ProviderAction(
            id="ilo-power-action",
            label="Power Action",
            enabled=False,
            read_only=False,
            reason=policy.dangerous_action_reason("ilo-power-action"),
        ),
        ProviderAction(
            id="ilo-virtual-media",
            label="Virtual Media",
            enabled=False,
            read_only=False,
            reason=policy.dangerous_action_reason("ilo-virtual-media"),
        ),
        ProviderAction(
            id="ilo-firmware-update",
            label="Firmware Update",
            enabled=False,
            read_only=False,
            reason=policy.dangerous_action_reason("ilo-firmware-update"),
        ),
        ProviderAction(
            id="ilo-user-change",
            label="User Changes",
            enabled=False,
            read_only=False,
            reason=policy.dangerous_action_reason("ilo-user-change"),
        ),
        ProviderAction(
            id="ilo-boot-order-change",
            label="Boot Order Change",
            enabled=False,
            read_only=False,
            reason=policy.dangerous_action_reason("ilo-boot-order-change"),
        ),
        ProviderAction(
            id="ilo-bios-change",
            label="BIOS Change",
            enabled=False,
            read_only=False,
            reason=policy.dangerous_action_reason("ilo-bios-change"),
        ),
        ProviderAction(
            id="ilo-network-change",
            label="iLO Network Change",
            enabled=False,
            read_only=False,
            reason=policy.dangerous_action_reason("ilo-network-change"),
        ),
        ProviderAction(
            id="ilo-factory-reset",
            label="Factory Reset",
            enabled=False,
            read_only=False,
            reason=policy.dangerous_action_reason("ilo-factory-reset"),
        ),
    ]
