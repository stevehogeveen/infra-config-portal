from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_LAB_ENV = REPO_ROOT / ".env.local.real-lab"

from app.services.env_utils import load_real_lab_env  # noqa: E402

load_real_lab_env(REPO_ROOT)

from app.services.golden_state import get_provider_lab_golden_state  # noqa: E402


def main() -> int:
    result = get_provider_lab_golden_state(write_report=True)
    print(json.dumps(_summary(result), indent=2))
    return 0


def _summary(result: dict) -> dict:
    return {
        "checked_at": result.get("checked_at"),
        "status": result.get("status"),
        "blockers": result.get("blockers"),
        "drift_count": len(result.get("drift_rows") or []),
        "report": (result.get("artifacts") or {}).get("report"),
        "summary_json": (result.get("artifacts") or {}).get("summary_json"),
        "no_write_actions_attempted": True,
    }


if __name__ == "__main__":
    raise SystemExit(main())
