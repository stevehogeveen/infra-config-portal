from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from app.providers.ilo_redfish import PROVIDER_ID as ILO_PROVIDER_ID
from app.providers.probe_cache import get_probe_result
from app.schemas import (
    IloUpgradeReadinessRead,
    MediaInventoryItemRead,
    UpgradeCandidateRead,
    UpgradeDecisionRead,
    UpgradeRuleRead,
    UpgradeSubjectRead,
)
from app.services.media_inventory import get_media_inventory

COMPATIBLE_CONFIDENCE = {"exact", "likely", "weak"}
NO_KNOWN_ILO_RULES: tuple[UpgradeRuleRead, ...] = ()


def get_ilo_upgrade_readiness() -> IloUpgradeReadinessRead:
    probe_result, _checked_at = get_probe_result(ILO_PROVIDER_ID)
    subject = ilo_subject_from_probe(probe_result)
    media_inventory = get_media_inventory()
    candidates = upgrade_candidates_from_media(subject, media_inventory.items)
    decision = decide_upgrade(subject, candidates, NO_KNOWN_ILO_RULES)

    if media_inventory.warnings:
        decision = decision.model_copy(
            update={
                "removable_warnings": _unique(
                    [*decision.removable_warnings, *media_inventory.warnings]
                )
            }
        )

    return IloUpgradeReadinessRead(
        provider_id=ILO_PROVIDER_ID,
        subject=subject,
        candidates=candidates,
        decision=decision,
        blockers=decision.blockers,
        warnings=decision.warnings,
        removable_warnings=decision.removable_warnings,
        upgrade_chain=decision.candidate_chain,
        apply_enabled=False,
    )


def ilo_subject_from_probe(probe_result: dict[str, Any] | None) -> UpgradeSubjectRead:
    if not probe_result:
        return UpgradeSubjectRead(
            provider_type="ilo",
            product="hpe-ilo",
            discovery_confidence="unknown",
        )

    managers = _records(probe_result.get("managers"))
    systems = _records(probe_result.get("systems"))
    chassis = _records(probe_result.get("chassis"))
    firmware = _records(probe_result.get("firmware"))
    legacy_identity = _legacy_identity(probe_result)

    current_version = _first_string(managers, "FirmwareVersion") or _first_ilo_firmware_version(
        firmware
    ) or _string_value(legacy_identity.get("current_firmware"))
    generation = _first_generation([*managers, *firmware]) or _first_generation(
        [*systems, *chassis]
    ) or _string_value(legacy_identity.get("ilo_generation"))
    model = (
        _first_string(systems, "Model")
        or _first_string(chassis, "Model")
        or _string_value(legacy_identity.get("model"))
    )
    serial = _first_string(systems, "SerialNumber") or _first_string(
        chassis, "SerialNumber"
    )
    if not serial and legacy_identity.get("serial_present") is True:
        serial = "SERIAL-REDACTED"

    discovery_confidence = "unknown"
    if current_version and generation:
        discovery_confidence = "exact"
    elif current_version or generation or model:
        discovery_confidence = "weak"

    return UpgradeSubjectRead(
        provider_type="ilo",
        product="hpe-ilo",
        generation=generation,
        model=model,
        serial=serial,
        current_version=current_version,
        discovery_confidence=discovery_confidence,
    )


def upgrade_candidates_from_media(
    subject: UpgradeSubjectRead,
    media_items: Iterable[MediaInventoryItemRead],
) -> list[UpgradeCandidateRead]:
    candidates: list[UpgradeCandidateRead] = []
    for item in media_items:
        if item.category != "firmware":
            continue
        candidate = UpgradeCandidateRead(
            id=item.placeholder_name,
            category=item.category,
            product_hint=_first(item.product_hints),
            generation_hint=_first(item.generation_hints),
            version=item.version_hint,
            source=item.source,
            redacted_label=item.placeholder_name,
            match_confidence="unknown",
        )
        candidates.append(match_candidate_to_subject(subject, candidate))
    return candidates


def _legacy_identity(probe_result: dict[str, Any]) -> dict[str, Any]:
    identity = probe_result.get("legacy_identity")
    if isinstance(identity, dict):
        return identity
    detection = probe_result.get("endpoint_detection")
    if isinstance(detection, dict) and isinstance(detection.get("legacy_identity"), dict):
        return detection["legacy_identity"]
    return {}


