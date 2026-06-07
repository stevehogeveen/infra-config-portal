from __future__ import annotations

import json

from app.services.build_verification import build_toolchain_availability


def main() -> int:
    result = build_toolchain_availability()
    print(json.dumps(_summary(result), indent=2))
    return 0 if result.get("status") in {"ready", "warning"} else 1


def _summary(result: dict) -> dict:
    return {
        "checked_at": result.get("checked_at"),
        "status": result.get("status"),
        "required_missing": result.get("required_missing") or [],
        "optional_missing": result.get("optional_missing") or [],
        "artifacts": result.get("artifacts") or {},
    }


if __name__ == "__main__":
    raise SystemExit(main())
