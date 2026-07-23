from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from ipaddress import ip_address
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.providers.ilo_redfish import (
    PROVIDER_ID,
    IloRedfishAdapter,
    IloRedfishConfig,
    ilo_target_fingerprint,
)
from app.providers.probe_cache import get_probe_result
from app.services.list_utils import unique_preserving_order

WRITE_TARGET_MAX_AGE = timedelta(minutes=5)
MAX_FUTURE_CLOCK_SKEW = timedelta(seconds=30)
WRITE_TARGET_HOST_ENV = "ILO_WRITE_TARGET_HOST"
WRITE_EVIDENCE_SOURCE = "live-ilo-redfish-inventory"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class IloWriteTargetContext(BaseModel):
    """Immutable server-built proof that one exact iLO access target was reviewed."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    current_access_host: str = Field(min_length=1, max_length=80)
    target_fingerprint: str = Field(pattern=r"^[0-9a-f]{16}$")
    identity_fingerprint_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_digest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    evidence_checked_at: datetime
    target_source: str = Field(min_length=1, max_length=120)

    @field_validator("current_access_host")
    @classmethod
    def require_explicit_ip(cls, value: str) -> str:
        try:
            return str(ip_address(value))
        except ValueError as exc:
            raise ValueError(
                "current_access_host must be one explicit IPv4 or IPv6 address"
            ) from exc


def requested_ilo_write_host(explicit_host: str | None = None) -> str | None:
    value = explicit_host if explicit_host is not None else os.getenv(WRITE_TARGET_HOST_ENV)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def resolve_ilo_write_target_context(
    ilo_host: str | None,
    *,
    now: datetime | None = None,
) -> tuple[IloWriteTargetContext | None, list[str]]:
    """Resolve only fresh, exact-target, authenticated cache evidence.

    No network operation is performed here. Evidence from a fallback candidate is
    deliberately unusable for a mutation.
    """

    blockers: list[str] = []
    normalized_host = _explicit_ip(ilo_host)
    if normalized_host is None:
        return None, [
            "An explicit current-access ilo_host IP is required for every iLO-backed write."
        ]

    result, checked_at_value = get_probe_result(PROVIDER_ID)
    if not isinstance(result, dict):
        return None, [
            "Fresh exact-target iLO Inventory Read evidence is required before any iLO-backed write."
        ]

    wrapper_checked_at = _aware_datetime(checked_at_value or result.get("checked_at"))
    current_time = _aware_datetime(now or datetime.now(UTC))
    evidence = (
        result.get("write_target_evidence")
        if isinstance(result.get("write_target_evidence"), dict)
        else {}
    )
    checked_at = _aware_datetime(evidence.get("collected_at"))
    if checked_at is None:
        blockers.append("iLO write-target evidence has no valid collected_at timestamp.")
    elif current_time is not None:
        if checked_at > current_time + MAX_FUTURE_CLOCK_SKEW:
            blockers.append("iLO write-target evidence timestamp is in the future.")
        elif current_time - checked_at > WRITE_TARGET_MAX_AGE:
            blockers.append("iLO write-target evidence is stale; run the exact iLO IP check again.")

    if result.get("status") != "ok":
        blockers.append("The latest exact-target iLO Inventory Read did not complete successfully.")

    candidate_index = _integer(result.get("candidate_index"))
    candidate_count = _integer(result.get("target_candidate_count"))
    if candidate_index != 1 or candidate_count != 1:
        blockers.append(
            "Fallback or multi-candidate iLO evidence cannot authorize a write; rerun an exact-target-only check."
        )

    expected_target_fingerprint = ilo_target_fingerprint(normalized_host)
    result_target_fingerprint = _string(result.get("target_fingerprint"))
    if (
        not expected_target_fingerprint
        or result_target_fingerprint != expected_target_fingerprint
    ):
        blockers.append(
            "Latest iLO evidence is not bound to the requested current-access host."
        )

    if wrapper_checked_at is None:
        blockers.append("iLO write-target cache wrapper has no valid checked_at timestamp.")
    elif checked_at is not None and wrapper_checked_at < checked_at:
        blockers.append("iLO write-target cache wrapper predates the nested inventory proof.")
    evidence_target_fingerprint = _string(evidence.get("target_fingerprint"))
    identity_fingerprint = _string(evidence.get("identity_fingerprint_sha256"))
    evidence_digest = _string(evidence.get("evidence_digest_sha256"))
    target_source = _string(evidence.get("target_source")) or _string(
        result.get("target_source")
    )

    if evidence.get("source") != WRITE_EVIDENCE_SOURCE:
        blockers.append("Latest iLO evidence is not a live read-only inventory proof.")
    if evidence.get("exact_target_only") is not True:
        blockers.append("Latest iLO evidence was not collected in exact-target-only mode.")
    if evidence.get("authenticated") is not True:
        blockers.append("Latest iLO evidence does not prove authenticated Redfish access.")
    if evidence.get("read_only_collection") is not True:
        blockers.append("Latest iLO evidence does not prove read-only collection.")
    if evidence.get("inventory_complete") is not True:
        blockers.append("Latest iLO evidence does not contain complete manager and system identity.")
    if evidence.get("identity_verified") is not True:
        blockers.append("Latest iLO evidence does not verify the target hardware identity.")
    if evidence_target_fingerprint != expected_target_fingerprint:
        blockers.append("iLO evidence target fingerprint does not match ilo_host.")
    if not identity_fingerprint or not SHA256_RE.fullmatch(identity_fingerprint):
        blockers.append("iLO evidence has no valid hardware identity fingerprint.")
    if not evidence_digest or not SHA256_RE.fullmatch(evidence_digest):
        blockers.append("iLO evidence has no valid evidence digest.")
    elif evidence_digest != ilo_write_evidence_digest(evidence):
        blockers.append("iLO evidence digest does not match the cached read-only proof.")
    if not target_source:
        blockers.append("iLO evidence does not identify its exact target source.")

    if blockers or checked_at is None or not expected_target_fingerprint:
        return None, unique_preserving_order(blockers)

    try:
        context = IloWriteTargetContext(
            current_access_host=normalized_host,
            target_fingerprint=expected_target_fingerprint,
            identity_fingerprint_sha256=identity_fingerprint or "",
            evidence_digest_sha256=evidence_digest or "",
            evidence_checked_at=checked_at,
            target_source=target_source or "",
        )
    except ValidationError as exc:
        return None, [f"iLO write-target evidence is malformed: {exc.__class__.__name__}."]
    return context, []


def exact_ilo_write_config(context: IloWriteTargetContext) -> IloRedfishConfig:
    """Pin credentials/TLS settings to the reviewed host and remove all fallbacks."""

    configured = IloRedfishConfig.from_settings()
    return replace(
        configured,
        host=context.current_access_host,
        host_source="exact_write_target_context",
        fallback_hosts=(),
        fallback_host_sources=(),
    )


def refresh_ilo_write_target_context(
    context: IloWriteTargetContext,
) -> tuple[IloWriteTargetContext | None, IloRedfishConfig | None, list[str]]:
    """Collect a new exact-target inventory proof immediately before a mutation."""

    config = exact_ilo_write_config(context)
    try:
        probe = IloRedfishAdapter(
            provider_mode="local-lab-readwrite",
            config=config,
        ).probe()
    except Exception as exc:
        return None, None, [
            f"Immediate exact-target iLO identity preflight failed: {type(exc).__name__}."
        ]
    if not isinstance(probe, dict) or probe.get("status") != "ok":
        return None, None, [
            "Immediate exact-target iLO identity preflight did not complete successfully."
        ]

    refreshed, blockers = resolve_ilo_write_target_context(
        context.current_access_host,
    )
    if blockers or refreshed is None:
        return None, None, unique_preserving_order(blockers)
    if refreshed.target_fingerprint != context.target_fingerprint:
        blockers.append("Immediate iLO preflight target fingerprint changed.")
    if (
        refreshed.identity_fingerprint_sha256
        != context.identity_fingerprint_sha256
    ):
        blockers.append(
            "Immediate iLO preflight hardware identity does not match the reviewed target."
        )
    if blockers:
        return None, None, unique_preserving_order(blockers)
    return refreshed, exact_ilo_write_config(refreshed), []


def ilo_write_evidence_digest(evidence: dict[str, Any]) -> str:
    payload = {
        key: value
        for key, value in evidence.items()
        if key != "evidence_digest_sha256"
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def compact_ilo_write_target(
    context: IloWriteTargetContext | None,
) -> dict[str, Any] | None:
    if context is None:
        return None
    return context.model_dump(mode="json")


def _explicit_ip(value: Any) -> str | None:
    text = _string(value)
    if not text:
        return None
    try:
        return str(ip_address(text))
    except ValueError:
        return None


def _aware_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
