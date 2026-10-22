from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.firmware_review import server_in_kit
from app.auth import get_current_actor
from app.core.database import get_session
from app.services import acceptance
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
def windows_setup(profile_id: str, device_id: str, host: bool = True, session: Session = Depends(get_session)):
    """host=false answers from records only (no ESXi contact): saved settings, images, and the host's address."""
    server_in_kit(profile_id, device_id, session)
    return service.get_setup(session, profile_id, device_id, read_host=host)


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


# ---------------------------------------------------------------- acceptance test

class GuestSignin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class AcceptanceStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=253)


def _test(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (acceptance.AcceptanceError, service.WindowsDeployError) as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/{profile_id}/windows/guest-signin")
def guest_signin(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    server_in_kit(profile_id, device_id, session)
    return acceptance.signin_status(device_id)


@router.put("/{profile_id}/windows/guest-signin")
def save_guest_signin(profile_id: str, device_id: str, payload: GuestSignin, session: Session = Depends(get_session)):
    server_in_kit(profile_id, device_id, session)
    return _test(acceptance.save_signin, device_id, payload.username, payload.password)


@router.get("/{profile_id}/windows/acceptance")
def acceptance_status(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    server_in_kit(profile_id, device_id, session)
    return acceptance.status(session, profile_id, device_id)


@router.post("/{profile_id}/windows/acceptance/start")
def acceptance_start(profile_id: str, device_id: str, payload: AcceptanceStart, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    return _test(acceptance.start, session, profile_id, device_id, actor, payload.name)


@router.post("/{profile_id}/windows/acceptance/advance")
def acceptance_advance(profile_id: str, device_id: str, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    return _test(acceptance.advance, session, profile_id, device_id, actor)


@router.post("/{profile_id}/windows/acceptance/close")
def acceptance_close(profile_id: str, device_id: str, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    return _test(acceptance.close, session, profile_id, device_id, actor)
