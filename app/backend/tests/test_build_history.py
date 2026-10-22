from app.services.audit import record_audit_event


def test_history_keeps_results_and_drops_polling_noise(client, db_session):
    for event_type, message, data in (
        ("spp.offline.observation", "Still waiting.", {}),
        ("kit.raid_rebuild.preview", "Preview only.", {}),
        ("kit.windows.result", "windows01 was imported.", {"outcome": "ok"}),
        ("kit.raid_rebuild.failed", "The RAID create was not confirmed.", {}),
        ("runtime.write_scope.applied", "Changed write permissions.", {}),
    ):
        record_audit_event(db_session, actor="op", event_type=event_type, message=message, data=data)
    db_session.commit()
    rows = client.get("/api/v1/build-history").json()
    assert {row["message"] for row in rows} == {"Changed write permissions.", "The RAID create was not confirmed.", "windows01 was imported."}
    by_message = {row["message"]: row for row in rows}
    assert by_message["windows01 was imported."]["outcome"] == "ok" and by_message["windows01 was imported."]["area"] == "Windows"
    assert by_message["The RAID create was not confirmed."]["outcome"] == "failed"
    assert all(row["at"].endswith("+00:00") for row in rows)


def test_a_burst_of_polling_records_never_hides_older_results(client, db_session):
    record_audit_event(db_session, actor="op", event_type="kit.windows.result", message="An older result.", data={"outcome": "ok"})
    db_session.commit()
    for _ in range(2100):
        record_audit_event(db_session, actor="op", event_type="spp.offline.observation", message="Still waiting.", data={})
    db_session.commit()
    rows = client.get("/api/v1/build-history").json()
    assert [row["message"] for row in rows] == ["An older result."]
