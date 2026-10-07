"""Capability blockers for drive-return-to-service; no hardware execution."""
BLOCKERS = (
    "Return-to-service support after restricted sanitize is not established for the selected controller and firmware.",
    "An identity-verified maintenance environment and allow-listed recovery executor are not enabled.",
    "EraseCompleted is not proof of drive health. Do not repeat sanitization.",
)
