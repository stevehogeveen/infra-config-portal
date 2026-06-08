from __future__ import annotations

import json

from app.services.full_rebuild_run import run_full_rebuild_execution


def main() -> int:
    result = run_full_rebuild_execution()
    print(json.dumps(_summary(result), indent=2))
    return 0 if result.get("status") in {"completed", "blocked"} else 1


def _summary(result: dict) -> dict:
    return {
        "checked_at": result.get("checked_at"),
        "status": result.get("status"),
        "provider_mode": result.get("provider_mode"),
        "mock_results_used": result.get("mock_results_used"),
        "stage_statuses": {
            key: value.get("status")
            for key, value in (result.get("stages") or {}).items()
            if isinstance(value, dict)
        },
        "blockers": result.get("blockers") or [],
        "artifacts": result.get("artifacts") or {},
    }


if __name__ == "__main__":
    raise SystemExit(main())
