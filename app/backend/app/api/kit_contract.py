"""Record-only contract reads; explicit approval and poll-driven execution."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import get_current_actor
from app.core.database import get_session
from app.services import kit_contract as service

router = APIRouter(prefix="/api/v1/rack-plans/{profile_id}/contract", tags=["kit contract"])


class Approval(BaseModel):
    model_config = ConfigDict(extra="forbid")
    digest: str = Field(pattern=r"^[a-f0-9]{64}$")


@router.get("")
def contract(profile_id: str, session: Session = Depends(get_session)):
    return service.contract(session, profile_id)


@router.post("/approve")
def approve(profile_id: str, payload: Approval, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    try:
        return service.approve(session, profile_id, actor, payload.digest)
    except service.ContractError as exc:
        raise HTTPException(409, str(exc)) from None


@router.post("/reconcile")
def reconcile(profile_id: str, session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    return service.reconcile(session, profile_id, actor)


@router.get("/certificate")
def certificate(profile_id: str, session: Session = Depends(get_session)):
    return service.certificate(session, profile_id)
