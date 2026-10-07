"""Both guarded resources must fail closed without provider or network access."""

import pytest
from sqlalchemy import select

from app.models import AuditEvent


@pytest.fixture(params=["firmware-execution", "drive-return-to-service"])
def guarded(client, request):
    kit = client.post(
        "/api/v1/lab/profiles",
        json={
            "name": "Guarded fixture",
            "profile_topology": "custom",
            "subnet_cidr": "192.0.2.0/24",
        },
    ).json()
    base = "/api/v1/rack-plans/" + kit["id"]
    plan = client.put(
        base,
        json={
            "equipment": [
                {
                    "id": "server",
                    "name": "Fixture server",
                    "kind": "server",
                    "model": "HPE DL360",
                    "position": 1,
                    "height": 1,
                }
            ]
        },
    ).json()
    device = plan["equipment"][0]["device_id"]
    return base + "/" + request.param, device


def test_preview_is_persisted_blocked_and_not_hardware_evidence(client, guarded, db_session):
    base, device = guarded

    def url(action):
        return base + "/" + action + "?device_id=" + device

    assert client.get(url("status")).json()["status"] == "not_started"
    response = client.post(url("preview"), json={})
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview["can_apply"] is False
    assert preview["operations"] == []
    assert preview["evidence_at"] is None
    assert preview["target_provenance"] == "saved_plan"
    assert preview["blockers"]
    assert [d["text"] for d in preview["blocker_details"]] == preview["blockers"]
    assert all(d["fix"] and d["code"] for d in preview["blocker_details"])
    assert len(preview["review_token"]) == 64
    events = list(db_session.scalars(select(AuditEvent)))
    assert any(
        e.data_json.get("preview", {}).get("review_token") == preview["review_token"]
        for e in events
    )
    status = client.get(url("status")).json()
    assert status["status"] == "blocked"
    assert status["reviewed_at"]
    assert status["evidence_at"] is None
    assert status["operation_id"] is None
    assert status["execution_available"] is False
    assert [d["text"] for d in status["blocker_details"]] == status["blockers"]


def test_apply_cannot_bypass_blockers_and_does_not_reconcile(client, guarded):
    base, device = guarded

    def url(action):
        return base + "/" + action + "?device_id=" + device

    preview = client.post(url("preview"), json={}).json()
    body = {
        "review_token": preview["review_token"],
        "confirmation_phrase": "APPROVED",
        "idempotency_key": "fixture-attempt",
    }
    for _ in range(2):
        assert client.post(url("apply"), json=body).status_code == 409
    result = client.get(url("reconcile") + "&idempotency_key=fixture-attempt").json()
    assert result["status"] == "uncertain"
    assert result["record_found"] is False
    assert result["safe_to_retry"] is False
    assert result["idempotency_key"] is None
    assert result["requested_idempotency_key"] == "fixture-attempt"


def test_reconcile_missing_record_and_preview_cannot_clear_pending_send(client, guarded):
    base, device = guarded
    client.post(base + "/preview?device_id=" + device, json={})
    response = client.get(
        base + "/reconcile", params={"device_id": device, "idempotency_key": "lost-send"}
    )
    assert response.status_code == 200
    assert response.json()["safe_to_retry"] is False
    assert response.json()["operation_id"] is None


def test_scope_and_untrusted_commands_rejected(client, guarded):
    base, device = guarded
    for action in ("status", "reconcile"):
        assert (
            client.get(
                base + "/" + action, params={"device_id": "wrong", "idempotency_key": "x"}
            ).status_code
            == 404
        )
    assert (
        client.post(base + "/preview?device_id=" + device, json={"command": "anything"}).status_code
        == 422
    )
    assert (
        client.post(
            base + "/apply?device_id=" + device,
            json={
                "review_token": "x",
                "confirmation_phrase": "x",
                "idempotency_key": "x",
                "command": "anything",
            },
        ).status_code
        == 422
    )


def test_reconcile_only_matches_recorded_scoped_attempt(client, guarded, db_session):
    from app.services.guarded_operation_ledger import reserve, claim_dispatch, mark_uncertain

    base, device = guarded
    profile_id, resource = base.split("/")[-2:]
    operation = reserve(
        db_session,
        profile_id=profile_id,
        device_id=device,
        resource=resource,
        idempotency_key="recorded-attempt",
        reviewed_intent={"fixture": True},
        actor="offline-test",
    )
    assert claim_dispatch(db_session, operation.id, actor="offline-worker")
    assert mark_uncertain(db_session, operation.id, actor="offline-worker")
    params = {"device_id": device, "idempotency_key": "recorded-attempt"}
    result = client.get(base + "/reconcile", params=params).json()
    assert result["record_found"] is True
    assert result["operation_id"] == operation.id
    assert result["idempotency_key"] == "recorded-attempt"
    assert result["status"] == "uncertain"
    assert result["safe_to_retry"] is False
    assert result["evidence_at"] is None
    assert (
        client.get(base + "/status", params={"device_id": device}).json()["operation_id"]
        == operation.id
    )
    params["idempotency_key"] = "new-lost-send"
    missing = client.get(base + "/reconcile", params=params).json()
    assert missing["record_found"] is False
    assert missing["idempotency_key"] is None
    assert missing["safe_to_retry"] is False
    other = "drive-return-to-service" if resource == "firmware-execution" else "firmware-execution"
    wrong_resource = client.get(
        base.rsplit("/", 1)[0] + "/" + other + "/reconcile",
        params={"device_id": device, "idempotency_key": "recorded-attempt"},
    ).json()
    assert wrong_resource["record_found"] is False