def _string_value(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def match_candidate_to_subject(
    subject: UpgradeSubjectRead,
    candidate: UpgradeCandidateRead,
) -> UpgradeCandidateRead:
    warnings = list(candidate.warnings)

    if candidate.category != "firmware":
        return candidate.model_copy(
            update={
                "match_confidence": "unknown",
                "warnings": _unique([*warnings, "Candidate media is not categorized as firmware."]),
            }
        )

    if _generation_conflicts(subject.generation, candidate.generation_hint):
        return candidate.model_copy(
            update={
                "match_confidence": "unknown",
                "warnings": _unique(
                    [
                        *warnings,
                        (
                            f"Candidate generation {candidate.generation_hint} does not match "
                            f"discovered generation {subject.generation}."
                        ),
                    ]
                ),
            }
        )

    product_match = bool(subject.product and candidate.product_hint == subject.product)
    generation_match = bool(
        subject.generation
        and candidate.generation_hint
        and _normalize_generation(subject.generation)
        == _normalize_generation(candidate.generation_hint)
    )

    if product_match and generation_match and candidate.version:
        confidence = "exact"
    elif product_match and (generation_match or not candidate.generation_hint):
        confidence = "likely"
    elif generation_match:
        confidence = "likely"
        warnings.append("Candidate generation matched, but product hint is incomplete.")
    else:
        confidence = "weak"
        warnings.append("Candidate matched by firmware category or redacted filename hints only.")

    if not candidate.version:
        warnings.append("Candidate version could not be parsed from redacted media metadata.")
    if candidate.source == "sample":
        warnings.append("Sample media metadata is not a real firmware catalog.")

    return candidate.model_copy(
        update={"match_confidence": confidence, "warnings": _unique(warnings)}
    )


def decide_upgrade(
    subject: UpgradeSubjectRead,
    candidates: Iterable[UpgradeCandidateRead],
    rules: Iterable[UpgradeRuleRead] = (),
) -> UpgradeDecisionRead:
    matched_candidates = [match_candidate_to_subject(subject, candidate) for candidate in candidates]
    removable_warnings = _candidate_warnings(matched_candidates)
    blockers: list[str] = []
    warnings: list[str] = []

    if not subject.current_version:
        blockers.append("Current firmware version is unknown.")
    if not subject.generation:
        blockers.append("Device generation is unknown.")
    if blockers:
        return _decision(
            "discovery_incomplete",
            subject,
            blockers=blockers,
            removable_warnings=removable_warnings,
            next_safe_action=(
                "Run explicit read-only iLO discovery and confirm device identity before "
                "planning firmware work."
            ),
        )

    firmware_candidates = [candidate for candidate in matched_candidates if candidate.category == "firmware"]
    if not firmware_candidates:
        return _decision(
            "no_candidate_found",
            subject,
            blockers=["No firmware candidate media was found in the metadata inventory."],
            next_safe_action=(
                "Add matching firmware media or a catalog entry to the local metadata inventory."
            ),
        )

    incompatible_candidates = [
        candidate for candidate in firmware_candidates if _candidate_incompatible(subject, candidate)
    ]
    compatible_candidates = [
        candidate
        for candidate in firmware_candidates
        if candidate.match_confidence in COMPATIBLE_CONFIDENCE
        and not _candidate_incompatible(subject, candidate)
    ]
    if not compatible_candidates and incompatible_candidates:
        return _decision(
            "blocked_incompatible",
            subject,
            blockers=["Firmware candidates do not match the discovered device generation."],
            removable_warnings=removable_warnings,
            next_safe_action=(
                "Add candidate media with product and generation hints that match discovery."
            ),
        )
    if not compatible_candidates:
        return _decision(
            "no_candidate_found",
            subject,
            blockers=["No compatible firmware candidate was found."],
            removable_warnings=removable_warnings,
            next_safe_action=(
                "Add matching firmware media or a sourced catalog entry before planning."
            ),
        )

    current_key = _version_key(subject.current_version)
    if current_key is None:
        return _decision(
            "manual_review_required",
            subject,
            blockers=["Current firmware version could not be compared automatically."],
            removable_warnings=_unique(
                [*removable_warnings, "Current version parsing was heuristic or incomplete."]
            ),
            next_safe_action=(
                "Review discovered firmware version and candidate versions manually."
            ),
        )

    versioned_candidates = [
        candidate for candidate in compatible_candidates if _version_key(candidate.version) is not None
    ]
    if not versioned_candidates:
        return _decision(
            "manual_review_required",
            subject,
            blockers=["Candidate firmware versions could not be compared automatically."],
            removable_warnings=removable_warnings,
            next_safe_action="Add catalog metadata with explicit target versions.",
        )

    newest_candidate = max(
        versioned_candidates,
        key=lambda candidate: _version_key(candidate.version) or (),
    )
    newer_candidates = [
        candidate
        for candidate in versioned_candidates
        if _compare_versions(candidate.version, subject.current_version) > 0
    ]
    if not newer_candidates:
        return _decision(
            "current",
            subject,
            recommended_target=newest_candidate.version,
            candidate_chain=[newest_candidate],
            removable_warnings=removable_warnings,
            next_safe_action="No firmware action is planned; current discovered firmware is up to date.",
        )

    target = max(newer_candidates, key=lambda candidate: _version_key(candidate.version) or ())
    if target.match_confidence == "weak":
        return _decision(
            "manual_review_required",
            subject,
            recommended_target=target.version,
            candidate_chain=[target],
            blockers=["Candidate identity is too weak for an automatic upgrade path decision."],
            removable_warnings=removable_warnings,
            next_safe_action=(
                "Confirm candidate identity with a sourced catalog before planning firmware work."
            ),
        )

    matching_rules = [
        rule for rule in rules if _rule_matches(rule, subject, target)
    ]
    if not matching_rules:
        return _decision(
            "blocked_unknown_path",
            subject,
            recommended_target=target.version,
            candidate_chain=[target],
            blockers=[
                "No sourced upgrade rule confirms this current-to-target firmware path."
            ],
            removable_warnings=removable_warnings,
            next_safe_action=(
                "Add sourced upgrade rules or release-note catalog data before planning."
            ),
        )

    rule = matching_rules[0]
    if rule.blocked_reason:
        return _decision(
            "blocked_incompatible",
            subject,
            recommended_target=target.version,
            candidate_chain=[target],
            blockers=[rule.blocked_reason],
            removable_warnings=removable_warnings,
            next_safe_action="Select a different target or add a corrected sourced rule.",
        )

    missing_intermediates = [
        version
        for version in rule.requires_intermediate
        if _candidate_for_version(versioned_candidates, version) is None
    ]
    if missing_intermediates:
        return _decision(
            "blocked_unknown_path",
            subject,
            recommended_target=target.version,
            required_intermediate_versions=rule.requires_intermediate,
            candidate_chain=[target],
            blockers=[
                "Upgrade requires intermediate firmware media that is missing: "
                + ", ".join(missing_intermediates)
                + "."
            ],
            removable_warnings=removable_warnings,
            next_safe_action="Add the required intermediate media before planning this path.",
        )

    candidate_chain = [
        candidate
        for version in rule.requires_intermediate
        if (candidate := _candidate_for_version(versioned_candidates, version)) is not None
    ]
    candidate_chain.append(target)
    if rule.warning:
        warnings.append(rule.warning)

    return _decision(
        "upgrade_available",
        subject,
        recommended_target=target.version,
        required_intermediate_versions=rule.requires_intermediate,
        candidate_chain=candidate_chain,
        warnings=warnings,
        removable_warnings=removable_warnings,
        next_safe_action=(
            "Review the sourced upgrade chain. Apply remains disabled in this planning preview."
        ),
    )


def _decision(
    status: str,
    subject: UpgradeSubjectRead,
    *,
    recommended_target: str | None = None,
    required_intermediate_versions: list[str] | None = None,
    candidate_chain: list[UpgradeCandidateRead] | None = None,
    blockers: list[str] | None = None,
    warnings: list[str] | None = None,
    removable_warnings: list[str] | None = None,
    next_safe_action: str,
) -> UpgradeDecisionRead:
    return UpgradeDecisionRead(
        status=status,
        current_version=subject.current_version,
        recommended_target=recommended_target,
        required_intermediate_versions=required_intermediate_versions or [],
        candidate_chain=candidate_chain or [],
        blockers=blockers or [],
        warnings=warnings or [],
        removable_warnings=removable_warnings or [],
        next_safe_action=next_safe_action,
        apply_enabled=False,
    )


def _rule_matches(
    rule: UpgradeRuleRead,
    subject: UpgradeSubjectRead,
    target: UpgradeCandidateRead,
) -> bool:
    if rule.product and rule.product != subject.product:
        return False
    if rule.generation and _normalize_generation(rule.generation) != _normalize_generation(
        subject.generation
    ):
        return False
    if not _constraint_matches(subject.current_version, rule.from_constraint):
        return False
    return _constraint_matches(target.version, rule.to_constraint)


def _constraint_matches(version: str | None, constraint: str | None) -> bool:
    if not constraint or constraint == "*":
        return True
    if not version:
        return False
    for part in [item.strip() for item in constraint.split(",") if item.strip()]:
        match = re.match(r"(>=|<=|>|<|==|=)?\s*(.+)", part)
        if not match:
            return False
        operator = match.group(1) or "=="
        expected = match.group(2)
        comparison = _compare_versions(version, expected)
        if operator in {"==", "="} and comparison != 0:
            return False
        if operator == ">" and comparison <= 0:
            return False
        if operator == ">=" and comparison < 0:
            return False
        if operator == "<" and comparison >= 0:
            return False
        if operator == "<=" and comparison > 0:
            return False
    return True


def _candidate_for_version(
    candidates: Iterable[UpgradeCandidateRead],
    version: str,
) -> UpgradeCandidateRead | None:
    return next((candidate for candidate in candidates if _compare_versions(candidate.version, version) == 0), None)


def _compare_versions(left: str | None, right: str | None) -> int:
    left_key = _version_key(left)
    right_key = _version_key(right)
    if left_key is None or right_key is None:
        return -1 if left_key is None and right_key is not None else int(right_key is None)
    width = max(len(left_key), len(right_key))
    padded_left = (*left_key, *([0] * (width - len(left_key))))
    padded_right = (*right_key, *([0] * (width - len(right_key))))
    if padded_left == padded_right:
        return 0
    return 1 if padded_left > padded_right else -1


def _version_key(version: str | None) -> tuple[int, ...] | None:
    if not version:
        return None
    parts = re.findall(r"\d+", version)
    if not parts:
        return None
    return tuple(int(part) for part in parts)


def _candidate_incompatible(
    subject: UpgradeSubjectRead,
    candidate: UpgradeCandidateRead,
) -> bool:
    return _generation_conflicts(subject.generation, candidate.generation_hint)


def _generation_conflicts(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    normalized_left = _normalize_generation(left)
    normalized_right = _normalize_generation(right)
    if normalized_left == normalized_right:
        return False
    return _generation_namespace(normalized_left) == _generation_namespace(normalized_right)


def _normalize_generation(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower()) if value else ""


def _generation_namespace(value: str) -> str:
    if value.startswith("ilo"):
        return "ilo"
    if value.startswith("gen"):
        return "gen"
    return value


def _candidate_warnings(candidates: Iterable[UpgradeCandidateRead]) -> list[str]:
    warnings: list[str] = []
    for candidate in candidates:
        warnings.extend(candidate.warnings)
    return _unique(warnings)


def _first(values: Iterable[str]) -> str | None:
    return next((value for value in values if value), None)


def _records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _first_string(records: Iterable[dict[str, Any]], *keys: str) -> str | None:
    for record in records:
        for key in keys:
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _first_ilo_firmware_version(records: Iterable[dict[str, Any]]) -> str | None:
    for record in records:
        label = " ".join(
            value
            for key in ("Name", "Id", "Description", "Model")
            if isinstance((value := record.get(key)), str)
        )
        if re.search(r"(?:^|[^a-z0-9])ilo(?:[^a-z0-9]|$)", label.lower()):
            version = record.get("FirmwareVersion")
            if isinstance(version, str) and version.strip():
                return version.strip()
    return None


def _first_generation(records: Iterable[dict[str, Any]]) -> str | None:
    for record in records:
        label = " ".join(
            value
            for key in ("Name", "Id", "Description", "Model")
            if isinstance((value := record.get(key)), str)
        )
        generation = _generation_from_label(label)
        if generation:
            return generation
    return None


def _generation_from_label(label: str) -> str | None:
    normalized = label.lower()
    ilo_match = re.search(r"(?:^|[^a-z0-9])ilo[\s._-]?([456])(?:[^a-z0-9]|$)", normalized)
    if ilo_match:
        return f"ilo{ilo_match.group(1)}"
    gen_match = re.search(r"(?:^|[^a-z0-9])gen[\s._-]?(\d{1,2})(?:[^a-z0-9]|$)", normalized)
    if gen_match:
        return f"gen{gen_match.group(1)}"
    return None


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            unique_values.append(value)
    return unique_values
