"""Guarded drive-return-to-service API."""
from app.services.guarded_execution import build_router
from app.services.drive_return_to_service import BLOCKERS

router = build_router("drive-return-to-service", BLOCKERS)
