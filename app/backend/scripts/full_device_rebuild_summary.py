from __future__ import annotations

import json

from app.services.full_rebuild_run import build_full_rebuild_summary_reports


def main() -> int:
    result = build_full_rebuild_summary_reports()
    print(json.dumps(_summary(result), indent=2))
    return 0


def _summary(result: dict) -> dict:
    return {
        "checked_at": result.get("checked_at"),
        "status": result.get("status"),
        "provider_mode": result.get("provider_mode"),
        "mock_results_used": result.get("mock_results_used"),
        "message": result.get("message"),
        "artifacts": result.get("artifacts") or {},
    }


if __name__ == "__main__":
    raise SystemExit(main())
