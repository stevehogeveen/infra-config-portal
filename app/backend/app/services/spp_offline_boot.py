"""Durable offline-SPP orchestration. Vendor SUM owns installation order.

Every transport mutation is claimed before it can be sent. A lost response is
never permission to retry that mutation. Status reads only recorded evidence.
"""

import hashlib
import hmac
import json
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import AuditEvent, FirmwareApproval, GuardedOperation
from app.providers.hpe_spp_boot import CommandNotSent
from app.services.audit import record_audit_event
from app.services.guarded_operation_ledger import OperationConflict, find_attempt, reserve
from app.services.spp_update_contract import Step, UpdatePlan, UpdateStatus
from app.services.spp_update_execution import _review, _transition, status

MODE = "offline-spp-boot-v1"
PHASES = ("media", "boot", "reset", "eject")


def _stamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timestamp needs timezone")
    return result


# HPE's updater normally restarts by itself; after this long in its environment without a
# restart, it is waiting on its own screen (it stops there when a part reports an error).
UPDATER_SETTLED = timedelta(minutes=15)
# After the updater's restart: no further restart, nothing queued, disc detached for this long
# means HPE's updater is finished, whatever it managed to install.
FINISHED_SETTLED = timedelta(minutes=10)


def _explain(reading, facts, first_post, now):
    """Plain words for what the server shows now. Read-only evidence, never completion proof."""
    parts = reading.get("parts") or []
    queued = reading.get("queued") or []
    done = [part for part in parts if part.get("at_target")]
    left = [part for part in parts if not part.get("at_target")]
    try:
        post_time = _stamp(reading.get("post_timestamp"))
        started = post_time > _stamp(facts["post_timestamp"])
        restarted = bool(first_post) and post_time > _stamp(first_post)
        in_updater_for = now - post_time if started and not restarted else timedelta(0)
    except (TypeError, ValueError, AttributeError):
        started = restarted = False
        in_updater_for = timedelta(0)
    error = bool(reading.get("update_errors"))
    waiting = (
        started
        and not restarted
        and bool(left)
        and reading.get("power") == "On"
        and in_updater_for >= UPDATER_SETTLED
        and (bool(queued) or bool(done) or error)
    )
    count = f"{len(done)} of {len(parts)} parts are already at their new version"
    if not started:
        summary = "The server is starting HPE's updater from the SPP disc."
    elif restarted:
        summary = f"The server restarted after HPE's updater. {count}; the app is reading the versions back."
    elif waiting:
        summary = (
            f"HPE's updater has finished what it can do without a restart: {count}. "
            "The rest install while the server restarts"
            + (f" ({len(queued)} queued in the iLO)" if queued else "")
            + ". HPE's screen is waiting for you: open the iLO remote console and choose Reboot."
            + (" HPE's updater reported an error for at least one part; any part that does not reach its version after the restart is shown as not verified." if error else "")
        )
    else:
        summary = f"HPE's updater is running: {count}."
    return {
        "checked_at": reading.get("checked_at"),
        "power": reading.get("power"),
        "post_state": reading.get("post_state"),
        "updater_started": started,
        "restarted_after_updater": restarted,
        "parts": parts,
        "queued": queued,
        "updater_reported_error": error,
        "waiting_for_reboot": waiting,
        "summary": summary,
    }


def _equivalent(original, fresh):
    return all(
        original.get(k) == fresh.get(k)
        for k in (
            "device_id",
            "hardware_identity",
            "endpoint_identity",
            "package_sha256",
            "boot_profile",
            "component_identity",
            "expected",
            "media_path",
            "media_url",
            "media_device",
        )
    )


