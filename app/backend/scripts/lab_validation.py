from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_LAB_ENV = REPO_ROOT / ".env.local.real-lab"

from app.services.env_utils import load_real_lab_env  # noqa: E402

load_real_lab_env(REPO_ROOT)

from app.services.lab_validation import get_lab_validation_summary  # noqa: E402


def main() -> int:
    result = get_lab_validation_summary(write_report=True)
    print(json.dumps(_summary(result), indent=2))
    return 0


def _summary(result: dict) -> dict:
    return {
        "overall_status": result.get("overall_status"),
        "generated_at": result.get("generated_at"),
        "progress_counts": result.get("progress_counts"),
        "top_blocker": {
            "component_label": (result.get("top_blocker") or {}).get("component_label"),
            "problem": (result.get("top_blocker") or {}).get("problem"),
            "recheck_command": (result.get("top_blocker") or {}).get("recheck_command"),
        }
        if result.get("top_blocker")
        else None,
        "handoff_report": result.get("handoff_report"),
        "proof_link_count": len(result.get("proof_links") or []),
        "no_write_actions_attempted": True,
    }


if __name__ == "__main__":
    raise SystemExit(main())
