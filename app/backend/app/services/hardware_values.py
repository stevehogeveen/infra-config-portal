"""Normalize vendor inventory values without guessing missing hardware."""
def firmware_version(resource):
    value = resource.get("FirmwareVersion") or resource.get("Version") or resource.get("FirmwarePackageVersion") or resource.get("Firmware")
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        current = value.get("Current", value)
        if isinstance(current, dict) and isinstance(current.get("VersionString"), str):
            return current["VersionString"].strip()
    return ""


def health(resource):
    status = resource.get("Status") or {}
    return status.get("Health") or status.get("HealthRollup") or "Unknown"


def pci_identity(resource):
    result = {}
    for key, aliases in {"ven": ("VendorID", "VendorId"), "dev": ("DeviceID", "DeviceId"),
                         "subven": ("SubsystemVendorID", "SubsystemVendorId"),
                         "subdev": ("SubsystemDeviceID", "SubsystemId", "SubsystemID")}.items():
        value = next((resource[a] for a in aliases if resource.get(a) is not None), None)
        if isinstance(value, int):
            result[key] = f"{value:04x}"
        elif isinstance(value, str):
            result[key] = value.lower().removeprefix("0x").zfill(4)
    return result
