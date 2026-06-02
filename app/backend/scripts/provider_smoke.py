from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

from app.core.config import settings
from app.providers.cisco_console import CiscoConsoleAdapter
from app.providers.ilo_redfish import IloRedfishAdapter
from app.providers.redaction import redact_sensitive
from app.providers.registry import ProviderRegistryError, provider_registry


def main() -> int:
    print(f"provider_mode={settings.provider_mode}")
    try:
        statuses = provider_registry().statuses()
    except ProviderRegistryError as exc:
        print(f"provider_status=blocked message={exc}")
        return 0

    status_payload = [_status_summary(_to_dict(status)) for status in statuses]
    print(json.dumps(redact_sensitive({"providers": status_payload}), indent=2))

    cisco_status = next((item for item in status_payload if item["id"] == "cisco-console"), None)
    if cisco_status:
        discovery = cisco_status.get("discovery") or {}
        print(
            json.dumps(
                {
                    "cisco_console_discovery": {
                        "status": discovery.get("status"),
                        "effective_path": discovery.get("effective_path"),
                        "candidate_count": len(discovery.get("candidates", [])),
                        "candidates": discovery.get("candidates", []),
                    }
                },
                indent=2,
            )
        )

    if settings.provider_mode != "local-readonly":
        print("probes=skipped reason=PROVIDER_MODE is not local-readonly")
        return 0

    _run_optional_probe("ilo-redfish", IloRedfishAdapter())
    _run_optional_probe("cisco-console", CiscoConsoleAdapter())
    return 0


def _run_optional_probe(provider_id: str, adapter: Any) -> None:
    status = adapter.health()
    enabled_actions = [action for action in status.safe_actions if action.enabled]
    if not enabled_actions:
        print(f"{provider_id}_probe=skipped reason=no enabled read-only action")
        return

    try:
        result = adapter.probe()
    except Exception as exc:
        print(f"{provider_id}_probe=skipped reason={exc}")
        return

    summary = {
        key: value
        for key, value in result.items()
        if key in {"provider_id", "status", "message", "warnings", "blockers", "checked_at"}
    }
    print(json.dumps(redact_sensitive(summary), indent=2))


def _status_summary(status: dict[str, Any]) -> dict[str, Any]:
    configuration = status.get("configuration") or {}
    if status.get("id") == "ilo-redfish":
        configuration = {
            "host_configured": bool(configuration.get("host")),
            "username_configured": bool(configuration.get("username")),
            "password_configured": bool(configuration.get("password_configured")),
            "tls_verify": configuration.get("tls_verify"),
            "missing_fields": configuration.get("missing_fields", []),
        }

    return {
        "id": status.get("id"),
        "name": status.get("name"),
        "mode": status.get("mode"),
        "status": status.get("status"),
        "configuration": configuration,
        "discovery": status.get("discovery"),
        "blockers": status.get("blockers", []),
        "warnings": status.get("warnings", []),
        "safe_actions": status.get("safe_actions", []),
        "disabled_actions": status.get("disabled_actions", []),
    }


def _to_dict(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return value
    return dict(value)


if __name__ == "__main__":
    raise SystemExit(main())
