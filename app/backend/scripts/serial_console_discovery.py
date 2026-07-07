from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
REAL_LAB_ENV = REPO_ROOT / ".env.local.real-lab"
REPORT = REPO_ROOT / "artifacts" / "codex-runs" / "serial-console-discovery-report.md"
JSON_REPORT = REPO_ROOT / "artifacts" / "codex-runs" / "serial-console-discovery-redacted.json"

from app.services.env_utils import load_real_lab_env  # noqa: E402

load_real_lab_env(REPO_ROOT)

from app.core.config import settings  # noqa: E402
from app.providers.action_policy import REAL_CONTACT_MODES, current_lab_action_policy  # noqa: E402
from app.providers.redaction import redact_sensitive  # noqa: E402
from app.services.json_file_store import write_json_object, write_text_value  # noqa: E402
from app.services.path_utils import display_path  # noqa: E402
from app.services.serial_console_discovery import (  # noqa: E402
    SerialConsoleProbeOptions,
    discover_serial_console_candidates,
    probe_serial_candidates,
    selectable_serial_candidates,
    serial_baud_order,
)


def main() -> int:
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    configured_hint = _configured_hint()
    configured_baud = _configured_baud(configured_hint)
    candidates = discover_serial_console_candidates(
        configured_hint=configured_hint,
        collect_details=True,
    )
    policy = current_lab_action_policy(settings.provider_mode)
    blockers = policy.readonly_blockers() if settings.provider_mode in REAL_CONTACT_MODES else [
        "PROVIDER_MODE=local-readonly or PROVIDER_MODE=local-lab-readwrite is required before opening real serial consoles."
    ]
    warnings = [
        "Probe mode sends newline, carriage return, and Ctrl+C only.",
        "No credentials, show commands, configuration commands, boot menu selections, or apply actions are sent.",
    ]
    attempts: list[dict[str, Any]] = []
    selected = _best_ranked_candidate(candidates)
    serial_import_error: str | None = None

    if not blockers:
        try:
            import serial  # type: ignore[import-untyped]
        except ImportError:
            serial_import_error = "pyserial is not installed; serial probe could not open candidates."
            blockers.append(serial_import_error)
        else:
            probe_result = probe_serial_candidates(
                serial,
                candidates,
                options=SerialConsoleProbeOptions(
                    configured_baud=configured_baud,
                    timeout_seconds=max(settings.netapp_console_timeout_seconds, settings.cisco_console_timeout_seconds),
                    max_candidates=1,
                ),
            )
            attempts = list(probe_result["attempts"])
            selected_attempt = probe_result.get("selected")
            if isinstance(selected_attempt, dict):
                selected = _candidate_for_attempt(candidates, selected_attempt) or selected

    selected_attempt = _selected_attempt(selected, attempts)
    status = "ready" if selected_attempt and selected_attempt.get("device_type") in {"cisco", "netapp"} else "blocked"
    if status == "blocked" and not blockers:
        blockers.append("Serial candidates were discovered, but no Cisco or NetApp console prompt was identified.")

    payload = {
        "provider_id": "serial-console",
        "action": "serial-console-discovery",
        "checked_at": datetime.now(UTC).isoformat(),
        "status": status,
        "mode": settings.provider_mode,
        "configured_port_hint": configured_hint,
        "configured_baud": configured_baud,
        "selected_port": (selected or {}).get("display_path") or (selected or {}).get("path"),
        "selected_baud": selected_attempt.get("baud") if selected_attempt else None,
        "selected_device_type": selected_attempt.get("device_type") if selected_attempt else None,
        "selected_classification": selected_attempt.get("classification") if selected_attempt else None,
        "selected_prompt_state": selected_attempt.get("prompt_state") if selected_attempt else None,
        "selection_confidence": (
            selected_attempt.get("confidence")
            if selected_attempt
            else (selected or {}).get("confidence")
        ),
        "selection_reason": _selection_reason(selected),
        "candidate_count": len(candidates),
        "candidate_counts": _candidate_counts(candidates),
        "candidates": candidates,
        "bauds_tried": list(serial_baud_order(configured_baud)),
        "attempt_count": len(attempts),
        "attempts": attempts,
        "serial_import_error": serial_import_error,
        "artifacts": {
            "report": _rel(REPORT),
            "json": _rel(JSON_REPORT),
        },
        "warnings": warnings,
        "blockers": blockers,
        "next_safe_action": (
            "Use the selected port and baud in the provider-specific Cisco or NetApp read-only workflow."
            if status == "ready"
            else "Check cable placement, adapter ownership, device permissions, power state, and baud, then rerun serial discovery."
        ),
    }
    sanitized = redact_sensitive(payload, _redaction_values())
    write_json_object(JSON_REPORT, sanitized)
    write_text_value(REPORT, _markdown(sanitized))
    print(json.dumps(_summary(sanitized), indent=2))
    return 0


def _configured_hint() -> str | None:
    return (
        os.getenv("SERIAL_CONSOLE_PORT")
        or settings.netapp_console_port
        or settings.cisco_console_port
    )


def _configured_baud(configured_hint: str | None) -> int | None:
    raw = os.getenv("SERIAL_CONSOLE_BAUD")
    if raw:
        try:
            return int(raw)
        except ValueError:
            return None
    if configured_hint and settings.cisco_console_port and configured_hint == settings.cisco_console_port:
        return settings.cisco_console_baud
    return settings.netapp_console_baud or settings.cisco_console_baud


