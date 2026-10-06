"""Shared helpers for the post-shortlist pipeline stage, used by both the
screening endpoints (auto-transitions) and the tracking endpoints (manual)."""
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import Assessment, PIPELINE_STAGES
from app.models.assessment_stage_history import AssessmentStageHistory


def validate_stage(stage: str) -> str:
    stage = (stage or "").strip()
    if stage not in PIPELINE_STAGES:
        raise ValueError(f"Invalid stage '{stage}'. Allowed: {', '.join(PIPELINE_STAGES)}")
    return stage


def change_stage(
    db: AsyncSession,
    assessment: Assessment,
    new_stage: str,
    user_id: uuid.UUID | None,
    note: str = "",
) -> bool:
    """Sets assessment.stage and appends a history row. No-op (returns
    False) if the stage isn't actually changing. Caller commits."""
    old = assessment.stage or ""
    if old == new_stage:
        return False
    assessment.stage = new_stage
    if new_stage == "Submitted":
        assessment.sent_to_client = True
        if assessment.submitted_on is None:
            assessment.submitted_on = datetime.now(timezone.utc)
    db.add(AssessmentStageHistory(
        assessment_id=assessment.id,
        from_stage=old,
        to_stage=new_stage,
        note=note,
        changed_by=user_id,
    ))
    return True


def sync_stage_from_screening(db: AsyncSession, assessment: Assessment, user_id: uuid.UUID | None) -> None:
    """Keeps `stage` in step with the screening outcome (`final_status`)
    without ever overriding a stage a recruiter has set by hand
    (re-saving the screening form must not undo a later Rejected/Joined):
      Share to Client -> Shortlisted (only if no stage yet)
      Hold            -> On Hold     (only while still Shortlisted)
      Reject          -> Rejected    (only while still Shortlisted)
    A candidate never shortlisted keeps a blank stage, so they stay off the
    Shortlisted page.
    """
    status = assessment.final_status
    current = assessment.stage or ""
    if status == "Share to Client" and current == "":
        change_stage(db, assessment, "Shortlisted", user_id, "Screening: Share to Client")
    elif status == "Hold" and current == "Shortlisted":
        change_stage(db, assessment, "On Hold", user_id, "Screening: Hold")
    elif status == "Reject" and current == "Shortlisted":
        change_stage(db, assessment, "Rejected", user_id, "Screening: Reject")
