"""Staff / Command Center API."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timezone

from app.models.database import get_db
from app.models.models import Patient, TriageSession, TriageResult as TriageResultORM
from app.core.security import require_role
from app.services.audit import get_audit_service, AuditAction

router = APIRouter()
audit = get_audit_service()

COLOUR_PRIORITY = {"RED": 1, "ORANGE": 2, "YELLOW": 3, "GREEN": 4, "BLUE": 5, "UNKNOWN": 6}
COLOUR_MINUTES = {"RED": 0, "ORANGE": 10, "YELLOW": 60, "GREEN": 120, "BLUE": 240, "UNKNOWN": 999}


@router.get("/queue")
async def patient_queue(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("nurse", "admin")),
):
    """
    Command Center: sorted patient queue.
    Primary sort: severity (RED first).
    Secondary sort: time remaining until target assessment time.
    """
    # Get all active sessions with latest triage result
    sessions_result = await db.execute(
        select(TriageSession).where(TriageSession.status != "COMPLETED")
    )
    sessions = sessions_result.scalars().all()

    queue = []
    now = datetime.now(timezone.utc)

    for session in sessions:
        # Get patient
        pt_result = await db.execute(select(Patient).where(Patient.id == session.patient_id))
        patient = pt_result.scalar_one_or_none()

        # Get latest triage result
        tr_result = await db.execute(
            select(TriageResultORM)
            .where(TriageResultORM.session_id == session.id)
            .order_by(TriageResultORM.created_at.desc())
        )
        latest_triage = tr_result.scalars().first()

        if not latest_triage:
            colour = "UNKNOWN"
            final_severity = "UNKNOWN"
        else:
            # Use clinician decision if available, else AI recommendation
            final_severity = (
                latest_triage.clinician_decision or latest_triage.ai_recommendation or "UNKNOWN"
            )
            colour = final_severity

        # Calculate time remaining
        arrived_at = session.started_at or now
        target_mins = COLOUR_MINUTES.get(colour, 999)
        elapsed_secs = (now - arrived_at.replace(tzinfo=timezone.utc) if arrived_at.tzinfo is None
                       else now - arrived_at).total_seconds()
        remaining_secs = max(0, target_mins * 60 - elapsed_secs)

        queue.append({
            "patient_id": patient.id if patient else None,
            "visit_number": patient.visit_number if patient else "Unknown",
            "session_id": session.id,
            "colour": colour,
            "severity_label": final_severity,
            "priority": COLOUR_PRIORITY.get(colour, 6),
            "target_minutes": target_mins,
            "remaining_seconds": int(remaining_secs),
            "arrived_at": arrived_at,
            "session_status": session.status,
            "triage_status": latest_triage.status if latest_triage else "NOT_COMPUTED",
            "is_override": latest_triage.is_override if latest_triage else False,
        })

    # Sort: priority (colour) first, then remaining time
    queue.sort(key=lambda x: (x["priority"], x["remaining_seconds"]))
    return queue


@router.get("/patient/{session_id}/full")
async def patient_full_view(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("nurse", "admin")),
):
    """Full clinical staff view - all facts, vitals, triage, audit trail."""
    from app.models.models import (
        ConversationMessage, ClinicalFact, VitalSigns, AuditLog
    )

    session_result = await db.execute(select(TriageSession).where(TriageSession.id == session_id))
    session = session_result.scalar_one_or_none()
    if not session:
        return {"error": "Session not found"}

    patient_result = await db.execute(select(Patient).where(Patient.id == session.patient_id))
    patient = patient_result.scalar_one_or_none()

    messages_result = await db.execute(
        select(ConversationMessage).where(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.created_at)
    )
    messages = messages_result.scalars().all()

    facts_result = await db.execute(
        select(ClinicalFact).where(ClinicalFact.session_id == session_id)
    )
    facts = facts_result.scalars().all()

    vitals_result = await db.execute(
        select(VitalSigns).where(VitalSigns.session_id == session_id)
        .order_by(VitalSigns.recorded_at.desc())
    )
    from app.services.triage.vitals import merge_latest_vitals
    vitals = merge_latest_vitals(vitals_result.scalars().all())

    triage_result = await db.execute(
        select(TriageResultORM).where(TriageResultORM.session_id == session_id)
        .order_by(TriageResultORM.created_at.desc())
    )
    triage = triage_result.scalars().first()

    audit_result = await db.execute(
        select(AuditLog).where(AuditLog.session_id == session_id)
        .order_by(AuditLog.created_at)
    )
    audit_logs = audit_result.scalars().all()

    return {
        "patient": {
            "id": patient.id if patient else None,
            "visit_number": patient.visit_number if patient else "Unknown",
            "age": patient.age if patient else None,
            "preferred_language": patient.preferred_language if patient else "en",
        },
        "chief_complaint": next(
            (f.fact_value for f in facts if f.fact_type == "SYMPTOM" and "complaint" in f.fact_key.lower()),
            None
        ),
        "triage": {
            "id": triage.id if triage else None,
            "ai_recommendation": triage.ai_recommendation if triage else None,
            "clinician_decision": triage.clinician_decision if triage else None,
            "is_override": triage.is_override if triage else False,
            "override_reason": triage.override_reason if triage else None,
            "triggered_rules": triage.triggered_rules if triage else [],
            "rules_version": triage.rules_version if triage else None,
            "protocol": triage.protocol if triage else None,
            "ruleset_hash": triage.ruleset_hash if triage else None,
            "status": triage.status if triage else "NOT_COMPUTED",
        },
        "clinical_facts": [
            {
                "fact_key": f.fact_key,
                "fact_value": f.fact_value,
                "status": f.status,
                "confidence": f.confidence,
                "source": f.source,
                "evidence_text": f.evidence_text,
                "is_contradicted": f.is_contradicted,
            }
            for f in facts if not f.is_hallucination_rejected
        ],
        "vital_signs": {
            "temperature": vitals.temperature if vitals else None,
            "pulse": vitals.pulse if vitals else None,
            "spo2": vitals.spo2 if vitals else None,
            "systolic_bp": vitals.systolic_bp if vitals else None,
            "respiratory_rate": vitals.respiratory_rate if vitals else None,
            "avpu": vitals.avpu if vitals else None,
            "source": "OBJECTIVELY_MEASURED",
        } if vitals else None,
        "conversation": [
            {
                "id": m.id,
                "speaker": m.speaker,
                "original_text": m.original_text,
                "translated_text": m.translated_text,
                "created_at": m.created_at,
            }
            for m in messages
        ],
        "audit_trail": [
            {
                "action": a.action,
                "actor": a.actor,
                "detail": a.detail,
                "timestamp": a.created_at,
            }
            for a in audit_logs
        ],
    }


@router.post("/patient/{session_id}/escalate")
async def escalate_patient(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("nurse", "admin")),
):
    """Clinical staff action: immediately flag this patient for the clinical team (spec §23)."""
    result = await db.execute(select(TriageSession).where(TriageSession.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    reviewer = current_user.get("sub", "unknown_clinician")
    await audit.log(
        db, AuditAction.PATIENT_ESCALATED, session_id=session_id,
        actor=reviewer,
        detail={"escalated_by": reviewer},
    )
    return {"message": "Patient escalated to clinical team", "session_id": session_id}


@router.get("/alerts")
async def high_acuity_alerts(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_role("nurse", "admin")),
):
    """
    Command Center Alert Feed (spec §18):
    Returns all active high-acuity / urgent-finding alerts and RED/ORANGE sessions.
    """
    from app.models.models import AuditLog
    # Fetch sessions with status HIGH_ACUITY_INTERRUPTED or high-acuity audit events
    alerts_result = await db.execute(
        select(TriageSession).where(
            (TriageSession.status == "HIGH_ACUITY_INTERRUPTED") |
            (TriageSession.status == "AWAITING_REVIEW")
        )
    )
    sessions = alerts_result.scalars().all()

    alerts = []
    for session in sessions:
        # Fetch patient details
        pt_res = await db.execute(select(Patient).where(Patient.id == session.patient_id))
        patient = pt_res.scalar_one_or_none()

        # Fetch latest triage result
        tr_res = await db.execute(
            select(TriageResultORM)
            .where(TriageResultORM.session_id == session.id)
            .order_by(TriageResultORM.created_at.desc())
        )
        triage = tr_res.scalars().first()

        # Fetch latest audit trigger
        audit_res = await db.execute(
            select(AuditLog)
            .where(AuditLog.session_id == session.id, AuditLog.action == AuditAction.HIGH_ACUITY_TRIGGERED)
            .order_by(AuditLog.created_at.desc())
        )
        high_audit = audit_res.scalars().first()

        alerts.append({
            "session_id": session.id,
            "patient_id": patient.id if patient else None,
            "visit_number": patient.visit_number if patient else "Unknown",
            "status": session.status,
            "colour": triage.colour if triage else "RED",
            "triage_level": triage.triage_level if triage else 1,
            "reason": high_audit.detail.get("reason") if (high_audit and high_audit.detail) else "Urgent finding red-flag alert",
            "alerted_at": high_audit.created_at if high_audit else session.started_at,
        })

    alerts.sort(key=lambda x: x["alerted_at"] or datetime.min, reverse=True)
    return {"alerts_count": len(alerts), "alerts": alerts}
