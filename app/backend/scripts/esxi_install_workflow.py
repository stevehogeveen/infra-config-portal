from __future__ import annotations

import json

from app.core.database import SessionLocal
from app.providers.redaction import redact_sensitive
from app.core.config import settings
from app.services.esxi_install_readiness import (
    ESXI_INSTALL_READINESS_REPORT,
    REPO_ROOT,
    get_esxi_install_readiness,
)


def main() -> int:
    with SessionLocal() as session:
        result = get_esxi_install_readiness(session)
    print(json.dumps(_summary(result), indent=2))
    print(f"esxi_install_readiness_report={ESXI_INSTALL_READINESS_REPORT.relative_to(REPO_ROOT)}")
    return 0 if result.get("status") == "ready" else 1


def _summary(result: dict) -> dict:
    return redact_sensitive(
        {
            "checked_at": result.get("checked_at"),
            "status": result.get("status"),
            "message": result.get("message"),
            "raid_validation": result.get("raid_validation"),
            "virtual_media_supported": (result.get("virtual_media") or {}).get("supported"),
            "one_time_boot_supported": (result.get("boot_control") or {}).get("one_time_boot_supported"),
            "iso_ready": (result.get("iso") or {}).get("ready"),
            "blockers": result.get("blockers") or [],
            "report": str(ESXI_INSTALL_READINESS_REPORT.relative_to(REPO_ROOT)),
        },
        [settings.ilo_test_host, settings.ilo_test_username, settings.ilo_test_password],
    )


if __name__ == "__main__":
    raise SystemExit(main())
