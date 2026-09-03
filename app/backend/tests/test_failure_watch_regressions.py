from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.services.ai_change_requests import _append_agent_chat_notice


def test_ai_change_request_mailbox_redacts_sensitive_operator_text(tmp_path) -> None:
    payload = SimpleNamespace(
        page="overview",
        route="/overview",
        target="hostname=customer-switch-01",
        request=(
            "password=supersecret token=abc123 customer=Acme "
            "admin@example.test 192.0.2.25"
        ),
    )

    _append_agent_chat_notice(
        tmp_path,
        payload,
        "20260716T112000Z",
        datetime(2026, 7, 16, 11, 20, tzinfo=UTC),
        "docs/change-requests/20260716T112000Z-overview.md",
    )

    mailbox = (tmp_path / "docs" / "agent-chat.md").read_text(encoding="utf-8")
    assert "supersecret" not in mailbox
    assert "abc123" not in mailbox
    assert "customer-switch-01" not in mailbox
    assert "Acme" not in mailbox
    assert "admin@example.test" not in mailbox
    assert "192.0.2.25" not in mailbox
    assert "password=REDACTED" in mailbox
    assert "token=REDACTED" in mailbox
    assert "hostname=REDACTED" in mailbox
    assert "customer=REDACTED" in mailbox
    assert "REDACTED_EMAIL" in mailbox
    assert "REDACTED_IP" in mailbox