def _best_ranked_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    selectable = selectable_serial_candidates(candidates)
    if selectable:
        return selectable[0]
    existing = [candidate for candidate in candidates if candidate.get("exists")]
    return existing[0] if existing else (candidates[0] if candidates else None)


def _candidate_for_attempt(
    candidates: list[dict[str, Any]],
    attempt: dict[str, Any],
) -> dict[str, Any] | None:
    path = attempt.get("path")
    return next(
        (
            candidate
            for candidate in candidates
            if candidate.get("display_path") == path or candidate.get("path") == path
        ),
        None,
    )


def _selected_attempt(
    candidate: dict[str, Any] | None,
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not candidate:
        return None
    path = candidate.get("display_path") or candidate.get("path")
    matching = [attempt for attempt in attempts if attempt.get("path") == path]
    prompt_matches = [
        attempt
        for attempt in matching
        if attempt.get("device_type") in {"cisco", "netapp"}
        and attempt.get("classification") not in {"no_bytes_read", "unreadable_gibberish", "unknown"}
    ]
    return (prompt_matches or matching or [None])[0]


def _candidate_counts(candidates: list[dict[str, Any]]) -> dict[str, int]:
    existing = [candidate for candidate in candidates if candidate.get("exists")]
    return {
        "total": len(candidates),
        "existing": len(existing),
        "selectable": len(selectable_serial_candidates(candidates)),
        "stable_existing": len([candidate for candidate in existing if candidate.get("stable_path")]),
        "usb_existing": len(
            [
                candidate
                for candidate in existing
                if candidate.get("path_type") in {"by-id", "ttyUSB", "ttyACM"}
            ]
        ),
        "ttys_existing": len([candidate for candidate in existing if candidate.get("path_type") == "ttyS"]),
        "in_use": len([candidate for candidate in existing if candidate.get("in_use")]),
        "inaccessible": len(
            [
                candidate
                for candidate in existing
                if not candidate.get("readable") or not candidate.get("writable")
            ]
        ),
    }


def _selection_reason(candidate: dict[str, Any] | None) -> str | None:
    if not candidate:
        return None
    reasons = candidate.get("selection_reasons")
    if isinstance(reasons, list) and reasons:
        return "; ".join(str(reason) for reason in reasons)
    return str(candidate.get("recommendation") or "")


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Serial Console Discovery",
        "",
        f"Checked at: {payload['checked_at']}",
        f"Status: `{payload['status']}`",
        f"Provider mode: `{payload['mode']}`",
        "",
        "## Selection",
        f"- Configured port hint: `{payload.get('configured_port_hint') or 'not set'}`",
        f"- Selected port: `{payload.get('selected_port') or 'none'}`",
        f"- Selected baud: `{payload.get('selected_baud') or 'none'}`",
        f"- Selected device type: `{payload.get('selected_device_type') or 'unknown'}`",
        f"- Selected classification: `{payload.get('selected_classification') or 'none'}`",
        f"- Selection confidence: `{payload.get('selection_confidence') or 'none'}`",
        f"- Selection reason: {payload.get('selection_reason') or 'none'}",
        f"- Candidate count: `{payload.get('candidate_count') or 0}`",
        "",
        "## Candidates",
    ]
    for candidate in payload.get("candidates", [])[:60]:
        if not isinstance(candidate, dict):
            continue
        lines.append(
            "- "
            f"`{candidate.get('display_path') or candidate.get('path')}` | "
            f"type=`{candidate.get('path_type')}` | exists=`{candidate.get('exists')}` | "
            f"rw=`{candidate.get('readable')}/{candidate.get('writable')}` | "
            f"in_use=`{candidate.get('in_use')}` | rank=`{candidate.get('rank')}` | "
            f"confidence=`{candidate.get('confidence')}`"
        )
    if not payload.get("candidates"):
        lines.append("- none")
    lines.extend(["", "## Attempts"])
    attempts = payload.get("attempts") or []
    for attempt in attempts[:80]:
        if not isinstance(attempt, dict):
            continue
        lines.append(
            "- "
            f"`{attempt.get('path')}` @ `{attempt.get('baud')}`: "
            f"{attempt.get('device_type')}/{attempt.get('classification')} "
            f"prompt=`{attempt.get('prompt_state')}` bytes=`{attempt.get('bytes')}`"
        )
    if not attempts:
        lines.append("- No serial open/read attempts were made.")
    lines.extend(["", "## Blockers"])
    lines.extend(f"- {item}" for item in payload.get("blockers", []) or ["None"])
    lines.extend(["", "## Warnings"])
    lines.extend(f"- {item}" for item in payload.get("warnings", []) or ["None"])
    lines.append("")
    return "\n".join(lines)


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider_id": payload.get("provider_id"),
        "action": payload.get("action"),
        "checked_at": payload.get("checked_at"),
        "status": payload.get("status"),
        "selected_port": payload.get("selected_port"),
        "selected_baud": payload.get("selected_baud"),
        "selected_device_type": payload.get("selected_device_type"),
        "selected_classification": payload.get("selected_classification"),
        "candidate_count": payload.get("candidate_count"),
        "blockers": payload.get("blockers") or [],
        "warnings": payload.get("warnings") or [],
        "artifacts": payload.get("artifacts") or {},
        "no_config_commands_sent": True,
    }


def _redaction_values() -> list[str]:
    values: list[str] = []
    for key, value in os.environ.items():
        if not value:
            continue
        lowered = key.lower()
        if any(fragment in lowered for fragment in ("password", "token", "secret", "credential", "authorization", "cookie")):
            values.append(value)
    return values


def _rel(path: Path) -> str:
    return display_path(path, REPO_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
