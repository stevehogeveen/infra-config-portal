from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.firmware_review import server_in_kit
from app.auth import get_current_actor
from app.core.database import get_session
from app.services import windows_deploy as service

router = APIRouter(prefix="/api/v1/rack-plans", tags=["windows deploy"])


class WindowsSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    image: str = Field(min_length=1, max_length=512)
    vm_name: str = Field(min_length=1, max_length=63)
    datastore: str = Field(min_length=1, max_length=128)
    network: str = Field(min_length=1, max_length=128)


def _call(function, *args):
    try:
        return function(*args)
    except service.WindowsDeployError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/{profile_id}/windows/setup")
def windows_setup(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    server_in_kit(profile_id, device_id, session)
    return service.get_setup(session, profile_id, device_id)


@router.put("/{profile_id}/windows/setup")
def save_windows_setup(profile_id: str, device_id: str, payload: WindowsSettings, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    return _call(service.save_settings, session, profile_id, device_id, payload.model_dump(), actor)


@router.post("/{profile_id}/windows/review")
def windows_review(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    server_in_kit(profile_id, device_id, session)
    return _call(service.review, session, profile_id, device_id)


@router.get("/{profile_id}/windows/status")
def windows_status(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    server_in_kit(profile_id, device_id, session)
    return service.status(session, profile_id, device_id)


@router.post("/{profile_id}/windows/start")
def windows_start(profile_id: str, device_id: str, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    return _call(service.start, session, profile_id, device_id, actor)


@router.post("/{profile_id}/windows/advance")
def windows_advance(profile_id: str, device_id: str, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    return _call(service.advance, session, profile_id, device_id, actor)


@router.post("/{profile_id}/windows/close")
def windows_close(profile_id: str, device_id: str, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    return _call(service.close, session, profile_id, device_id, actor)
