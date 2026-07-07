from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_LAB_ENV = REPO_ROOT / ".env.local.real-lab"

from app.services.env_utils import load_real_lab_env  # noqa: E402

load_real_lab_env(REPO_ROOT)

from app.services.build_verification import build_lab_build_verification  # noqa: E402


def main() -> int:
    result = build_lab_build_verification()
    print(json.dumps(_summary(result), indent=2))
    return 0 if result.get("status") in {"completed", "warning"} else 1


def _summary(result: dict) -> dict:
    return {
        "checked_at": result.get("checked_at"),
        "status": result.get("status"),
        "blockers": result.get("blockers") or [],
        "warnings": result.get("warnings") or [],
        "artifacts": result.get("artifacts") or {},
    }


if __name__ == "__main__":
    raise SystemExit(main())
