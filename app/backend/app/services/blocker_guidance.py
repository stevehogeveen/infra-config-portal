"""Display-only guidance for legacy blocker strings. Never changes admission rules."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class BlockerDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    text: str
    fix_kind: Literal["app", "physical", "wait", "vendor"]
    fix: str
    action: Literal[
        "read_again",
        "prepare_again",
        "narrow_scope_firmware",
        "open_connection",
        "select_package",
        "check_status",
        "none",
    ] = "none"


# Match known messages at the compatibility boundary. Unknown messages remain
# visible with neutral guidance instead of inventing a repair from arbitrary text.
RULES = (
    (
        "ilo_health_unknown",
        (
            "the ilo did not report",
            "exactly one ilo must answer",
        ),
        "app",
        "Read the iLO again. If its health remains unknown, inspect iLO Diagnostics.",
        "read_again",
    ),
    (
        "ilo_health_reported",
        ("the ilo reports its own health", "the ilo reports its state", "ilo self-test "),
        "vendor",
        "Open iLO Information > Diagnostics and inspect the reported self-test. Use the HPE-documented recovery for that result; approval alone does not clear it.",
        "read_again",
    ),
    (
        "psu_no_input",
        ("at least one enabled healthy power supply",),
        "physical",
        "Connect at least one healthy power supply to a working outlet and keep that feed connected throughout the update.",
        "read_again",
    ),
    (
        "psu_fault",
        ("an energized power supply", "a power supply has unknown input"),
        "physical",
        "Check the power supply and input power identified by iLO. Resolve the reported fault using the server's service instructions, then read again.",
        "read_again",
    ),
    (
        "cooling_fault",
        ("cooling or temperature sensor reports",),
        "physical",
        "Inspect the fan or temperature sensor reported by iLO and resolve its fault before updating.",
        "read_again",
    ),
    (
        "thermal_incomplete",
        (
            "fresh cooling and temperature",
            "present cooling and temperature",
            "run a fresh ilo-specific",
        ),
        "app",
        "Read the iLO again to collect complete cooling, temperature and controller health evidence.",
        "read_again",
    ),
    (
        "storage_operation_active",
        ("a storage operation is active",),
        "wait",
        "Wait for the existing disk operation to finish and verify its recorded status. Do not start another erase.",
        "check_status",
    ),
    (
        "operation_unresolved",
        (
            "an unresolved operation",
            "resolve ",
        ),
        "wait",
        "Check and reconcile the existing operation before starting another change. Do not resend an uncertain request.",
        "check_status",
    ),
    (
        "critical_health",
        ("critical server or chassis health",),
        "physical",
        "Open the iLO Integrated Management Log, identify the critical item and resolve it before reading again.",
        "read_again",
    ),
    (
        "scope_not_firmware",
        ("exclusive firmware maintenance scope",),
        "app",
        "Review and allow only iLO firmware changes. Reading the server remains available.",
        "narrow_scope_firmware",
    ),
    (
        "capabilities_stale",
        (
            "a fresh explicit firmware",
            "run the explicitly confirmed",
            "recorded preparation evidence",
            "fresh authenticated idle ilo",
            "read this server again",
        ),
        "app",
        "Prepare the update again to refresh the exact server's capabilities and review.",
        "prepare_again",
    ),
    (
        "package_missing",
        (
            "select the spp",
            "selected iso is missing",
            "selected iso changed",
            "selected spp does not establish",
            "the selected spp does not establish",
        ),
        "app",
        "Choose the SPP for this server generation again and prepare a new review.",
        "select_package",
    ),
    (
        "signed_target_mismatch",
        ("hpe's signed file", "signed firmware targets"),
        "vendor",
        "Check the selected package against the server and iLO generation. Select a matching HPE package; if its signed target remains ambiguous, obtain HPE guidance.",
        "select_package",
    ),
    (
        "connection_missing",
        (
            "save the ilo",
            "ilo connection settings",
            "no saved ilo",
        ),
        "app",
        "Save the exact server's iLO address and sign-in, then read again.",
        "open_connection",
    ),
    (
        "review_expired",
        ("firmware review expired", "this review has expired", "review expired"),
        "app",
        "Open a new review and confirm the current plan.",
        "prepare_again",
    ),
    (
        "inventory_version_mismatch",
        ("the ilo's firmware list",),
        "app",
        "Read the iLO again and compare the manager and firmware inventory versions before preparing another update.",
        "read_again",
    ),
    (
        "update_not_available",
        ("the ilo reports that its firmware can't", "the ilo reported an invalid updateable"),
        "app",
        "Read the iLO again. If the update remains unavailable, inspect its update service and Diagnostics before proceeding.",
        "read_again",
    ),
    (
        "recovery_not_supported",
        (
            "return-to-service support",
            "an identity-verified maintenance",
            "erasecompleted is not proof",
        ),
        "vendor",
        "A supported recovery method for this controller and firmware must be established. Do not repeat sanitization or clear the warning by creating RAID.",
        "none",
    ),
)


def describe_blockers(blockers: list[str]) -> list[dict]:
    result = []
    for text in blockers:
        normalized = text.casefold().strip()
        match = next((r for r in RULES if normalized.startswith(r[1])), None)
        if match:
            code, _, kind, fix, action = match
        else:
            code, kind, action = "review_required", "vendor", "none"
            fix = "Inspect the reported prerequisite and technical details. A supported resolution is required; this message does not authorize a hardware change."
        result.append(
            BlockerDetail(code=code, text=text, fix_kind=kind, fix=fix, action=action).model_dump()
        )
    return result


def with_blocker_details(result: dict) -> dict:
    return {**result, "blocker_details": describe_blockers(result.get("blockers") or [])}
