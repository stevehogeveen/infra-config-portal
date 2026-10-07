from typing import Literal

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.firmware_review import server_in_kit
from app.auth import get_current_actor
from app.core.database import get_session
from app.services import esxi_install as service

router = APIRouter(prefix="/api/v1/rack-plans", tags=["esxi install"])


class MediaChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(min_length=1, max_length=512)


class EsxiSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hostname: str = Field(min_length=3, max_length=253)
    addressing: Literal["static", "dhcp"] = "static"
    management_ip: str | None = Field(default=None, max_length=15)
    datastore_name: str = Field(default="VMdata", max_length=42)
    vlan_id: int = Field(default=0, ge=0, le=4094)
    # A vmnic name, or the port's MAC address as the iLO lists it (the kickstart accepts either).
    management_nic: str = Field(default="vmnic0", max_length=17)
    # Accepted once and hashed; never stored, logged or returned in plain text.
    root_password: str | None = Field(default=None, max_length=64)


def _call(function, *args):
    try:
        return function(*args)
    except service.EsxiInstallError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/{profile_id}/esxi/media")
def esxi_media(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    server_in_kit(profile_id, device_id, session)
    return service.list_media(session, profile_id, device_id)


@router.post("/{profile_id}/esxi/media")
def choose_esxi_media(profile_id: str, device_id: str, payload: MediaChoice, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    return _call(service.select_media, session, profile_id, device_id, payload.path, actor)


@router.get("/{profile_id}/esxi/settings")
def esxi_settings(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    server_in_kit(profile_id, device_id, session)
    return service.get_settings(session, profile_id, device_id)


@router.put("/{profile_id}/esxi/settings")
def save_esxi_settings(profile_id: str, device_id: str, payload: EsxiSettings, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    return _call(service.save_settings, session, profile_id, device_id, payload.model_dump(), actor)


@router.get("/{profile_id}/esxi/network-ports")
def esxi_network_ports(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    server_in_kit(profile_id, device_id, session)
    return service.list_network_ports(session, profile_id, device_id)


@router.get("/{profile_id}/esxi/installer")
def esxi_installer(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    server_in_kit(profile_id, device_id, session)
    return service.build_status(session, profile_id, device_id)


@router.post("/{profile_id}/esxi/installer")
def build_esxi_installer(profile_id: str, device_id: str, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    return _call(service.build_installer, session, profile_id, device_id, actor)


@router.get("/{profile_id}/esxi/install")
def esxi_install_status(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    server_in_kit(profile_id, device_id, session)
    return service.install_status(session, profile_id, device_id)


@router.post("/{profile_id}/esxi/install")
def start_esxi_install(profile_id: str, device_id: str, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    return _call(service.start_install, session, profile_id, device_id, actor)


class CheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # DHCP only: the address shown on the server screen, when the iLO has not reported one yet.
    address: str | None = Field(default=None, max_length=15)


@router.post("/{profile_id}/esxi/install/check")
def check_esxi_install(profile_id: str, device_id: str, payload: CheckRequest | None = Body(default=None), session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    return _call(service.check_install, session, profile_id, device_id, actor, payload.address if payload else None)


@router.post("/{profile_id}/esxi/install/resume")
def resume_esxi_install(profile_id: str, device_id: str, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    return _call(service.resume_install, session, profile_id, device_id, actor)


@router.post("/{profile_id}/esxi/install/close")
def close_esxi_install(profile_id: str, device_id: str, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    return _call(service.cancel_install, session, profile_id, device_id, actor)
