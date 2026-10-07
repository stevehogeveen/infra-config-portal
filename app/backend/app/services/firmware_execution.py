"""Default prerequisites when no actionable firmware review is available."""

BLOCKERS = (
    "A selected SPP with authenticated iLO 1.48 or 3.19 firmware and fresh exact-target capabilities is required.",
    "Healthy iLO, available power, safe cooling and an exclusive firmware maintenance write scope are required; storage warnings are reviewed separately.",
    "Create a fresh review and explicitly confirm the exact update and automatic iLO reset; host reboot is not authorized.",
)
