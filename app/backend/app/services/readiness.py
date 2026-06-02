from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.enums import RequestStatus
from app.models import Request
from app.schemas import ReadinessIssue, RequestReadinessRead
from app.services.lifecycle import (
    ExecutionPlanProblem,
    get_request,
    inspect_execution_plan,
)


def get_request_readiness(session: Session, request_id: str) -> RequestReadinessRead:
    request = get_request(session, request_id)
    blockers: list[ReadinessIssue] = []
    warnings: list[ReadinessIssue] = []

    ready_for_submit = False
    ready_for_approval = False
    ready_for_plan = False
    ready_for_execute = False
    next_action = "none"
    summary = "Request is not ready for another lifecycle action."

    if request.status == RequestStatus.DRAFT.value:
        blockers.extend(_required_request_blockers(request))
        if blockers:
            next_action = "edit"
            summary = "Draft request is missing required intent fields."
        else:
            ready_for_submit = True
            next_action = "submit"
            summary = "Draft request has required fields and can be submitted."

    elif request.status == RequestStatus.SUBMITTED.value:
        next_action = "wait"
        warnings.append(
            _warning(
                "validation_pending",
                "Request has been submitted and is waiting for validation.",
                "Wait for validation to complete before approving or planning.",
            )
        )
        summary = "Request is waiting for validation."

    elif request.status == RequestStatus.VALIDATING.value:
        next_action = "wait"
        warnings.append(
            _warning(
                "validation_in_progress",
                "Request validation is in progress.",
                "Wait for validation to complete before approving or planning.",
            )
        )
        summary = "Request validation is in progress."

    elif request.status == RequestStatus.NEEDS_APPROVAL.value:
        ready_for_approval = True
        next_action = "approve_or_reject"
        summary = "Request validated and is waiting for an approval decision."

    elif request.status == RequestStatus.APPROVED.value:
        ready_for_plan = True
        next_action = "plan"
        summary = "Request is approved and ready for dry-run planning."

    elif request.status == RequestStatus.PLANNED.value:
        _, plan_problem = inspect_execution_plan(session, request)
        if plan_problem is None:
            ready_for_execute = True
            next_action = "execute"
            summary = "Request has a valid dry-run plan and is ready for mock execution."
        else:
            blockers.append(_plan_problem_blocker(plan_problem))
            next_action = _next_action_for_plan_problem(plan_problem)
            summary = (
                "Request is planned, but execution is blocked because the "
                "persisted dry-run plan is not valid for the current request."
            )

    elif request.status == RequestStatus.EXECUTING.value:
        next_action = "monitor"
        warnings.append(
            _warning(
                "request_executing",
                "Request is already executing.",
                "Monitor the workflow run and audit events.",
            )
        )
        summary = "Request is executing; no additional lifecycle action is available."

    elif request.status == RequestStatus.COMPLETED.value:
        blockers.append(
            _blocker(
                "already_completed",
                "Request already completed.",
                "Review the workflow run and audit history; no further action is available.",
            )
        )
        summary = "Request is complete; no further action is available."

    elif request.status == RequestStatus.CANCELLED.value:
        blockers.append(
            _blocker(
                "cancelled_request",
                "Request was cancelled and is locked.",
                "Create a new request if this intent still needs to run.",
            )
        )
        summary = "Request is cancelled and locked."

    elif request.status == RequestStatus.REJECTED.value:
        blockers.append(
            _blocker(
                "rejected_request",
                "Request was rejected and is locked.",
                "Create or revise a request before submitting again.",
            )
        )
        summary = "Request is rejected and locked."

    elif request.status == RequestStatus.FAILED.value:
        blockers.append(
            _blocker(
                "failed_request",
                "Request failed and is locked.",
                "Review audit events, then create a new request if the intent is still needed.",
            )
        )
        summary = "Request failed and is locked."

    return RequestReadinessRead(
        request_id=request.id,
        current_status=request.status,
        ready_for_submit=ready_for_submit,
        ready_for_approval=ready_for_approval,
        ready_for_plan=ready_for_plan,
        ready_for_execute=ready_for_execute,
        next_action=next_action,
        blockers=blockers,
        warnings=warnings,
        summary=summary,
    )


def _required_request_blockers(request: Request) -> list[ReadinessIssue]:
    if request.request_type != "vm_deploy":
        return [
            _blocker(
                "unsupported_request_type",
                f"Readiness is not available for request type {request.request_type!r}.",
                "Use a supported VM deployment request.",
            )
        ]

    if request.vm_deploy is None:
        return [
            _blocker(
                "request_intent_missing",
                "VM deployment intent is missing from the request.",
                "Edit or recreate the draft request with VM deployment details.",
            )
        ]

    missing_fields: list[str] = []
    for field_name in ("requester", "environment", "site", "owner", "expiry_date"):
        if _is_missing(getattr(request, field_name)):
            missing_fields.append(field_name)

    vm = request.vm_deploy
    for field_name in (
        "cluster",
        "vm_name",
        "template",
        "cpu",
        "memory_gb",
        "disk_gb",
        "network",
    ):
        if _is_missing(getattr(vm, field_name)):
            missing_fields.append(f"vm.{field_name}")

    if _is_missing(vm.datastore) and _is_missing(vm.storage_tier):
        missing_fields.append("vm.datastore_or_storage_tier")

    if not missing_fields:
        return []

    return [
        _blocker(
            "required_fields_missing",
            f"Missing required fields: {', '.join(missing_fields)}.",
            "Edit the draft request and provide the missing fields before submitting.",
        )
    ]


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def _plan_problem_blocker(problem: ExecutionPlanProblem) -> ReadinessIssue:
    return _blocker(
        problem.code,
        problem.message,
        _plan_problem_action(problem),
    )


def _plan_problem_action(problem: ExecutionPlanProblem) -> str:
    reason = problem.data.get("reason")
    if reason == "request_intent_mismatch":
        return (
            "Use the formal edit flow to reconcile intent, then submit, approve, "
            "and plan again."
        )
    if problem.code == "plan_belongs_to_different_request":
        return "Discard the mismatched dry-run plan and create a new plan for this request."
    return "Create a new dry-run plan before executing."


def _next_action_for_plan_problem(problem: ExecutionPlanProblem) -> str:
    if problem.data.get("reason") == "request_intent_mismatch":
        return "edit_resubmit"
    return "replan"


def _blocker(code: str, message: str, action: str) -> ReadinessIssue:
    return ReadinessIssue(
        code=code,
        message=message,
        severity="blocking",
        action=action,
    )


def _warning(code: str, message: str, action: str) -> ReadinessIssue:
    return ReadinessIssue(
        code=code,
        message=message,
        severity="warning",
        action=action,
    )
