from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.firmware_review import server_in_kit
from app.auth import get_current_actor
from app.core.database import get_session
from app.services import parts_update as service

router = APIRouter(prefix="/api/v1/rack-plans", tags=["firmware parts"])


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_id: str = Field(min_length=8, max_length=64, pattern=r"^[0-9a-f]+$")


def _call(function, *args):
    try:
        return function(*args)
    except service.PartsUpdateError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/{profile_id}/parts-update/status")
def parts_status(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    server_in_kit(profile_id, device_id, session)
    return service.status(session, profile_id, device_id)


@router.post("/{profile_id}/parts-update/review")
def parts_review(profile_id: str, device_id: str, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    return _call(service.review, session, profile_id, device_id, actor)


@router.post("/{profile_id}/parts-update/start")
def parts_start(profile_id: str, device_id: str, payload: StartRequest, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    return _call(service.start, session, profile_id, device_id, actor, payload.review_id)


@router.post("/{profile_id}/parts-update/advance")
def parts_advance(profile_id: str, device_id: str, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    return _call(service.advance, session, profile_id, device_id, actor)


@router.post("/{profile_id}/parts-update/close")
def parts_close(profile_id: str, device_id: str, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    return _call(service.close, session, profile_id, device_id, actor)
