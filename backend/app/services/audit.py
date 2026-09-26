"""
Audit service — immutable, append-only logging of all clinical actions.

Every triage recommendation must answer:
- What did the patient say?
- What facts were extracted?
- What rule triggered?
- Which protocol version was used?
- What severity did the machine recommend?
- What did the clinician decide?
- Were they different?
"""

from __future__ import annotations
import logging
from typing import Optional, Any
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import AuditLog as AuditLogModel

logger = logging.getLogger(__name__)


# Standard audit action names
class AuditAction:
    SESSION_STARTED = "SESSION_STARTED"
    PATIENT_REGISTERED = "PATIENT_REGISTERED"
    STT_TRANSCRIBED = "STT_TRANSCRIBED"
    FACTS_EXTRACTED = "FACTS_EXTRACTED"
    HALLUCINATION_REJECTED = "HALLUCINATION_REJECTED"
    CONTRADICTION_DETECTED = "CONTRADICTION_DETECTED"
    HIGH_ACUITY_TRIGGERED = "HIGH_ACUITY_TRIGGERED"
    VITAL_SIGNS_ENTERED = "VITAL_SIGNS_ENTERED"
    TRIAGE_COMPUTED = "TRIAGE_COMPUTED"
    TRIAGE_CONFIRMED = "TRIAGE_CONFIRMED"
    TRIAGE_OVERRIDDEN = "TRIAGE_OVERRIDDEN"
    REASSESSMENT_STARTED = "REASSESSMENT_STARTED"
    STT_FAILURE = "STT_FAILURE"
    LLM_FAILURE = "LLM_FAILURE"
    RULES_ENGINE_EXCEPTION = "RULES_ENGINE_EXCEPTION"
    KNOWLEDGE_RETRIEVED = "KNOWLEDGE_RETRIEVED"
    KNOWLEDGE_RETRIEVAL_FAILURE = "KNOWLEDGE_RETRIEVAL_FAILURE"
    TRANSLATION_FAILURE = "TRANSLATION_FAILURE"
    PATIENT_INACTIVE = "PATIENT_INACTIVE"
    PATIENT_ESCALATED = "PATIENT_ESCALATED"
    LOW_CONFIDENCE_CLARIFICATION = "LOW_CONFIDENCE_CLARIFICATION"


class AuditService:
    """Append-only audit log service."""

    async def log(
        self,
        db: AsyncSession,
        action: str,
        session_id: Optional[str] = None,
        actor: str = "system",
        detail: Optional[Any] = None,
    ) -> None:
        """Append an audit event. Never updates or deletes."""
        entry = AuditLogModel(
            session_id=session_id,
            actor=actor,
            action=action,
            detail=detail,
        )
        db.add(entry)
        await db.commit()

        # Deliberately do NOT include `detail` here — it may carry patient statements
        # or clinical text. The full record belongs only in the audit_logs table
        # (access-restricted, spec §31); ordinary application/stdout logs must stay
        # free of clinical content and are for operational debugging only.
        logger.info("AUDIT | action=%s | session=%s | actor=%s", action, session_id or "N/A", actor)


_audit_service = AuditService()


def get_audit_service() -> AuditService:
    return _audit_service
