from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_LAB_ENV = REPO_ROOT / ".env.local.real-lab"

if REAL_LAB_ENV.exists():
    for key, value in dotenv_values(REAL_LAB_ENV).items():
        if value is None or key in os.environ:
            continue
        os.environ[key] = value

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
