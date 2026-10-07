"""Reviewed HPE SUM handoff. No firmware execution or hardware mutation."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.rack_plans import firmware_assessment, get_plan, kit_profile
from app.auth import get_current_actor
from app.core.database import get_session
from app.services.audit import record_audit_event
from app.services.hardware_health import digest, read_health_review
from app.services.ilo_access_settings import read_ilo_access_settings

router = APIRouter(prefix="/api/v1/rack-plans", tags=["firmware review"])


class ReviewToken(BaseModel):
    model_config = ConfigDict(extra="forbid")
    review_token: str = Field(min_length=64, max_length=64)


class HealthAcknowledgement(ReviewToken):
    issue_id: str = Field(min_length=64, max_length=64)


def server_in_kit(profile_id, device_id, session):
    kit_profile(profile_id)
    server = next((i for i in get_plan(profile_id, session).equipment if i.device_id == device_id and i.kind == "server"), None)
    if not server:
        raise HTTPException(404, "Server is not part of this kit.")
    return server


@router.post("/{profile_id}/health-acknowledgements")
def acknowledge_health(profile_id: str, device_id: str, payload: HealthAcknowledgement,
                       session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    server_in_kit(profile_id, device_id, session)
    review = read_health_review(session, profile_id, device_id)
    if not review["current"] or review["review_token"] != payload.review_token:
        raise HTTPException(409, "Health readings changed or expired. Refresh and review the current alerts.")
    issue = next((i for i in review["issues"] if i["id"] == payload.issue_id), None)
    if not issue:
        raise HTTPException(409, "This alert is not in the current health review.")
    if not issue["acknowledged_at"]:
        record_audit_event(session, actor=actor, event_type="kit.health_issue_acknowledged",
                           message="Hardware alert acknowledged; still unresolved. No approval or hardware changes.",
                           data={"profile_id": profile_id, "device_id": device_id, "review_token": review["review_token"],
                                 "issue_id": issue["id"], "title": issue["title"], "health": issue["health"]})
        session.commit()
    return read_health_review(session, profile_id, device_id)


@router.get("/{profile_id}/firmware-upgrade-review")
def upgrade_review(profile_id: str, device_id: str, session: Session = Depends(get_session)):
    server = server_in_kit(profile_id, device_id, session)
    assessment = firmware_assessment(profile_id, device_id, session)
    health_review = assessment["health_review"]
    host = read_ilo_access_settings(session, device_id)["host"]
    updates = [r for r in assessment["rows"] if r["status"] == "Update available"]
    unknown = [r for r in assessment["rows"] if r["status"] == "Cannot determine"]
    blockers = []
    if not health_review["current"]:
        blockers.append("Refresh this server's inventory before reviewing an upgrade.")
    if health_review["unacknowledged"]:
        blockers.append(f"{health_review['unacknowledged']} hardware alert(s) still need acknowledgement.")
    if health_review["issues"]:
        blockers.append("Hardware alerts remain unresolved. Acknowledgement is not approval to install firmware.")
    if not updates:
        blockers.append(assessment.get("reason") or "No matching newer firmware has been established.")
    if unknown:
        blockers.append(f"{len(unknown)} component(s) still need HPE SUM applicability review; they are not declared up to date.")
    blockers.append("Automatic SPP installation is not connected. Use attended HPE Smart Update Manager (SUM) for dependency checks and installation.")
    token = digest({"profile": profile_id, "device": device_id, "host": host,
                    "health_review": health_review["review_token"], "metadata": assessment.get("metadata_sha256"),
                    "package": assessment.get("package_file"), "rows": assessment["rows"]})
    return {"review_token": token, "server": server.name, "host": host,
            "model": assessment.get("detected_model"), "package_file": assessment.get("package_file"),
            "updates": updates, "unassessed": len(unknown), "health_review": health_review, "blockers": blockers,
            "can_save_review": bool(health_review["current"] and not health_review["unacknowledged"] and updates),
            "apply_enabled": False, "execution_method": "Attended HPE SUM",
            "vendor_url": "https://support.hpe.com/hpesc/public/docDisplay?docId=c03190790&page=GUID-AF397BA5-4F05-47E2-A822-80301DC0123F.html"}


@router.post("/{profile_id}/firmware-upgrade-review")
def save_upgrade_review(profile_id: str, device_id: str, payload: ReviewToken,
                        session: Session = Depends(get_session), actor: str = Depends(get_current_actor)):
    review = upgrade_review(profile_id, device_id, session)
    if payload.review_token != review["review_token"] or not review["can_save_review"]:
        raise HTTPException(409, "Refresh the firmware comparison and acknowledge its current hardware alerts before saving this review.")
    record_audit_event(session, actor=actor, event_type="kit.firmware_upgrade_reviewed",
                       message="Saved firmware review for attended HPE SUM; no installation authorized or started.",
                       data={"profile_id": profile_id, "device_id": device_id, "review_token": review["review_token"],
                             "package_file": review["package_file"], "updates": review["updates"],
                             "health_review": review["health_review"], "blockers": review["blockers"], "apply_enabled": False})
    session.commit()
    return {"status": "Review saved", "message": "Review saved in kit history. No firmware installation approved or started.", "apply_enabled": False}
