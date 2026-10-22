"""Operator-scoped runtime permission changes, without hardware requests."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.auth import get_current_actor
from app.core.database import get_session
from app.services import runtime_write_scope as service

router = APIRouter(prefix="/api/v1/runtime/write-scope", tags=["Runtime write scope"])


class ScopePreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_scope: Literal["read_only", "firmware_only", "storage_only", "esxi_install_only", "vm_deploy_only", "switch_setup_only", "switch_reset_only"]


class ScopeApply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_token: str = Field(min_length=1, max_length=128)
    confirmation_phrase: str = Field(default="", max_length=256)


@router.get("")
def get_scope(session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    return service.state(session)


@router.post("/preview")
def preview_scope(
    payload: ScopePreview,
    session: Session = Depends(get_session),
    actor: str = Depends(get_current_actor),
):
    return service.preview(session, actor, payload.target_scope)


@router.post("/apply")
def apply_scope(
    payload: ScopeApply,
    session: Session = Depends(get_session),
    actor: str = Depends(get_current_actor),
):
    try:
        return service.apply(session, actor, payload.review_token, payload.confirmation_phrase)
    except service.WriteScopeError as exc:
        session.rollback()
        raise HTTPException(409, str(exc)) from None
