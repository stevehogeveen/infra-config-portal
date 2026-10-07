"""Offline-SPP workflow tests: synthetic inventory, no sockets or vendor process."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.models import GuardedOperation
from app.services.spp_offline_boot import OfflineBackend
from app.services.spp_update_contract import ApplyRequest
from app.services.spp_update_execution import status
from app.services.spp_update_runtime import work_once, reconcile
from app.services.guarded_operation_ledger import OperationConflict


class Transport:
    def __init__(self):
        self.sent = []
        self.fail = None
        self.fail_before = None
        self.facts = dict(
            profile_id="kit",
            device_id="srv",
            hardware_identity="a" * 64,
            endpoint_identity="b" * 64,
            component_identity="c" * 64,
            package_sha256="d" * 64,
            boot_profile="e" * 64,
            media_path="fixture.iso",
            media_url="http://192.0.2.10/fixture.iso",
            media_device={"path": "/redfish/v1/Managers/1/VirtualMedia/2"},
            update_idle=True,
            media_inserted=False,
            power_state="On",
            post_timestamp="2026-01-01T00:00:00Z",
            server={"name": "Fixture server", "model": "Fixture Gen10", "manager_generation": 5},
            package={"file": "fixture.iso", "release": "2026.05"},
            expected=[
                {"component": "ROM", "installed": "1.46", "target": "3.66", "kind": "numeric"},
                {"component": "Drive / 1", "installed": "HPD1", "target": "HPD9", "kind": "drive"},
            ],
        )
        self.reading = dict(
            hardware_identity="a" * 64,
            component_identity="c" * 64,
            post_timestamp="2026-01-01T00:01:00Z",
            versions_match=True,
            update_idle=True,
        )

    def available(self, *args):
        return True

    def capture(self, *args):
        return deepcopy(self.facts)

    def preflight(self, session, device, facts, phase):
        if phase == self.fail_before:
            raise ValueError("fixture changed")

    def dispatch(self, session, device, facts, phase):
        self.sent.append(phase)
        if phase == self.fail:
            raise TimeoutError("fixture secret must not be persisted")
        return {"checked_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()}

    def observe(self, *args):
        return {**self.reading, "checked_at": datetime.now(UTC).isoformat()}

    def reconcile_phase(self, *args):
        return {**self.observe(), "applied": True}


def setup_run(session):
    transport = Transport()
    factory = sessionmaker(bind=session.get_bind())
    backend = OfflineBackend(factory, transport)
    plan = backend.plan(session, "kit", "srv", "fixture")
    request = ApplyRequest(
        review_token=plan.review_token,
        confirmation_phrase=plan.confirmation_phrase,
        idempotency_key="offline-attempt",
    )
    result = backend.submit(session, "kit", "srv", "fixture", request)
    return backend, transport, factory, result.operation_id, request


def poll(backend, session, operation):
    op = session.get(GuardedOperation, operation, populate_existing=True)
    backend._note(
        session, op, "poll", {"checked_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat()}
    )
    backend.advance(session, operation)


def test_boot_waits_for_second_post_and_versions_before_eject(db_session):
    backend, transport, factory, operation, request = setup_run(db_session)
    assert not transport.sent
    for _ in range(3):
        work_once(factory, backend)
    assert transport.sent == ["media", "boot", "reset"]
    poll(backend, db_session, operation)
    poll(backend, db_session, operation)
    assert status(db_session, operation).active
    transport.reading["post_timestamp"] = "2026-01-01T00:02:00Z"
    transport.reading["versions_match"] = False
    poll(backend, db_session, operation)
    assert transport.sent == ["media", "boot", "reset"]
    transport.reading["versions_match"] = True
    poll(backend, db_session, operation)
    assert status(db_session, operation).status == "verifying"
    # A fresh worker handles the persisted cleanup phase, not another boot.
    replacement = OfflineBackend(factory, transport)
    work_once(factory, replacement)
    result = status(db_session, operation)
    assert result.status == "verified" and not result.active
    assert result.execution_mode == "offline"
    assert transport.sent == ["media", "boot", "reset", "eject"]
    assert backend.submit(db_session, "kit", "srv", "fixture", request) == result


@pytest.mark.parametrize("phase", ["media", "boot", "reset", "eject"])
def test_lost_response_never_repeats_command(db_session, phase):
    backend, transport, factory, operation, _ = setup_run(db_session)
    transport.fail = phase
    for _ in range(3):
        work_once(factory, backend)
    if phase == "eject":
        poll(backend, db_session, operation)
        transport.reading["post_timestamp"] = "2026-01-01T00:02:00Z"
        poll(backend, db_session, operation)
        work_once(factory, backend)
    before = list(transport.sent)
    work_once(factory, OfflineBackend(factory, transport))
    assert transport.sent == before and before.count(phase) == 1
    assert status(db_session, operation).status == "uncertain"
    assert "secret" not in status(db_session, operation).model_dump_json()


@pytest.mark.parametrize(
    "field,value",
    [("hardware_identity", "wrong"), ("component_identity", "wrong"), ("update_idle", False)],
)
def test_incomplete_or_wrong_target_readback_cannot_finish(db_session, field, value):
    backend, transport, factory, operation, _ = setup_run(db_session)
    for _ in range(3):
        work_once(factory, backend)
    poll(backend, db_session, operation)
    transport.reading.update(post_timestamp="2026-01-01T00:02:00Z")
    transport.reading[field] = value
    poll(backend, db_session, operation)
    assert status(db_session, operation).active
    assert "eject" not in transport.sent


def test_failure_before_first_command_is_proven_unsent(db_session):
    backend, transport, factory, operation, _ = setup_run(db_session)
    transport.fail_before = "media"
    work_once(factory, backend)
    result = status(db_session, operation)
    assert result.dispatch_prevented and not result.active and not transport.sent


def test_lost_offline_admission_is_fenced_without_hardware(db_session):
    transport = Transport()
    backend = OfflineBackend(sessionmaker(bind=db_session.get_bind()), transport)
    plan = backend.plan(db_session, "kit", "srv", "fixture")
    request = ApplyRequest(
        review_token=plan.review_token,
        confirmation_phrase=plan.confirmation_phrase,
        idempotency_key="lost",
    )
    result = reconcile(db_session, "kit", "srv", "fixture", request)
    assert result.execution_mode == "offline" and result.dispatch_prevented
    assert backend.submit(db_session, "kit", "srv", "fixture", request) == result
    assert not transport.sent


def test_approval_rejects_changed_media_and_wrong_actor(db_session):
    transport = Transport()
    backend = OfflineBackend(sessionmaker(bind=db_session.get_bind()), transport)
    plan = backend.plan(db_session, "kit", "srv", "fixture")
    request = ApplyRequest(
        review_token=plan.review_token,
        confirmation_phrase=plan.confirmation_phrase,
        idempotency_key="changed",
    )
    with pytest.raises(OperationConflict):
        backend.submit(db_session, "kit", "srv", "other", request)
    transport.facts["package_sha256"] = "f" * 64
    with pytest.raises(OperationConflict):
        backend.submit(db_session, "kit", "srv", "fixture", request)
    assert not transport.sent


@pytest.mark.parametrize("phase", ["media", "boot", "reset", "eject"])
def test_explicit_readback_recovers_lost_response_without_resending(db_session, phase):
    backend, transport, factory, operation, _ = setup_run(db_session)
    transport.fail = phase
    for _ in range(3):
        work_once(factory, backend)
    if phase == "eject":
        poll(backend, db_session, operation)
        transport.reading["post_timestamp"] = "2026-01-01T00:02:00Z"
        poll(backend, db_session, operation)
        work_once(factory, backend)
    before = list(transport.sent)
    result = backend.verify(db_session, "kit", "srv", operation)
    assert transport.sent == before
    assert result.status == ("verified" if phase == "eject" else "running")
    transport.fail = None
    for _ in range(3):
        work_once(factory, backend)
    assert transport.sent.count(phase) == 1


@pytest.mark.parametrize("offset", [-600, 600])
def test_reconciliation_rejects_stale_and_future_evidence(db_session, offset):
    backend, transport, factory, operation, _ = setup_run(db_session)
    transport.fail = "media"
    work_once(factory, backend)
    transport.reconcile_phase = lambda *args: {
        "applied": True,
        "checked_at": (datetime.now(UTC) + timedelta(seconds=offset)).isoformat(),
    }
    assert backend.verify(db_session, "kit", "srv", operation).status == "uncertain"
    assert transport.sent == ["media"]


def test_observation_timeout_is_visible_and_explicit_read_can_finish(db_session):
    backend, transport, factory, operation, _ = setup_run(db_session)
    for _ in range(3):
        work_once(factory, backend)
    poll(backend, db_session, operation)
    op = db_session.get(GuardedOperation, operation, populate_existing=True)
    backend._note(
        db_session,
        op,
        "reset",
        {
            "checked_at": (datetime.now(UTC) - timedelta(hours=5)).isoformat(),
        },
    )
    work_once(factory, backend)
    assert status(db_session, operation).status == "uncertain"
    transport.reading["post_timestamp"] = "2026-01-01T00:02:00Z"
    work_once(factory, backend)
    assert status(db_session, operation).status == "uncertain"
    assert backend.verify(db_session, "kit", "srv", operation).status == "verifying"
    work_once(factory, backend)
    assert status(db_session, operation).status == "verified"
    assert transport.sent == ["media", "boot", "reset", "eject"]


def test_failed_preflight_after_mount_can_resume_the_unsent_command(db_session):
    backend, transport, factory, operation, _ = setup_run(db_session)
    work_once(factory, backend)
    transport.fail_before = "boot"
    work_once(factory, backend)
    assert status(db_session, operation).status == "uncertain"
    assert transport.sent == ["media"]
    transport.fail_before = None
    assert backend.verify(db_session, "kit", "srv", operation).status == "running"
    assert transport.sent == ["media"]
    work_once(factory, backend)
    assert transport.sent == ["media", "boot"]


def test_offline_api_plan_apply_and_exact_operation_verify(client, db_session, monkeypatch):
    from app.main import app
    from app.api import spp_update

    transport = Transport()
    backend = OfflineBackend(sessionmaker(bind=db_session.get_bind()), transport)
    monkeypatch.setattr(app.state, "spp_backend", backend, raising=False)
    monkeypatch.setattr(spp_update, "server_in_kit", lambda *args: None)
    base = "/api/v1/rack-plans/kit/firmware-update"
    params = {"device_id": "srv"}
    headers = {"X-Local-User": "fixture"}
    assert client.get(base + "/status", params=params).status_code == 200
    response = client.post(base + "/plan", params=params, json=params, headers=headers)
    assert response.status_code == 200
    plan = response.json()
    response = client.post(
        base + "/apply",
        params=params,
        headers=headers,
        json={
            "review_token": plan["review_token"],
            "confirmation_phrase": plan["confirmation_phrase"],
            "idempotency_key": "offline-api",
        },
    )
    assert response.status_code == 200 and not transport.sent
    operation = response.json()["operation_id"]
    transport.fail = "media"
    work_once(backend.sessions, backend)
    assert (
        client.post(base + "/verify", params=params, json={"operation_id": "wrong"}).status_code
        == 409
    )
    response = client.post(base + "/verify", params=params, json={"operation_id": operation})
    assert response.status_code == 200 and response.json()["status"] == "running"
    assert transport.sent == ["media"]


def test_media_delivery_failure_does_not_leave_an_unsent_run_locked(db_session):
    from app.providers.hpe_spp_boot import CommandNotSent

    backend, transport, factory, operation, _ = setup_run(db_session)

    def unavailable(*args):
        raise CommandNotSent("The ISO service is unavailable; no command was sent.")

    transport.dispatch = unavailable
    work_once(factory, backend)
    result = status(db_session, operation)
    assert result.status == "failed" and result.dispatch_prevented and not result.active
    assert not transport.sent


def test_explain_says_hpe_is_waiting_for_a_reboot_and_lists_what_is_left():
    from datetime import UTC, datetime, timedelta

    from app.services.spp_offline_boot import _explain

    start = datetime(2026, 10, 5, 18, 0, tzinfo=UTC)
    facts = {"post_timestamp": start.isoformat()}
    spp_boot = start + timedelta(minutes=10)
    reading = {
        "checked_at": (spp_boot + timedelta(minutes=40)).isoformat(),
        "post_timestamp": spp_boot.isoformat(),
        "power": "On", "post_state": "FinishedPost", "update_errors": True,
        "parts": [
            {"component": "System ROM / BIOS", "installed": "U32 v1.46", "target": "3.66", "at_target": False},
            {"component": "Drive: fixture / 2I:1:5", "installed": "HPD9", "target": "HPD9", "at_target": True},
        ],
        "queued": ["HPE Smart Array P408i-a fixture"],
    }
    look = _explain(reading, facts, spp_boot.isoformat(), spp_boot + timedelta(minutes=41))
    assert look["waiting_for_reboot"] is True and look["updater_started"] and not look["restarted_after_updater"]
    assert "1 of 2 parts are already at their new version" in look["summary"]
    assert "choose Reboot" in look["summary"] and "reported an error" in look["summary"]
    assert "1 queued in the iLO" in look["summary"]
    # Early on, the same reading is just "running"; after a restart it is "reading back".
    early = _explain(reading, facts, spp_boot.isoformat(), spp_boot + timedelta(minutes=5))
    assert early["waiting_for_reboot"] is False and early["summary"].startswith("HPE's updater is running")
    later = {**reading, "post_timestamp": (spp_boot + timedelta(minutes=50)).isoformat()}
    after = _explain(later, facts, spp_boot.isoformat(), spp_boot + timedelta(minutes=55))
    assert after["restarted_after_updater"] is True and "reading the versions back" in after["summary"]


def test_explain_before_the_updater_boots():
    from datetime import UTC, datetime

    from app.services.spp_offline_boot import _explain

    now = datetime(2026, 10, 5, 18, 0, tzinfo=UTC)
    look = _explain({"post_timestamp": now.isoformat(), "parts": []}, {"post_timestamp": now.isoformat()}, None, now)
    assert look["updater_started"] is False and "starting HPE's updater" in look["summary"]


def test_status_shows_the_latest_look_while_running_and_not_after_the_run(db_session):
    backend, transport, factory, operation, _ = setup_run(db_session)
    for _ in range(3):
        work_once(factory, backend)
    transport.reading["parts"] = [{"component": "iLO", "installed": "3.19", "target": "3.19", "at_target": True}]
    poll(backend, db_session, operation)
    running = status(db_session, operation)
    assert running.observed is not None and running.observed.parts[0].at_target is True
    assert running.observed.updater_started is True
    transport.reading["post_timestamp"] = "2026-01-01T00:02:00Z"
    poll(backend, db_session, operation)
    work_once(factory, backend)
    finished = status(db_session, operation)
    assert finished.status == "verified" and finished.active is False


def test_a_finished_updater_that_left_parts_short_closes_failed_and_releases_the_server(db_session):
    backend, transport, factory, operation, _ = setup_run(db_session)
    for _ in range(3):
        work_once(factory, backend)
    poll(backend, db_session, operation)  # first POST: the SPP boot
    restart = datetime.now(UTC) - timedelta(minutes=30)
    transport.reading.update(
        post_timestamp=restart.isoformat(), versions_match=False, media_inserted=False, update_state="Complete", queued=["fixture task"],
        parts=[{"component": "System ROM / BIOS", "installed": "U32 v1.46", "target": "3.66", "at_target": False},
               {"component": "Drive: fixture", "installed": "HPD9", "target": "HPD9", "at_target": True}])
    poll(backend, db_session, operation)
    assert status(db_session, operation).active is True  # something still queued in the iLO
    transport.reading["queued"] = []
    poll(backend, db_session, operation)
    closed = status(db_session, operation)
    assert closed.status == "failed" and closed.active is False
    assert "Already at the new version: Drive: fixture" in closed.message
    assert "System ROM / BIOS (still U32 v1.46, wanted 3.66)" in closed.message
    op = db_session.get(GuardedOperation, operation, populate_existing=True)
    assert op.active_device is None
    assert transport.sent == ["media", "boot", "reset"]


def test_every_offline_status_fits_the_status_column():
    import re
    from pathlib import Path

    from app.models import GuardedOperation

    width = GuardedOperation.__table__.c.status.type.length
    source = Path("app/services/spp_offline_boot.py").read_text()
    names = set(re.findall(r'"(spp-offline-[a-z-]+)"', source))
    names |= {prefix + phase for prefix in re.findall(r'f"(spp-offline-[a-z]+-)\{', source) for phase in ("media", "boot", "reset", "eject")}
    assert names and all(len(name) <= width for name in names), sorted(n for n in names if len(n) > width)
    assert all(len(f"pu-{o}-{i}") <= width for o in ("uncertain", "failed", "sent", "ok") for i in range(999))


def test_a_timed_out_run_whose_updater_finished_short_closes_instead_of_waiting_forever(db_session):
    backend, transport, factory, operation, _ = setup_run(db_session)
    for _ in range(3):
        work_once(factory, backend)
    poll(backend, db_session, operation)  # first POST
    op = db_session.get(GuardedOperation, operation, populate_existing=True)
    backend._note(db_session, op, "reset", {"checked_at": (datetime.now(UTC) - timedelta(hours=5)).isoformat()})
    transport.reading.update(post_timestamp=(datetime.now(UTC) - timedelta(minutes=30)).isoformat(), versions_match=False,
                             media_inserted=False, update_state="Complete", queued=[], parts=[{"component": "System ROM / BIOS", "installed": "U32 v1.46", "target": "3.66", "at_target": False}])
    work_once(factory, backend)
    closed = status(db_session, operation)
    assert closed.status == "failed" and closed.active is False and "System ROM / BIOS" in closed.message
