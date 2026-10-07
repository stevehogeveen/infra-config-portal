"""Explain erase choices separately from permission to execute them."""


def erase_options(probe, *, executor_available=False, current=False, arrays_present=None):
    storage = probe.get("storage") or {}
    drives = storage.get("physical_drives") or []
    media = {d.get("MediaType") for d in drives}
    known = bool(drives) and media <= {"HDD", "SSD"}
    base_reason = ("Run a fresh connection check for this device." if not current else
                   "This device has no validated erase execution path in this app. Server generation alone does not establish support."
                   if not executor_available else "")

    def option(key, label, speed, protection, compatible, mismatch):
        reason = base_reason or (mismatch if not compatible else "")
        return {"id": key, "label": label, "speed": speed, "protection": protection,
                "selectable": not reason, "status": "Review required" if not reason else "Unavailable",
                "reason": reason or "Selection opens a fresh device-specific review. Firmware/method approval and confirmation are still required."}

    choices = [
        option("auto", "Choose by drive type", "HDD overwrite; SSD block erase. Duration varies.",
               "Device sanitization; every disk needs completion evidence.", known, "Drive media must be identified as HDD or SSD."),
        option("OnePass", "Single-pass overwrite", "Can take hours; not guaranteed faster than device sanitize.",
               "Clears accessible sectors. Not a purge claim; not intended for SSDs.", known and media == {"HDD"}, "Only available for an all-HDD operation."),
        option("SanitizeRestrictedOverwrite", "Device sanitize overwrite", "Can take hours.",
               "Drive-managed overwrite, subject to verified firmware support.", known and media == {"HDD"}, "Only available for an all-HDD operation."),
        option("SanitizeRestrictedBlockErase", "Device sanitize block erase", "Drive-dependent; not instant crypto erase.",
               "Flash block erasure, subject to verified firmware support.", known and media == {"SSD"}, "Only available for an all-SSD operation. For mixed media, choose by drive type."),
        {"id": "crypto", "label": "Cryptographic erase", "speed": "Potentially very fast.",
         "protection": "Destroys encryption keys; requires verified encryption coverage and key sanitization.",
         "selectable": False, "status": "Not implemented",
         "reason": "The app cannot yet verify encryption prerequisites or execute and verify crypto erase on this device. Approval alone cannot enable it."},
        {"id": "native", "label": "Other native secure erase", "speed": "Depends on the advertised device operation.",
         "protection": "Controller/drive-specific; the action name alone does not establish sanitization coverage.",
         "selectable": False, "status": "Not implemented",
         "reason": "Gen11/RDE, MR, NVMe and other native erase paths need their own capability, execution and verification adapters. The legacy command is never substituted."},
    ]
    return {"models": [s.get("Model") for s in probe.get("systems", []) if s.get("Model")] if current else [],
            "controllers": [c.get("Model") for c in storage.get("controllers", []) if c.get("Model")] if current else [],
            "current": current, "options": choices,
            "reset": {"label": "Reset RAID for reuse", "speed": "Usually much faster than a full-disk wipe.",
                      "protection": "Removes array configuration, not disk contents. NOT secure erasure.",
                      "reason": "No arrays remain to remove." if arrays_present is False else
                                "Uses the separate RAID deletion confirmation; never starts a physical wipe."}}
