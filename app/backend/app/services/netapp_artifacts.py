from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.providers.netapp import PROVIDER_ID


PLAN_PREVIEW_ENDPOINT = "/api/v1/providers/netapp-ontap/plan-preview"


def list_netapp_artifact_placeholders() -> list[dict[str, Any]]:
    generated_at = datetime.now(UTC)
    return [
        {
            "id": f"{PROVIDER_ID}:plan-preview-placeholder",
            "provider_id": PROVIDER_ID,
            "kind": "netapp_plan_preview",
            "title": "NetApp ONTAP Plan Preview",
            "description": (
                "Mock-only metadata placeholder for the NetApp ONTAP plan preview. "
                "No report file is written and no ONTAP endpoint is contacted."
            ),
            "status": "available_preview",
            "mock_only": True,
            "redacted": True,
            "downloadable": False,
            "download_url": None,
            "generated_at": generated_at,
            "metadata": {
                "source_endpoint": PLAN_PREVIEW_ENDPOINT,
                "apply_enabled": False,
                "includes_planned_targets": True,
                "includes_readiness": True,
                "includes_intent_preview": True,
                "includes_disabled_actions": True,
                "no_ontap_calls": True,
            },
        }
    ]


def list_provider_artifact_placeholders() -> list[dict[str, Any]]:
    return [
        *list_netapp_artifact_placeholders(),
    ]
