from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.services.spp_update_contract import UpdatePlan
from app.services.spp_update_plan import Assessment, AssessedUpdate, assessment_digest, project_plan


@pytest.fixture
def assessment():
    return Assessment(
        profile_id="kit",
        device_id="srv",
        source="sum-assessment",
        checked_at=datetime.now(UTC),
        target_identity_sha256="a" * 64,
        package_identity_sha256="b" * 64,
        report_sha256="c" * 64,
        server={"name": "Fixture", "model": "Detected model", "manager_generation": 5},
        package={"file": "fixture.iso", "release": "fixture-release"},
        execution_mode="online",
        platform_supported=True,
        runner_supported=True,
        power_on_required=True,
        updates=[
            AssessedUpdate(
                component_id="ilo",
                component="iLO",
                from_version="1.37",
                to="1.48",
                package_sha256="d" * 64,
                applicable=True,
                signature_verified=True,
                dependencies_satisfied=True,
                adapter_supported=True,
                restarts="ilo",
                est_minutes=5,
            )
        ],
    )


def test_projection_is_not_permission(assessment):
    plan = project_plan(assessment)
    assert plan.blockers == []
    assert plan.can_apply is False
    assert plan.review_token is plan.confirmation_phrase is None
    assert plan.effects.ilo_restarts == 1
    assert plan.effects.host_restarts == 0
    assert plan.effects.est_total_minutes == 5
    assert "1.48" == plan.updates[0].to


@pytest.mark.parametrize(
    "generation,mode,blocked",
    [(5, "online", False), (6, "online", False), (7, "online", False), (7, "offline", True)],
)
def test_detected_generation_selects_execution_policy(assessment, generation, mode, blocked):
    assessment.server.manager_generation = generation
    assessment.execution_mode = mode
    assert bool(project_plan(assessment).blockers) is blocked


@pytest.mark.parametrize(
    "field,value",
    [
        ("platform_supported", False),
        ("runner_supported", False),
        ("checked_at", datetime(2000, 1, 1, tzinfo=UTC)),
        ("checked_at", datetime(2000, 1, 1)),
        ("checked_at", datetime.now(UTC) + timedelta(hours=1)),
    ],
)
def test_missing_or_stale_evidence_blocks_plan(assessment, field, value):
    setattr(assessment, field, value)
    plan = project_plan(assessment)
    assert plan.blockers
    assert [d.text for d in plan.blocker_details] == plan.blockers


@pytest.mark.parametrize(
    "field,value",
    [("signature_verified", False), ("dependencies_satisfied", False), ("restarts", None)],
)
def test_component_proof_required(assessment, field, value):
    setattr(assessment.updates[0], field, value)
    assert project_plan(assessment).blockers


def test_no_fabricated_estimates(assessment):
    assessment.updates[0].est_minutes = None
    assert project_plan(assessment).effects.est_total_minutes is None


def test_unsupported_components_are_visible_not_silently_installed(assessment):
    assessment.updates[0].adapter_supported = False
    assessment.updates[0].exclusion_reason = "Needs a supported host-side agent."
    result = project_plan(assessment)
    assert not result.updates
    assert result.not_included[0].reason == "Needs a supported host-side agent."
    assert result.blockers


def test_chain_has_unique_step_ids_and_no_278_requirement(assessment):
    assessment.updates.append(
        assessment.updates[0].model_copy(
            update={"from_version": "1.48", "to": "3.19", "package_sha256": "e" * 64}
        )
    )
    result = project_plan(assessment)
    assert result.blockers == []
    assert len({u.step_id for u in result.updates}) == 2
    assert result.effects.ilo_restarts == 2
    assessment.updates[1].from_version = "2.78"
    assert project_plan(assessment).blockers


def test_duplicate_update_is_not_dispatched_twice(assessment):
    assessment.updates *= 2
    result = project_plan(assessment)
    assert len(result.updates) == 1
    assert result.blockers


@pytest.mark.parametrize(
    "field,value",
    [("device_id", "other"), ("report_sha256", "e" * 64), ("package_identity_sha256", "f" * 64)],
)
def test_review_identity_changes_with_target_package_or_evidence(assessment, field, value):
    previous = assessment_digest(assessment)
    setattr(assessment, field, value)
    assert assessment_digest(assessment) != previous


def test_cannot_claim_executable_plan_with_blockers_or_hidden_restarts(assessment):
    data = project_plan(assessment).model_dump()
    with pytest.raises(ValidationError):
        UpdatePlan.model_validate({**data, "can_apply": True})
    with pytest.raises(ValidationError):
        UpdatePlan.model_validate({**data, "effects": {**data["effects"], "host_restarts": 1}})
