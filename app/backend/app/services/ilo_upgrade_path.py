"""Known iLO 5 prerequisite exclusions; passing is not upgrade authorization."""
from app.services.spp_assessment import numeric_version

def ilo_upgrade_blockers(installed: str, target: str, binary_size: int) -> list[str]:
    current = numeric_version(installed, "ilo")
    desired = numeric_version(target, "ilo")
    if current is None or desired is None:
        return ["Installed and target iLO versions must be known before planning an update."]
    if type(binary_size) is not int or binary_size <= 0:
        return ["A measured firmware binary size is required."]
    width = max(2, len(current), len(desired))
    current += (0,) * (width - len(current))
    desired += (0,) * (width - len(desired))
    first_bridge = (1, 48) + (0,) * (width - 2)
    requires_first_bridge = (2, 44) + (0,) * (width - 2)
    blockers = []
    if current < first_bridge and desired >= requires_first_bridge:
        blockers.append(
            "Install a separately reviewed iLO 5 1.48 update first. "
            "This workflow retains the 1.48 bridge before firmware 2.44 or later."
        )
    if desired <= current:
        blockers.append("The target must be newer than installed iLO; reinstall and downgrade are not enabled.")
    return blockers
