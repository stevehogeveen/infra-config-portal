"""Conservative classification of a completed, rejected storage request."""
from datetime import UTC, datetime


def confirmed_rejection(snapshot, attempt, boot_started_at):
    if (attempt.get("operation") not in {"clear", "reset"} or not boot_started_at
            or snapshot["identity"] != attempt.get("identity")
            or snapshot["pending_differs"]):
        return None
    settings = snapshot["current"].get("@Redfish.Settings") or {}
    messages = settings.get("Messages") or []
    codes = [m.get("MessageId", "") for m in messages if isinstance(m, dict)]
    rejection = "SmartStorageMessages.2.0.1.CanCreateEditableConfigControllerStatusNotOK"
    if attempt.get("operation") == "reset":
        rejection = "SmartStorageMessages.2.0.1.PropertyKeyMissing"
        if not any(m.get("MessageId") == rejection and m.get("MessageArgs") == ["LogicalDrives"]
                   for m in messages if isinstance(m, dict)):
            return None
    if len(codes) != len(messages) or rejection not in codes or any(not isinstance(c, str) or (c != rejection and not c.endswith(".Success")) for c in codes):
        return None
    try:
        reported = datetime.fromisoformat(settings.get("Time", "").replace("Z", "+00:00"))
        if reported.tzinfo is None:
            return None
        started = boot_started_at.replace(tzinfo=UTC) if boot_started_at.tzinfo is None else boot_started_at
        if not started < reported <= datetime.now(UTC):
            return None
    except (TypeError, ValueError, AttributeError):
        return None
    return {"codes": codes, "reported_at": reported.isoformat(),
            "message": ("HPE rejected the controller reset: the request was missing LogicalDrives. No pending settings remain. The reset is not verified and no replacement arrays were created. Do not repeat the same request; review controller recovery."
                        if attempt.get("operation") == "reset" else
                        "HPE rejected the deletion because controller status was not OK. No pending settings remain. Do not repeat the same deletion; review controller recovery.")}
