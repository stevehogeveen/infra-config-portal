from __future__ import annotations

from typing import Any

from app.services.netapp_upgrade_center import get_legacy_upgrade_readiness


def get_netapp_upgrade_readiness() -> dict[str, Any]:
    return get_legacy_upgrade_readiness()
