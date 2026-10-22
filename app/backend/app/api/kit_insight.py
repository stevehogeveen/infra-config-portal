from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.services import ask_lab, trace

router = APIRouter(prefix="/api/v1", tags=["kit insight"])


@router.get("/rack-plans/{profile_id}/trace")
def trace_path(profile_id: str, session: Session = Depends(get_session)):
    """Stored records only: VM to gateway, hop by hop, and where the evidence stops."""
    return trace.build(session, profile_id)


@router.get("/ask")
def ask_the_lab(q: str = Query(min_length=1, max_length=200), session: Session = Depends(get_session)):
    """Answers from the app's own records (plan, changes, checks); nothing is generated."""
    return ask_lab.ask(session, q)
