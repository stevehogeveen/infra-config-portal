from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import get_current_actor
from app.core.database import get_session
from app.services import kit_reset, switch_access, switch_reset

router = APIRouter(prefix="/api/v1", tags=["reset"])


class Typed(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation: str = Field(min_length=1, max_length=250)


def _switch_in_kit(profile_id: str, device_id: str, session: Session) -> None:
    from app.api.rack_plans import get_plan

    plan = get_plan(profile_id, session)
    if not any(item.device_id == device_id and item.kind == "switch" for item in plan.equipment):
        raise HTTPException(404, "That switch is not in this kit.")
    try:
        switch_access.require_switch(session, device_id)
    except switch_access.SwitchNotFoundError:
        raise HTTPException(404, "Switch not found") from None


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (switch_reset.SwitchResetError, kit_reset.KitResetError, switch_access.SwitchAccessError) as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/rack-plans/{profile_id}/reset")
def reset_summary(profile_id: str, session: Session = Depends(get_session)):
    return kit_reset.summary(session, profile_id)


@router.post("/rack-plans/{profile_id}/reset/forget-signins")
def forget_signins(profile_id: str, payload: Typed, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    return _call(kit_reset.forget, session, profile_id, actor, payload.confirmation)


@router.post("/rack-plans/{profile_id}/switch-reset/review")
def switch_reset_review(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    _switch_in_kit(profile_id, device_id, session)
    return _call(switch_reset.review, session, device_id)


@router.get("/rack-plans/{profile_id}/switch-reset/status")
def switch_reset_status(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    _switch_in_kit(profile_id, device_id, session)
    return switch_reset.status(session, profile_id, device_id)


@router.post("/rack-plans/{profile_id}/switch-reset/start")
def switch_reset_start(profile_id: str, device_id: str, payload: Typed, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    _switch_in_kit(profile_id, device_id, session)
    return _call(switch_reset.start, session, profile_id, device_id, actor, payload.confirmation)


@router.post("/rack-plans/{profile_id}/switch-reset/advance")
def switch_reset_advance(profile_id: str, device_id: str, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    _switch_in_kit(profile_id, device_id, session)
    return _call(switch_reset.advance, session, profile_id, device_id, actor)


@router.post("/rack-plans/{profile_id}/switch-reset/close")
def switch_reset_close(profile_id: str, device_id: str, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    _switch_in_kit(profile_id, device_id, session)
    return _call(switch_reset.close, session, profile_id, device_id, actor)
