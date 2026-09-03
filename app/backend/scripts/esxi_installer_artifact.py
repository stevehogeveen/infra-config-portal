from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.esxi_installer_artifact import (
    REPORT_MARKDOWN,
    prepare_esxi_installer_artifact,
)
from app.services.json_utils import parse_json_object
from app.services.path_utils import display_path

REPO_ROOT = Path(__file__).resolve().parents[3]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Derive a profile-bound ESXi Kickstart ISO offline. "
            "This command never contacts hardware."
        )
    )
    parser.add_argument(
        "request",
        type=Path,
        help="Path to a local ignored JSON request that follows esxi-installer-artifact-v1.",
    )
    arguments = parser.parse_args()
    payload = _read_request(arguments.request)
    result = prepare_esxi_installer_artifact(payload)
    print(json.dumps(_summary(result), indent=2, sort_keys=True))
    print(f"esxi_installer_artifact_report={display_path(REPORT_MARKDOWN, REPO_ROOT)}")
    return 0 if result.get("status") == "ready" else 1


def _read_request(path: Path) -> dict:
    try:
        raw = path.read_bytes()
    except OSError:
        return {}
    return parse_json_object(raw)


def _summary(result: dict) -> dict:
    artifact = result.get("derived_artifact")
    artifact = artifact if isinstance(artifact, dict) else {}
    return {
        "status": result.get("status"),
        "failure_code": result.get("failure_code"),
        "message": result.get("message"),
        "hardware_contacted": result.get("hardware_contacted"),
        "source_iso_write_attempted": result.get("source_iso_write_attempted"),
        "blockers": result.get("blockers") or [],
        "derived_iso": artifact.get("iso"),
        "derived_iso_sha256": artifact.get("iso_sha256"),
        "manifest": artifact.get("manifest"),
        "next_safe_action": result.get("next_safe_action"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
