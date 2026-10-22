from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.rack_plans import get_plan, kit_profile
from app.auth import get_current_actor
from app.core.database import get_session
from app.services import switch_access
from app.services import switch_setup as service

router = APIRouter(prefix="/api/v1/rack-plans", tags=["switch setup"])


class SwitchSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hostname: str = Field(min_length=1, max_length=63)
    domain: str = Field(min_length=1, max_length=253)
    username: str = Field(min_length=1, max_length=32)
    password: str | None = Field(default=None, max_length=64)
    enable_password: str | None = Field(default=None, max_length=64)
    vlan: int = Field(ge=1, le=4094)
    mode: str = Field(pattern="^(dhcp|static)$")
    address: str | None = Field(default=None, max_length=45)
    prefix: int | None = Field(default=None, ge=8, le=30)
    gateway: str | None = Field(default=None, max_length=45)
    save: bool = True
    uplink: str = Field(default="auto", max_length=40)
    uplink_mode: str = Field(default="access", pattern="^(access|trunk)$")


def switch_in_kit(profile_id: str, device_id: str, session: Session):
    kit_profile(profile_id)
    item = next((i for i in get_plan(profile_id, session).equipment if i.device_id == device_id and i.kind == "switch"), None)
    if not item:
        raise HTTPException(404, "Switch is not part of this kit.")
    return item


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except (service.SwitchSetupError, switch_access.SwitchAccessError) as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/{profile_id}/switch-setup/setup")
def setup(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    item = switch_in_kit(profile_id, device_id, session)
    return _call(service.get_setup, session, device_id, item.name)


@router.put("/{profile_id}/switch-setup/setup")
def save(profile_id: str, device_id: str, payload: SwitchSettings, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    item = switch_in_kit(profile_id, device_id, session)
    _call(service.save_settings, session, device_id, payload.model_dump(), actor)
    return _call(service.get_setup, session, device_id, item.name)


@router.post("/{profile_id}/switch-setup/review")
def review(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    switch_in_kit(profile_id, device_id, session)
    return _call(service.review, session, device_id)


@router.get("/{profile_id}/switch-setup/status")
def status(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    switch_in_kit(profile_id, device_id, session)
    return service.status(session, profile_id, device_id)


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    replace_existing: bool = False


@router.post("/{profile_id}/switch-setup/start")
def start(profile_id: str, device_id: str, payload: StartRequest | None = None, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    switch_in_kit(profile_id, device_id, session)
    return _call(service.start, session, profile_id, device_id, actor, replace_existing=bool(payload and payload.replace_existing))


@router.post("/{profile_id}/switch-setup/advance")
def advance(profile_id: str, device_id: str, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    switch_in_kit(profile_id, device_id, session)
    return _call(service.advance, session, profile_id, device_id, actor)


@router.post("/{profile_id}/switch-setup/close")
def close(profile_id: str, device_id: str, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    switch_in_kit(profile_id, device_id, session)
    return _call(service.close, session, profile_id, device_id, actor)
