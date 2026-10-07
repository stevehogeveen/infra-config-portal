"""Project normalized assessment evidence into Claude's simple review contract.

Internal boundary only: no route accepts this evidence from a browser. Vendor report
parsers and the durable execution/approval service must supply it independently.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import Field
from app.services.blocker_guidance import describe_blockers

from app.services.spp_update_contract import (
    Contract,
    Effects,
    Excluded,
    Identifier,
    Minutes,
    Package,
    Restart,
    Server,
    Text,
    Update,
    UpdatePlan,
)


class AssessedUpdate(Contract):
    component_id: Identifier
    component: Text
    from_version: Text
    to: Text
    package_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    applicable: bool
    signature_verified: bool
    dependencies_satisfied: bool
    adapter_supported: bool
    restarts: Restart | None
    est_minutes: Minutes | None = None
    exclusion_reason: Text | None = None


class Assessment(Contract):
    profile_id: Identifier
    device_id: Identifier
    source: Literal["sum-assessment"]
    checked_at: datetime
    target_identity_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    package_identity_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    report_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    server: Server
    package: Package
    execution_mode: Literal["online", "offline"]
    platform_supported: bool
    runner_supported: bool
    power_on_required: bool
    updates: list[AssessedUpdate] = Field(max_length=256)
    blockers: list[Text] = Field(default_factory=list, max_length=128)
    warnings: list[Text] = Field(default_factory=list, max_length=128)


def assessment_digest(assessment: Assessment) -> str:
    return hashlib.sha256(
        json.dumps(
            assessment.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def project_plan(assessment: Assessment, *, now: datetime | None = None) -> UpdatePlan:
    """No approval token is minted by projection; the durable issuer owns authorization."""
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("Assessment clock must include a timezone.")
    blockers = list(assessment.blockers)
    if (
        assessment.checked_at.tzinfo is None
        or not now - timedelta(minutes=5) <= assessment.checked_at <= now
    ):
        blockers.append("Read this server again before approving its updates.")
    if not assessment.platform_supported:
        blockers.append("The selected SPP does not establish support for this server.")
    if not assessment.runner_supported:
        blockers.append("The firmware assessment runner is not ready for this server.")
    if assessment.server.manager_generation == 7 and assessment.execution_mode == "offline":
        blockers.append("This iLO 7 server requires an online update method.")
    updates = []
    excluded = []
    prior_versions = {}
    identities = set()
    for item in assessment.updates:
        identity = (item.component_id, item.from_version, item.to)
        if identity in identities:
            blockers.append(f"The assessment repeats an update for {item.component}.")
            continue
        identities.add(identity)
        if not item.applicable or not item.adapter_supported:
            excluded.append(
                Excluded(
                    component=item.component,
                    reason=item.exclusion_reason
                    or "No supported installation method was established for this component.",
                )
            )
            continue
        if not item.signature_verified:
            blockers.append(f"The {item.component} update has not been authenticated.")
        if not item.dependencies_satisfied:
            blockers.append(f"The {item.component} prerequisites are unresolved.")
        if item.restarts is None:
            blockers.append(f"The restart requirements for {item.component} are unknown.")
            continue
        if (
            item.component_id in prior_versions
            and item.from_version != prior_versions[item.component_id]
        ):
            blockers.append(f"The update sequence for {item.component} is inconsistent.")
        if item.from_version == item.to:
            blockers.append(f"The {item.component} update would reinstall the current version.")
        prior_versions[item.component_id] = item.to
        step_id = hashlib.sha256(
            json.dumps(
                [item.component_id, item.from_version, item.to, item.package_sha256]
            ).encode()
        ).hexdigest()[:32]
        updates.append(
            Update(
                step_id=step_id,
                component=item.component,
                from_version=item.from_version,
                to=item.to,
                order=len(updates) + 1,
                restarts=item.restarts,
                est_minutes=item.est_minutes,
            )
        )
    if not updates:
        blockers.append("No supported firmware updates are ready to install.")
    total = (
        sum(u.est_minutes for u in updates)
        if updates and all(u.est_minutes is not None for u in updates)
        else None
    )
    if total is not None and total > 10080:
        total = None
    return UpdatePlan(
        plan_id=assessment_digest(assessment),
        profile_id=assessment.profile_id,
        device_id=assessment.device_id,
        review_token=None,
        expires_at=now + timedelta(minutes=5),
        server=assessment.server,
        package=assessment.package,
        updates=updates,
        effects=Effects(
            host_restarts=sum(u.restarts == "host" for u in updates),
            ilo_restarts=sum(u.restarts == "ilo" for u in updates),
            est_total_minutes=total,
            power_on_required=assessment.power_on_required,
        ),
        not_included=excluded,
        blockers=list(dict.fromkeys(blockers)),
        blocker_details=describe_blockers(list(dict.fromkeys(blockers))),
        warnings=assessment.warnings,
        can_apply=False,
        confirmation_phrase=None,
        details={
            "source": assessment.source,
            "assessment_at": assessment.checked_at.isoformat(),
            "report_sha256": assessment.report_sha256,
            "package_identity_sha256": assessment.package_identity_sha256,
            "target_identity_sha256": assessment.target_identity_sha256,
            "execution_mode": assessment.execution_mode,
            "approval_state": "not_issued",
        },
    )
