from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def test_ai_change_request_redacts_sensitive_text_from_artifact_and_mailbox(
    client: TestClient,
) -> None:
    mailbox = Path(__file__).resolve().parents[2] / "docs" / "agent-chat.md"
    original_mailbox = mailbox.read_text(encoding="utf-8") if mailbox.exists() else ""
    response = client.post(
        "/api/v1/ai-change-requests",
        json={
            "page": "Network customer=TEST_ONLY_CUSTOMER",
            "route": "/network?ip_address=192.0.2.44",
            "request": (
                "The check failed with password=TEST_ONLY_PASSWORD for "
                "admin-test@example.invalid on 192.0.2.44"
            ),
            "target": "hostname=TEST_ONLY_HOST",
            "regions": [
                {
                    "id": "network-details",
                    "label": "customer=TEST_ONLY_CUSTOMER",
                    "kind": "drawer",
                }
            ],
            "current_layout": {
                "network-details": {"visible": True, "collapsed": True, "order": 0},
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    artifact = Path(__file__).resolve().parents[2] / payload["artifact"]
    try:
        artifact_text = artifact.read_text(encoding="utf-8")
        mailbox_delta = mailbox.read_text(encoding="utf-8")[len(original_mailbox) :]
        persisted = f"{artifact_text}\n{mailbox_delta}"

        for sensitive_value in (
            "TEST_ONLY_CUSTOMER",
            "TEST_ONLY_PASSWORD",
            "TEST_ONLY_HOST",
            "admin-test@example.invalid",
            "192.0.2.44",
        ):
            assert sensitive_value not in persisted

        assert "REDACTED" in artifact_text
        assert "REDACTED" in mailbox_delta
        assert "capture-only" in artifact_text
        assert "no workflow ran" in mailbox_delta
    finally:
        artifact.unlink(missing_ok=True)
        mailbox.write_text(original_mailbox, encoding="utf-8")
