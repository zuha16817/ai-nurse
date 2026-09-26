"""
Triage API — runs the deterministic triage engine and manages human-in-the-loop.

Key principle: The LLM never decides triage. This router calls the pure
deterministic engine which produces explainable, evidence-backed results.
"""

from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.models.database import get_db
from app.models.models import (
    TriageSession, TriageResult as TriageResultORM,
    ClinicalFact as ClinicalFactORM, VitalSigns as VitalSignsORM,
    Patient,
)
from app.services.triage.engine import get_triage_engine, load_rules
from app.services.triage.models import (
    ClinicalAssessment, ClinicalFact, Evidence,
    ObjectiveVitalSigns, TriageColour, SymptomStatus, ClinicalValueStatus,
    PainAssessment, BreathingAssessment, BleedingAssessment, ConsciousnessAssessment,
    ChiefComplaint,
)
from app.services.audit import get_audit_service, AuditAction
from app.services.triage.vitals import merge_latest_vitals
from app.core.security import get_current_user, require_role

router = APIRouter()
logger = logging.getLogger(__name__)
audit = get_audit_service()


@router.post("/{session_id}/compute")
async def compute_triage(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Run the deterministic triage engine on the current clinical assessment.

    Deliberately NOT staff-authenticated: this is triggered by the patient's own
    conversation completing (system-initiated, not a clinician action), unlike
    confirm/override/reassess below which require a logged-in clinician. Restricting
    this endpoint previously made it impossible for the patient kiosk to ever reach
    the "Assessment Complete" screen.

    Same facts + same rules version = same result (deterministic).
    LLM is NOT called here.
    """
    # Load session
    session = await _get_session(session_id, db)

    # Rebuild ClinicalAssessment from DB
    assessment = await _rebuild_assessment(session_id, db)

    # Load triage rules (versioned)
    try:
        rule_set = load_rules()
    except Exception as e:
        await audit.log(db, AuditAction.RULES_ENGINE_EXCEPTION, session_id=session_id,
                        detail={"error": str(e)})
        raise HTTPException(status_code=500, detail=f"Rules engine error: {e}")

    # Run engine (deterministic — no LLM)
    engine = get_triage_engine()
    try:
        result = engine.evaluate(assessment, rule_set)
    except Exception as e:
        await audit.log(db, AuditAction.RULES_ENGINE_EXCEPTION, session_id=session_id,
                        detail={"error": str(e)})
        # On rules engine failure → safe escalation (never invent a low-acuity result)
        raise HTTPException(
            status_code=500,
            detail="Triage rules engine failed — escalate to clinician review"
        )

    # Persist result
    triage_orm = TriageResultORM(
        session_id=session_id,
        triage_level=result.triage_level,
        colour=result.colour.value,
        category=result.category.value,
        target_minutes=result.target_assessment_minutes,
        triggered_rules=[r.model_dump() for r in result.triggered_rules],
        rules_version=result.rules_version,
        protocol=result.protocol,
        ruleset_hash=result.ruleset_hash,
        evaluated_at=result.evaluated_at,
        ai_recommendation=result.colour.value,
        status="PENDING_REVIEW",
    )
    db.add(triage_orm)
    session.status = "AWAITING_REVIEW"
    await db.commit()

    await audit.log(
        db, AuditAction.TRIAGE_COMPUTED, session_id=session_id,
        actor="system",
        detail={
            "colour": result.colour.value,
            "level": result.triage_level,
            "rules_version": result.rules_version,
            "rules_triggered": [r.rule_id for r in result.triggered_rules],
        },
    )

    return {
        "triage_result_id": triage_orm.id,
        "ai_recommendation": result.colour.value,
        "triage_level": result.triage_level,
        "category": result.category.value,
        "target_assessment_minutes": result.target_assessment_minutes,
        "triggered_rules": [r.model_dump() for r in result.triggered_rules],
        "rules_version": result.rules_version,
        "protocol": result.protocol,
        "ruleset_hash": result.ruleset_hash,
        "evaluated_at": result.evaluated_at,
        "explanation": result.explanation,
        "status": "PENDING_REVIEW",
        "note": "This is an AI TRIAGE RECOMMENDATION — awaiting clinician confirmation.",
    }


class ConfirmRequest(BaseModel):
    decision: str           # RED | ORANGE | YELLOW | GREEN | BLUE (same as AI)
    override_reason: Optional[str] = None


class OverrideRequest(BaseModel):
    new_severity: str       # RED | ORANGE | YELLOW | GREEN | BLUE
    override_reason: str    # required for overrides


@router.post("/{triage_result_id}/confirm")
async def confirm_triage(
    triage_result_id: str,
    body: ConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("nurse", "admin")),
):
    """Clinician accepts the AI recommendation."""
    triage = await _get_triage_result(triage_result_id, db)
    reviewer = current_user.get("sub", "unknown_clinician")
    triage.clinician_decision = body.decision
    triage.reviewed_by = reviewer
    triage.reviewed_at = datetime.now(timezone.utc)
    triage.status = "CONFIRMED"
    triage.is_override = False
    await db.commit()

    await audit.log(
        db, AuditAction.TRIAGE_CONFIRMED, session_id=triage.session_id,
        actor=reviewer,
        detail={"ai_recommendation": triage.ai_recommendation, "decision": body.decision},
    )
    return {"message": "Triage confirmed", "final_severity": body.decision}


@router.post("/{triage_result_id}/override")
async def override_triage(
    triage_result_id: str,
    body: OverrideRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("nurse", "admin")),
):
    """Clinician overrides the AI recommendation — captured in audit trail."""
    triage = await _get_triage_result(triage_result_id, db)
    reviewer = current_user.get("sub", "unknown_clinician")
    triage.clinician_decision = body.new_severity
    triage.override_reason = body.override_reason
    triage.reviewed_by = reviewer
    triage.reviewed_at = datetime.now(timezone.utc)
    triage.status = "OVERRIDDEN"
    triage.is_override = True
    await db.commit()

    await audit.log(
        db, AuditAction.TRIAGE_OVERRIDDEN, session_id=triage.session_id,
        actor=reviewer,
        detail={
            "ai_recommendation": triage.ai_recommendation,
            "clinician_decision": body.new_severity,
            "override_reason": body.override_reason,
            "reviewed_by": reviewer,
        },
    )
    return {
        "message": "Triage override recorded",
        "ai_recommendation": triage.ai_recommendation,
        "final_severity": body.new_severity,
        "override_reason": body.override_reason,
    }


@router.post("/{session_id}/reassess")
async def start_reassessment(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("nurse", "admin")),
):
    """Start a new triage session for re-assessment. Keeps all previous sessions."""
    session = await _get_session(session_id, db)
    patient_id = session.patient_id

    # Count existing sessions
    result = await db.execute(
        select(TriageSession).where(TriageSession.patient_id == patient_id)
    )
    existing = result.scalars().all()
    new_number = len(existing) + 1

    new_session = TriageSession(
        patient_id=patient_id,
        session_number=new_number,
        status="IN_PROGRESS",
    )
    db.add(new_session)
    await db.commit()
    await db.refresh(new_session)

    await audit.log(
        db, AuditAction.REASSESSMENT_STARTED, session_id=new_session.id,
        actor=current_user.get("sub", "unknown_clinician"),
        detail={"previous_session_id": session_id, "session_number": new_number},
    )

    return {
        "new_session_id": new_session.id,
        "session_number": new_number,
        "message": "New triage session started for reassessment",
    }


@router.get("/{session_id}/history")
async def triage_history(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Full triage history for a session — never replaced, always appended."""
    result = await db.execute(
        select(TriageResultORM)
        .where(TriageResultORM.session_id == session_id)
        .order_by(TriageResultORM.created_at)
    )
    results = result.scalars().all()
    return [
        {
            "id": r.id,
            "ai_recommendation": r.ai_recommendation,
            "clinician_decision": r.clinician_decision,
            "is_override": r.is_override,
            "override_reason": r.override_reason,
            "reviewed_by": r.reviewed_by,
            "reviewed_at": r.reviewed_at,
            "status": r.status,
            "created_at": r.created_at,
            "rules_version": r.rules_version,
            "triggered_rules": r.triggered_rules,
        }
        for r in results
    ]


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_session(session_id: str, db: AsyncSession) -> TriageSession:
    result = await db.execute(select(TriageSession).where(TriageSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


async def _get_triage_result(result_id: str, db: AsyncSession) -> TriageResultORM:
    result = await db.execute(select(TriageResultORM).where(TriageResultORM.id == result_id))
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(status_code=404, detail="Triage result not found")
    return r


async def _rebuild_assessment(session_id: str, db: AsyncSession) -> ClinicalAssessment:
    """Reconstruct ClinicalAssessment from all stored facts and vitals."""

    # Load facts
    fact_result = await db.execute(
        select(ClinicalFactORM).where(ClinicalFactORM.session_id == session_id)
    )
    facts_orm = fact_result.scalars().all()

    # Load latest vital signs
    vs_result = await db.execute(
        select(VitalSignsORM)
        .where(VitalSignsORM.session_id == session_id)
        .order_by(VitalSignsORM.recorded_at.desc())
    )
    latest_vitals = merge_latest_vitals(vs_result.scalars().all())

    assessment = ClinicalAssessment(session_id=session_id)

    # Intake demographics live on the Patient row. Rules such as RULE-ORANGE-010
    # (pregnancy + bleeding) and RULE-ORANGE-011 (infant + fever) read these fields
    # from the assessment, so they must be loaded here or those rules can never fire.
    patient_result = await db.execute(
        select(Patient).join(TriageSession, TriageSession.patient_id == Patient.id)
        .where(TriageSession.id == session_id)
    )
    patient = patient_result.scalar_one_or_none()
    if patient:
        assessment.patient_age = patient.age
        assessment.patient_language = patient.preferred_language or "en"
        # Unknown stays UNKNOWN — never coerced into a negative finding.
        assessment.pregnancy_status = patient.pregnancy_status or "UNKNOWN"

    # Merge vitals (OBJECTIVELY_MEASURED)
    if latest_vitals:
        assessment.vital_signs = ObjectiveVitalSigns(
            temperature=latest_vitals.temperature,
            pulse=latest_vitals.pulse,
            systolic_bp=latest_vitals.systolic_bp,
            diastolic_bp=latest_vitals.diastolic_bp,
            respiratory_rate=latest_vitals.respiratory_rate,
            spo2=latest_vitals.spo2,
            pain_score=latest_vitals.pain_score,
            gcs=latest_vitals.gcs,
            avpu=latest_vitals.avpu,
            entered_by=latest_vitals.entered_by,
        )
        assessment.temperature = latest_vitals.temperature

    # Merge facts
    extractor_instance = None
    for f in facts_orm:
        if f.is_hallucination_rejected:
            continue

        fact = ClinicalFact(
            fact_id=f.id,
            fact_type=f.fact_type,
            fact_key=f.fact_key,
            fact_value=f.fact_value,
            status=SymptomStatus(f.status) if f.status else SymptomStatus.UNKNOWN,
            confidence=f.confidence,
            evidence=Evidence(
                message_id=f.evidence_message_id or "unknown",
                speaker="patient",
                original_text=f.evidence_text or "",
            ),
            source=f.source or "PATIENT_REPORTED",
        )
        assessment.all_facts.append(fact)

    # Update structured fields from facts
    from app.services.extraction.extractor import ClinicalFactExtractor
    e = ClinicalFactExtractor()
    e._update_structured_fields(assessment, assessment.all_facts)
    e._update_chief_complaint(assessment, assessment.all_facts, type("x", (), {"missing_information": []})())

    # CRITICAL: rules like RULE-RED-003 ("consciousness.avpu equals Unresponsive")
    # read assessment.consciousness, NOT assessment.vital_signs. Applied AFTER fact
    # merging so an OBJECTIVELY_MEASURED nurse assessment always outranks an earlier
    # PATIENT_REPORTED value for the same field — never the other way around.
    if latest_vitals and (latest_vitals.avpu or latest_vitals.gcs is not None):
        assessment.consciousness = ConsciousnessAssessment(
            avpu=latest_vitals.avpu or assessment.consciousness.avpu,
            gcs=latest_vitals.gcs if latest_vitals.gcs is not None else assessment.consciousness.gcs,
            confusion=assessment.consciousness.confusion,
            status=ClinicalValueStatus.KNOWN,
        )

    # A nurse-entered pain score is an objective reading, so it outranks any
    # patient-reported severity. Rules read assessment.pain.severity, not vital_signs.
    if latest_vitals and latest_vitals.pain_score is not None:
        assessment.pain.severity = latest_vitals.pain_score
        assessment.pain.status = ClinicalValueStatus.KNOWN
        if latest_vitals.pain_score > 0:
            assessment.pain.present = SymptomStatus.PRESENT

    return assessment
