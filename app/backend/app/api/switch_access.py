from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.services import switch_access as service

router = APIRouter(prefix="/api/v1/devices", tags=["switch access"])


class SwitchAccessWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    host: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=256)
    enable_password: str | None = Field(default=None, max_length=256)


def _call(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except service.SwitchNotFoundError:
        raise HTTPException(404, "Device not found") from None
    except service.SwitchAccessError as exc:
        raise HTTPException(409, str(exc)) from None


@router.get("/{device_id}/switch-access")
def read_switch_access(device_id: str, session: Session = Depends(get_session)):
    return _call(service.read_access, session, device_id)


@router.put("/{device_id}/switch-access")
def save_switch_access(device_id: str, payload: SwitchAccessWrite, session: Session = Depends(get_session)):
    return _call(service.save_access, session, device_id, payload.model_dump(exclude_unset=True))


@router.post("/{device_id}/switch-access/check")
def check_switch(device_id: str, session: Session = Depends(get_session)):
    """Read-only: SSH sign-in plus show version, show inventory and show interfaces status."""
    return _call(service.check, session, device_id)


class ConsoleIdentify(BaseModel):
    model_config = ConfigDict(extra="forbid")
    port: str = Field(min_length=1, max_length=260)
    baud: int
    candidate_fingerprint: str = Field(min_length=1, max_length=128)


@router.get("/{device_id}/switch-console/ports")
def console_ports(device_id: str, session: Session = Depends(get_session)):
    """The COM ports on the operator's PC, through the console helper. Opens nothing."""
    return _call(service.console_ports, session, device_id)


@router.post("/{device_id}/switch-console/identify")
def console_identify(device_id: str, payload: ConsoleIdentify, session: Session = Depends(get_session)):
    """Read-only: open the chosen port, send one blank Enter, and read show version at a normal prompt."""
    return _call(service.console_identify, session, device_id, payload.port, payload.baud, payload.candidate_fingerprint)


@router.post("/{device_id}/switch-console/address")
def console_address(device_id: str, session: Session = Depends(get_session)):
    """Read-only: over the console, read the addresses the switch has (DHCP or static)."""
    return _call(service.console_address, session, device_id)
