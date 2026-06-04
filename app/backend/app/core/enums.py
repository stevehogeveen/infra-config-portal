from __future__ import annotations

from enum import Enum


class EnvironmentName(str, Enum):
    DEV = "dev"
    TEST = "test"
    PROD = "prod"


class RequestStatus(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    VALIDATING = "validating"
    NEEDS_APPROVAL = "needs_approval"
    APPROVED = "approved"
    PLANNED = "planned"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class WorkflowRunStatus(str, Enum):
    PLANNED = "planned"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    INVALIDATED = "invalidated"
    REJECTED = "rejected"
