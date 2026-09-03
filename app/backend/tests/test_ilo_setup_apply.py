from __future__ import annotations

import types

from app.providers.action_policy import ActionCategory
from app.providers.ilo_redfish import IloRedfishConfig
from app.services import ilo_setup_apply


def test_environment_gate_blockers_dedupes_preserving_first_seen_order(monkeypatch) -> None:
    fake_settings = types.SimpleNamespace(
        provider_mode="local-lab-readwrite",
        ilo_setup_apply_enabled=False,
        lab_apply_ack="NO",
        lab_target_ack="wrong-host",
    )

    class DuplicatePolicy:
        def action_blockers(self, action_id: str, category: ActionCategory) -> list[str]:
            assert action_id == "ilo-redfish.manager-network-protocol-hostname"
            assert category == ActionCategory.NETWORK_CONFIG
            return [
                "policy blocker",
                "ILO_SETUP_APPLY_ENABLED=true is required for guarded iLO setup apply.",
                "policy blocker",
            ]

    monkeypatch.setattr(ilo_setup_apply, "settings", fake_settings)
    monkeypatch.setattr(ilo_setup_apply, "current_lab_action_policy", lambda mode: DuplicatePolicy())
    config = IloRedfishConfig(
        host="ilo.lab.local",
        username="local-admin",
        password="local-password",
        verify_tls=False,
        timeout_seconds=3.0,
    )

    blockers = ilo_setup_apply._environment_gate_blockers(
        config,
        confirmation_phrase="wrong phrase",
    )

    assert blockers == [
        "policy blocker",
        "ILO_SETUP_APPLY_ENABLED=true is required for guarded iLO setup apply.",
        "LAB_APPLY_ACK=YES is required for guarded iLO setup apply.",
        "LAB_TARGET_ACK must match the configured ILO_TEST_HOST value.",
        f"Exact confirmation phrase is required: {ilo_setup_apply.CONFIRMATION_PHRASE}",
    ]


def test_environment_gate_blockers_keep_scalar_policy_blocker_whole(monkeypatch) -> None:
    fake_settings = types.SimpleNamespace(
        provider_mode="local-lab-readwrite",
        ilo_setup_apply_enabled=True,
        lab_apply_ack="YES",
        lab_target_ack="ilo.lab.local",
    )

    class ScalarPolicy:
        def action_blockers(self, action_id: str, category: ActionCategory) -> str:
            assert action_id == "ilo-redfish.manager-network-protocol-hostname"
            assert category == ActionCategory.NETWORK_CONFIG
            return " policy blocker "

    monkeypatch.setattr(ilo_setup_apply, "settings", fake_settings)
    monkeypatch.setattr(ilo_setup_apply, "current_lab_action_policy", lambda mode: ScalarPolicy())
    config = IloRedfishConfig(
        host="ilo.lab.local",
        username="local-admin",
        password="local-password",
        verify_tls=False,
        timeout_seconds=3.0,
    )

    blockers = ilo_setup_apply._environment_gate_blockers(
        config,
        confirmation_phrase=ilo_setup_apply.CONFIRMATION_PHRASE,
    )

    assert blockers == ["policy blocker"]
    assert "p" not in blockers
