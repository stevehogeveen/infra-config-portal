"""Whole-SPP API boundary. These types do not confer execution authority."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator
from app.services.blocker_guidance import BlockerDetail

Text = Annotated[str, Field(min_length=1, max_length=1024)]
Identifier = Annotated[str, Field(min_length=1, max_length=128)]
Minutes = Annotated[int, Field(ge=0, le=10080)]
Restart = Literal["none", "ilo", "host"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, populate_by_name=True)


class Server(Contract):
    name: Text
    model: Text
    manager_generation: Literal[5, 6, 7]


class Package(Contract):
    file: Text
    release: Text


class Update(Contract):
    step_id: Identifier
    component: Text
    from_version: Text = Field(alias="from")
    to: Text
    order: int = Field(ge=1, le=256)
    restarts: Restart
    est_minutes: Minutes | None = None


class Effects(Contract):
    host_restarts: int | None = Field(ge=0, le=256)
    ilo_restarts: int | None = Field(ge=0, le=256)
    est_total_minutes: Minutes | None = None
    power_on_required: bool


class Excluded(Contract):
    component: Text
    reason: Text


class UpdatePlan(Contract):
    execution_mode: Literal["online", "offline"] = "online"
    plan_id: Identifier
    profile_id: Identifier
    device_id: Identifier
    review_token: Identifier | None
    expires_at: datetime
    server: Server
    package: Package
    updates: list[Update] = Field(max_length=256)
    effects: Effects
    not_included: list[Excluded] = Field(default_factory=list, max_length=256)
    blockers: list[Text] = Field(default_factory=list, max_length=256)
    blocker_details: list[BlockerDetail] = Field(default_factory=list, max_length=256)
    warnings: list[Text] = Field(default_factory=list, max_length=256)
    can_apply: bool
    confirmation_phrase: Text | None
    details: JsonValue = Field(default_factory=dict)

    @model_validator(mode="after")
    def consistent_plan(self):
        if self.expires_at.tzinfo is None:
            raise ValueError("Plan expiry must include a timezone.")
        if len({u.step_id for u in self.updates}) != len(self.updates):
            raise ValueError("Plan step IDs must be unique.")
        if [u.order for u in self.updates] != list(range(1, len(self.updates) + 1)):
            raise ValueError("Plan order must be contiguous and explicit.")
        if self.execution_mode == "online" and self.effects.host_restarts != sum(
            u.restarts == "host" for u in self.updates
        ):
            raise ValueError("Every host restart must appear in the plan.")
        if self.execution_mode == "online" and self.effects.ilo_restarts != sum(
            u.restarts == "ilo" for u in self.updates
        ):
            raise ValueError("Every iLO restart must appear in the plan.")
        if self.can_apply and (
            self.blockers
            or not self.updates
            or not self.review_token
            or not self.confirmation_phrase
        ):
            raise ValueError("An executable plan requires updates, approval and no blockers.")
        if not self.can_apply and (
            self.review_token is not None or self.confirmation_phrase is not None
        ):
            raise ValueError("A blocked plan cannot issue execution credentials.")
        return self


class PlanRequest(Contract):
    device_id: Identifier


class ApplyRequest(Contract):
    review_token: Identifier
    confirmation_phrase: Text
    idempotency_key: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


class Step(Update):
    state: Literal[
        "waiting",
        "installing",
        "restarting",
        "verifying",
        "done",
        "failed",
        "uncertain",
        "not_started",
    ]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    verified_version: Text | None = None

    @model_validator(mode="after")
    def verified_means_readback(self):
        for value in (self.started_at, self.finished_at):
            if value is not None and value.tzinfo is None:
                raise ValueError("Progress timestamps must include a timezone.")
        if self.finished_at is not None and (
            self.started_at is None or self.finished_at < self.started_at
        ):
            raise ValueError("A finish time must follow a start time.")
        if self.state == "done" and (self.verified_version != self.to or self.finished_at is None):
            raise ValueError("Done requires the exact reviewed version and completed readback.")
        if self.state != "done" and self.verified_version is not None:
            raise ValueError("Only a verified step can advertise an installed result.")
        return self


class ObservedPart(Contract):
    component: Text
    installed: Text | None
    target: Text
    at_target: bool


class Observed(Contract):
    """Latest read-only look at the server while HPE's updater runs. Explains progress; it is
    not completion evidence (steps stay unverified until the reboot readback)."""

    checked_at: datetime
    power: Text | None = None
    post_state: Text | None = None
    updater_started: bool = False
    restarted_after_updater: bool = False
    parts: list[ObservedPart] = Field(default_factory=list, max_length=256)
    queued: list[Text] = Field(default_factory=list, max_length=64)
    updater_reported_error: bool = False
    waiting_for_reboot: bool = False
    summary: Text


class UpdateStatus(Contract):
    execution_mode: Literal["online", "offline"] = "online"
    profile_id: Identifier
    device_id: Identifier
    operation_id: Identifier | None
    idempotency_key: Identifier | None
    status: Literal[
        "not_started", "running", "waiting_restart", "verifying", "verified", "failed", "uncertain"
    ]
    steps: list[Step] = Field(default_factory=list, max_length=256)
    current_step: Identifier | None
    message: Text
    next_action: Text | None
    evidence_at: datetime | None
    active: bool
    dispatch_prevented: bool = False
    observed: Observed | None = None

    @model_validator(mode="after")
    def consistent_progress(self):
        if self.evidence_at is not None and self.evidence_at.tzinfo is None:
            raise ValueError("Evidence timestamps must include a timezone.")
        if self.status != "not_started" and (not self.operation_id or not self.idempotency_key):
            raise ValueError("Recorded progress requires its operation and attempt identity.")
        if len({s.step_id for s in self.steps}) != len(self.steps):
            raise ValueError("Progress step IDs must be unique.")
        if [s.order for s in self.steps] != list(range(1, len(self.steps) + 1)):
            raise ValueError("Progress must preserve plan order.")
        if self.current_step is not None and self.current_step not in {
            s.step_id for s in self.steps
        }:
            raise ValueError("Current step must belong to this plan.")
        previous_done = True
        for step in self.steps:
            if step.state not in {"waiting", "not_started"} and not previous_done:
                raise ValueError("A later step cannot run after an unfinished or failed step.")
            previous_done = previous_done and step.state == "done"
        if self.status == "verified" and (
            not self.steps or not previous_done or self.active or self.evidence_at is None
        ):
            raise ValueError(
                "Verified requires completed readback for every step and a released lock."
            )
        if (
            self.status in {"running", "waiting_restart", "verifying", "uncertain"}
            and not self.active
        ):
            raise ValueError("Unresolved work must retain its operation lock.")
        if self.dispatch_prevented and (
            self.status != "failed" or self.active or any(s.started_at for s in self.steps)
        ):
            raise ValueError("Dispatch prevention is only proof of an unsent closed attempt.")
        return self