class OfflineBackend:
    mode = MODE

    def __init__(self, session_factory, transport):
        self.sessions = session_factory
        self.transport = transport

    def available(self, profile_id, device_id):
        with self.sessions() as session:
            return self.transport.available(session, profile_id, device_id)

    def plan(self, session, profile_id, device_id, actor):
        facts = self.transport.capture(session, profile_id, device_id)
        if not facts.get("update_idle"):
            raise OperationConflict("Another firmware update is still active.")
        if facts.get("media_inserted") is True:
            raise OperationConflict(
                "Virtual media is already connected. Disconnect it before starting a new SPP run."
            )
        if not facts.get("post_timestamp"):
            raise OperationConflict(
                "The server did not report the POST timestamp needed to track the updater reboot."
            )
        try:
            _stamp(facts["post_timestamp"])
        except (AttributeError, TypeError, ValueError):
            raise OperationConflict(
                "The server's POST timestamp could not be interpreted."
            ) from None
        if not facts["expected"]:
            raise OperationConflict(
                "No independently verifiable newer firmware was identified in this package."
            )
        if session.scalar(
            select(GuardedOperation.id).where(GuardedOperation.active_device == device_id)
        ):
            raise OperationConflict("A recorded operation already holds this server.")
        now = datetime.now(UTC)
        token = secrets.token_hex(32)
        phrase = f"UPDATE {device_id}"
        plan = UpdatePlan(
            execution_mode="offline",
            plan_id=secrets.token_hex(16),
            profile_id=profile_id,
            device_id=device_id,
            review_token=token,
            expires_at=now + timedelta(minutes=30),
            server=facts["server"],
            package=facts["package"],
            updates=[
                dict(
                    step_id=f"verify-{i}",
                    component=item["component"],
                    from_version=item["installed"],
                    to=item["target"],
                    order=i + 1,
                    restarts="none",
                )
                for i, item in enumerate(facts["expected"])
            ],
            effects=dict(
                host_restarts=None,
                ilo_restarts=None,
                est_total_minutes=None,
                power_on_required=facts["power_state"] == "Off",
            ),
            warnings=[
                "HPE's automatic updater selects all applicable firmware from this ISO, including components not listed here.",
                "The server will restart to run the updater and may restart again. Keep power connected.",
                "Listed versions are verification targets, not a promised installation order.",
            ],
            can_apply=True,
            confirmation_phrase=phrase,
            details={
                "method": MODE,
                "iso_sha256": facts["package_sha256"],
                "unassessed": facts.get("unassessed", []),
                "actions": [
                    "Serve selected ISO",
                    "Insert virtual media",
                    "Set one-time CD boot",
                    "Power on or restart server",
                    "Observe vendor update and reboot",
                    "Verify listed firmware",
                    "Eject only this operation's media",
                ],
            },
        )
        saved = plan.model_copy(
            update={"review_token": None, "confirmation_phrase": None, "can_apply": False}
        )
        row = FirmwareApproval(
            token_hash=hashlib.sha256(token.encode()).hexdigest(),
            profile_id=profile_id,
            device_id=device_id,
            actor=actor,
            confirmation_phrase=phrase,
            expires_at=plan.expires_at,
            intent_json={
                "operation": "whole-spp-update",
                "mode": MODE,
                "facts": facts,
                "plan": saved.model_dump(mode="json", by_alias=True),
            },
        )
        session.add(row)
        record_audit_event(
            session,
            actor=actor,
            event_type="spp.offline.review",
            message="Offline-SPP review issued; no hardware changes.",
            data={"profile_id": profile_id, "device_id": device_id, "plan_id": plan.plan_id},
        )
        session.commit()
        return plan

    def submit(self, session, profile_id, device_id, actor, request):
        row = _review(
            session,
            profile_id=profile_id,
            device_id=device_id,
            actor=actor,
            token=request.review_token,
        )
        if row.intent_json.get("mode") != MODE:
            raise OperationConflict("The review uses a different firmware execution method.")
        existing = find_attempt(
            session, profile_id, device_id, "firmware-execution", request.idempotency_key
        )
        if existing:
            if row.operation_id != existing.id:
                raise OperationConflict("Attempt key belongs to another review.")
            return status(session, existing.id)
        if not hmac.compare_digest(row.confirmation_phrase, request.confirmation_phrase):
            raise OperationConflict("Approval does not match the reviewed plan.")
        expiry = (
            row.expires_at.replace(tzinfo=UTC) if row.expires_at.tzinfo is None else row.expires_at
        )
        if expiry <= datetime.now(UTC):
            raise OperationConflict("Review expired. Review again.")
        fresh = self.transport.capture(session, profile_id, device_id)
        if not _equivalent(row.intent_json["facts"], fresh):
            raise OperationConflict("The server, media or reviewed component targets changed.")
        op = reserve(
            session,
            profile_id=profile_id,
            device_id=device_id,
            resource="firmware-execution",
            idempotency_key=request.idempotency_key,
            reviewed_intent={"review_token_sha256": row.token_hash, "intent": row.intent_json},
            actor=actor,
            firmware_review_id=row.id,
        )
        plan = UpdatePlan.model_validate_json(json.dumps(row.intent_json["plan"]))
        snapshot = UpdateStatus(
            execution_mode="offline",
            profile_id=profile_id,
            device_id=device_id,
            operation_id=op.id,
            idempotency_key=request.idempotency_key,
            status="running",
            steps=[Step(**item.model_dump(), state="waiting") for item in plan.updates],
            current_step=plan.updates[0].step_id,
            message="Approved; preparing the selected SPP.",
            next_action=None,
            evidence_at=None,
            active=True,
        )
        _transition(session, op.id, "accepted", "spp-offline-ready-media", snapshot, actor)
        return status(session, op.id)

    def _note(self, session, op, name, value):
        record_audit_event(
            session,
            actor="spp-worker",
            event_type="spp.offline.observation",
            message="Offline-SPP execution evidence recorded.",
            data={"operation_id": op.id, "name": name, "value": value},
        )
        session.commit()

    def _last(self, session, operation_id, name):
        event = session.scalar(
            select(AuditEvent)
            .where(
                AuditEvent.event_type == "spp.offline.observation",
                AuditEvent.data_json["operation_id"].as_string() == operation_id,
                AuditEvent.data_json["name"].as_string() == name,
            )
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(1)
        )
        return event.data_json["value"] if event else None

    def advance(self, session, operation_id):
        op = session.get(GuardedOperation, operation_id, populate_existing=True)
        review = session.scalar(
            select(FirmwareApproval).where(FirmwareApproval.operation_id == operation_id)
        )
        if not op or not op.active_device or not review or review.intent_json.get("mode") != MODE:
            return
        current = status(session, op.id)
        facts = review.intent_json["facts"]
        if op.status in {"spp-offline-observing", "spp-offline-observation-timeout"}:
            if op.status == "spp-offline-observation-timeout":
                # Keep looking (at most once a minute) for an updater that finished short.
                previous = self._last(session, op.id, "poll")
                if not previous or datetime.now(UTC) - _stamp(previous["checked_at"]) > timedelta(minutes=1):
                    self._note(session, op, "poll", {"checked_at": datetime.now(UTC).isoformat()})
                    self._finished_short(session, op, current, facts)
                return
            self._observe(session, op, current, facts)
            return
        if not op.status.startswith("spp-offline-ready-"):
            if op.status.startswith("spp-offline-sent-"):
                updated = (
                    op.updated_at.replace(tzinfo=UTC)
                    if op.updated_at.tzinfo is None
                    else op.updated_at
                )
                if datetime.now(UTC) - updated > timedelta(minutes=2):
                    phase = op.status.removeprefix("spp-offline-sent-")
                    _transition(
                        session,
                        op.id,
                        op.status,
                        f"spp-offline-uncertain-{phase}",
                        current.model_copy(
                            update={
                                "status": "uncertain",
                                "message": "Execution was interrupted. Check the server's status to reconcile this action without resending it.",
                            }
                        ),
                        "spp-worker",
                    )
            return
        phase = op.status.removeprefix("spp-offline-ready-")
        if phase not in PHASES:
            raise OperationConflict("Unknown offline-SPP phase.")
        sent = f"spp-offline-sent-{phase}"
        snapshot = current.model_copy(
            update={
                "message": {
                    "media": "Mounting the selected SPP.",
                    "boot": "Setting one-time SPP boot.",
                    "reset": "Starting HPE's automatic firmware updater.",
                    "eject": "Firmware versions verified; disconnecting update media.",
                }[phase]
            }
        )
        try:
            self.transport.preflight(session, op.device_id, facts, phase)
        except Exception:
            unsent = phase == "media"
            failure = current.model_copy(
                update={
                    "status": "failed" if unsent else "uncertain",
                    "active": not unsent,
                    "dispatch_prevented": unsent,
                    "message": "Preparation changed or failed before the next hardware command; that command was not sent.",
                    "next_action": "Review the update again."
                    if unsent
                    else "Inspect the recorded partial SPP preparation.",
                }
            )
            _transition(
                session,
                op.id,
                op.status,
                "failed" if unsent else f"spp-offline-paused-{phase}",
                failure,
                "spp-worker",
            )
            return
        if not _transition(session, op.id, op.status, sent, snapshot, "spp-worker"):
            return
        try:
            # This run-owned authority is bounded to the reviewed target and phase;
            # it never expands the global operator write scope.
            self._note(session, op, "authority", {"phase": phase, "state": "granted"})
            self._note(
                session, op, f"attempt-{phase}", {"checked_at": datetime.now(UTC).isoformat()}
            )
            result = self.transport.dispatch(session, op.device_id, facts, phase)
            self._note(session, op, phase, result)
        except CommandNotSent as exc:
            first = phase == "media"
            _transition(
                session,
                op.id,
                sent,
                "failed" if first else f"spp-offline-paused-{phase}",
                snapshot.model_copy(
                    update={
                        "status": "failed" if first else "uncertain",
                        "active": not first,
                        "dispatch_prevented": first,
                        "message": str(exc),
                        "next_action": "Review the update again."
                        if first
                        else "Check status to continue preparation.",
                    }
                ),
                "spp-worker",
            )
            return
        except Exception:
            unresolved = snapshot.model_copy(
                update={
                    "status": "uncertain",
                    "message": "The last hardware action has an unknown outcome. It will not be sent again.",
                    "next_action": "Inspect the server's recorded operation before another update.",
                }
            )
            _transition(
                session, op.id, sent, f"spp-offline-uncertain-{phase}", unresolved, "spp-worker"
            )
            return
        finally:
            self._note(session, op, "authority", {"phase": phase, "state": "revoked"})
        if phase == "eject":
            self._complete(session, op, current, sent)
        else:
            target = {
                "media": "spp-offline-ready-boot",
                "boot": "spp-offline-ready-reset",
                "reset": "spp-offline-observing",
            }[phase]
            message = (
                "HPE's updater is running. Waiting for its reboot and firmware readback."
                if phase == "reset"
                else "Preparing HPE's automatic update."
            )
            _transition(
                session,
                op.id,
                sent,
                target,
                snapshot.model_copy(update={"message": message}),
                "spp-worker",
            )

    def _complete(self, session, op, current, state):
        proof = self._last(session, op.id, "verified")
        if not proof:
            raise OperationConflict("Missing firmware completion evidence.")
        checked = _stamp(proof["checked_at"])
        started = _stamp(self._last(session, op.id, "reset")["checked_at"])
        steps = [
            Step(
                **{
                    **step.model_dump(),
                    "state": "done",
                    "started_at": started,
                    "finished_at": checked,
                    "verified_version": step.to,
                }
            )
            for step in current.steps
        ]
        finished = current.model_copy(
            update={
                "status": "verified",
                "active": False,
                "current_step": None,
                "steps": steps,
                "evidence_at": checked,
                "message": "Listed firmware versions verified after the updater reboot; update media disconnected.",
                "next_action": None,
            }
        )
        _transition(session, op.id, state, "verified", finished, "spp-worker")

    def verify(self, session, profile_id, device_id, operation_id):
        op = session.get(GuardedOperation, operation_id, populate_existing=True)
        review = session.scalar(
            select(FirmwareApproval).where(FirmwareApproval.operation_id == operation_id)
        )
        if (
            not op
            or (op.profile_id, op.device_id) != (profile_id, device_id)
            or not review
            or review.intent_json.get("mode") != MODE
        ):
            raise OperationConflict("No matching offline-SPP operation exists.")
        current = status(session, op.id)
        if not op.active_device:
            return current
        if op.status in {"spp-offline-observing", "spp-offline-observation-timeout"}:
            self._observe(session, op, current, review.intent_json["facts"], explicit=True)
            return status(session, op.id)
        if op.status.startswith("spp-offline-paused-"):
            phase = op.status.removeprefix("spp-offline-paused-")
            if phase not in PHASES:
                return current
            self.transport.preflight(session, device_id, review.intent_json["facts"], phase)
            _transition(
                session,
                op.id,
                op.status,
                f"spp-offline-ready-{phase}",
                current.model_copy(
                    update={
                        "status": "running",
                        "next_action": None,
                        "message": "Preparation is ready; continuing the approved update.",
                    }
                ),
                "spp-worker",
            )
            return status(session, op.id)
        prefix = next(
            (p for p in ("spp-offline-sent-", "spp-offline-uncertain-") if op.status.startswith(p)),
            None,
        )
        if not prefix:
            return current
        phase = op.status.removeprefix(prefix)
        if phase not in PHASES:
            return current
        state = op.status
        facts = review.intent_json["facts"]
        proof = self.transport.reconcile_phase(session, device_id, facts, phase)
        if proof.get("applied") is not True:
            return current
        attempt = self._last(session, op.id, f"attempt-{phase}")
        if not attempt:
            return current
        try:
            checked = _stamp(proof["checked_at"])
            now = datetime.now(UTC)
            if not _stamp(attempt["checked_at"]) < checked <= now:
                return current
            if now - checked > timedelta(minutes=5):
                return current
        except (KeyError, TypeError, ValueError):
            return current
        if phase == "eject":
            if proof.get("versions_match") is not True or not self._last(
                session, op.id, "verified"
            ):
                return current
            self._note(
                session,
                op,
                "verified",
                {"checked_at": proof["checked_at"], "post_timestamp": proof.get("post_timestamp")},
            )
            self._complete(session, op, current, state)
        else:
            self._note(session, op, phase, attempt)
            if phase == "reset":
                self._note(session, op, "first_post", proof["post_timestamp"])
            target = {
                "media": "spp-offline-ready-boot",
                "boot": "spp-offline-ready-reset",
                "reset": "spp-offline-observing",
            }[phase]
            _transition(
                session,
                op.id,
                state,
                target,
                current.model_copy(
                    update={
                        "status": "running",
                        "message": "The interrupted action was confirmed by readback; continuing the approved update.",
                        "next_action": None,
                    }
                ),
                "spp-worker",
            )
        return status(session, op.id)

    def _close_short(self, session, op, current, reading, since_restart):
        """HPE's updater is finished but not every listed part reached its version: close the run
        as failed with what the server shows, and release the server. Nothing is sent."""
        if (
            since_restart < FINISHED_SETTLED
            or reading.get("queued")
            or reading.get("media_inserted") is not False
            # Not busy is enough: the iLO keeps the last update's result message after finishing.
            or str(reading.get("update_state") or "").upper() not in {"IDLE", "COMPLETE", "COMPLETED", "ERROR"}
        ):
            return
        parts = reading.get("parts") or []
        done = [p["component"] for p in parts if p.get("at_target")]
        short = [f"{p['component']} (still {p.get('installed') or 'unknown'}, wanted {p['target']})" for p in parts if not p.get("at_target")]
        steps = [step.model_copy(update={"state": "not_started"}) for step in current.steps]
        if steps:
            steps[0] = steps[0].model_copy(update={"state": "failed"})
        message = (
            "HPE's updater finished, but not every part reached its new version. "
            + ("The iLO reported an error from the update. " if reading.get("update_errors") else "")
            + (f"Already at the new version: {', '.join(done)}. " if done else "")
            + f"Not updated: {'; '.join(short) or 'unknown'}. Nothing more will be sent; review the update again."
        )
        _transition(
            session, op.id, op.status, "failed",
            current.model_copy(update={
                "status": "failed", "active": False, "current_step": None, "steps": steps,
                "message": message[:1000], "next_action": "Review the update again.",
                "evidence_at": _stamp(reading["checked_at"]), "observed": None,
            }),
            "spp-worker",
        )

    def _finished_short(self, session, op, current, facts):
        first = self._last(session, op.id, "first_post")
        if not first:
            return False
        try:
            reading = self.transport.observe(session, op.device_id, facts)
            post_time = _stamp(reading["post_timestamp"])
        except Exception:
            return False
        if (
            reading.get("hardware_identity") != facts["hardware_identity"]
            or post_time <= _stamp(first)
            or reading.get("versions_match") is True
        ):
            return False
        self._close_short(session, op, current, reading, datetime.now(UTC) - post_time)
        refreshed = session.get(GuardedOperation, op.id, populate_existing=True)
        return refreshed is not None and refreshed.active_device is None

    def _observe(self, session, op, current, facts, explicit=False):
        reset = self._last(session, op.id, "reset")
        if not reset:
            return
        if not explicit and datetime.now(UTC) - _stamp(reset["checked_at"]) > timedelta(hours=4):
            # One last read: an updater that clearly finished with parts short closes as failed
            # (and frees the server) instead of sitting as "unknown".
            if self._finished_short(session, op, current, facts):
                return
            _transition(
                session,
                op.id,
                op.status,
                "spp-offline-observation-timeout",
                current.model_copy(
                    update={
                        "status": "uncertain",
                        "message": "The updater has not provided completion evidence within four hours. No restart or update will be repeated.",
                        "next_action": "Check status to read the server again.",
                    }
                ),
                "spp-worker",
            )
            return
        previous = self._last(session, op.id, "poll")
        if (
            not explicit
            and previous
            and datetime.now(UTC) - _stamp(previous["checked_at"]) < timedelta(seconds=20)
        ):
            return
        self._note(session, op, "poll", {"checked_at": datetime.now(UTC).isoformat()})
        try:
            reading = self.transport.observe(session, op.device_id, facts)
        except Exception:
            return  # iLO and host may be restarting. No write is retried.
        if not reset or reading.get("hardware_identity") != facts["hardware_identity"]:
            return
        try:
            checked = _stamp(reading["checked_at"])
            post_time = _stamp(reading["post_timestamp"])
        except (KeyError, AttributeError, TypeError, ValueError):
            return
        submitted = _stamp(reset["checked_at"])
        now = datetime.now(UTC)
        if not submitted < checked <= now or now - checked > timedelta(minutes=5):
            return
        self._note(session, op, "observed", _explain(reading, facts, self._last(session, op.id, "first_post"), now))
        post = reading.get("post_timestamp")
        if post_time <= _stamp(facts["post_timestamp"]):
            return
        first = self._last(session, op.id, "first_post")
        if first is None:
            self._note(session, op, "first_post", post)
            return
        # A second POST distinguishes the updater's exit/reboot from initial SPP boot.
        if post_time <= _stamp(first):
            return
        if reading.get("versions_match") is not True:
            self._close_short(session, op, current, reading, now - post_time)
            return
        if (
            reading.get("update_idle") is not True
            or reading.get("component_identity") != facts["component_identity"]
        ):
            return
        self._note(
            session, op, "verified", {"checked_at": reading["checked_at"], "post_timestamp": post}
        )
        _transition(
            session,
            op.id,
            op.status,
            "spp-offline-ready-eject",
            current.model_copy(
                update={
                    "status": "verifying",
                    "message": "Listed firmware versions match; finishing update media cleanup.",
                }
            ),
            "spp-worker",
        )
