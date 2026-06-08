from __future__ import annotations

import argparse
import json

from app.providers.redaction import redact_sensitive
from app.core.config import settings
from app.services.esxi_boot_workflow import (
    detect_esxi_installer_boot_status,
    eject_esxi_virtual_media,
    insert_esxi_virtual_media,
    prepare_esxi_media_url,
    reset_for_esxi_installer_boot,
    set_esxi_one_time_boot,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run controlled real-lab ESXi boot workflow stages.")
    parser.add_argument(
        "stage",
        choices=(
            "media-url",
            "insert-virtual-media",
            "eject-virtual-media",
            "one-time-boot",
            "reset-installer-boot",
            "detect-installer",
        ),
    )
    args = parser.parse_args()

    result = {
        "media-url": prepare_esxi_media_url,
        "insert-virtual-media": insert_esxi_virtual_media,
        "eject-virtual-media": eject_esxi_virtual_media,
        "one-time-boot": set_esxi_one_time_boot,
        "reset-installer-boot": reset_for_esxi_installer_boot,
        "detect-installer": detect_esxi_installer_boot_status,
    }[args.stage]()
    print(json.dumps(_summary(result), indent=2))
    return 0 if result.get("status") not in {"blocked", "failed"} else 1


def _summary(result: dict) -> dict:
    return redact_sensitive(
        {
            "checked_at": result.get("checked_at"),
            "status": result.get("status"),
            "message": result.get("message"),
            "selected_iso": result.get("selected_iso"),
            "media_url": result.get("media_url"),
            "inserted": result.get("inserted"),
            "ejected": result.get("ejected"),
            "target": result.get("target"),
            "installer_detection": result.get("installer_detection"),
            "blockers": result.get("blockers") or [],
            "warnings": result.get("warnings") or [],
            "report": result.get("report"),
        },
        [settings.ilo_test_host, settings.ilo_test_username, settings.ilo_test_password],
    )


if __name__ == "__main__":
    raise SystemExit(main())
