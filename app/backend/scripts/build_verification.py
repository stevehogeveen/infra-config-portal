from __future__ import annotations

import json

from app.services.build_verification import build_lab_build_verification


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
