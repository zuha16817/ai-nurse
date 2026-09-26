"""
Conversations API — the core clinical interview pipeline.

Flow per message:
1. Accept audio (multipart) or text
2. STT (if audio) → transcript
3. Save message to DB
4. LLM extract → structured facts (JSON only)
5. Hallucination guard
6. Update ClinicalAssessment
7. Run red-flag safety check
8. Return next question + current assessment state
"""

from __future__ import annotations
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel, field_validator

from app.models.database import get_db
from app.models.models import (
    Patient, TriageSession, ConversationMessage, ClinicalFact as ClinicalFactORM,
    VitalSigns as VitalSignsORM,
)
from app.services.stt.whisper import get_stt_service
from app.services.llm.openai_service import get_conversation_service
from app.services.extraction.extractor import get_fact_extractor
from app.services.translation.translator import get_translation_service
from app.services.triage.models import (
    ClinicalAssessment, ObjectiveVitalSigns, SymptomStatus, ClinicalValueStatus,
)
from app.services.audit import get_audit_service, AuditAction
from app.core.security import get_current_user
from app.core.config import get_settings

router = APIRouter()
logger = logging.getLogger(__name__)
audit = get_audit_service()
settings = get_settings()

MAX_AUDIO_BYTES = 15 * 1024 * 1024  # 15 MB
ALLOWED_AUDIO_EXTENSIONS = {".webm", ".wav", ".mp3", ".m4a", ".ogg", ".mp4"}

# Clarification questions asked when a fact was rejected only for low confidence, or
# when the patient has given conflicting answers — never silently resolved (spec §16/§17).
CLARIFICATION_QUESTIONS = {
    "en": "I want to make sure I understood correctly — could you repeat or clarify what you said about {topic}?",
    "ur": "میں واضح کرنا چاہتا ہوں — کیا آپ {topic} کے بارے میں دوبارہ بتا سکتے ہیں؟",
    "ar": "أريد التأكد من فهمي بشكل صحيح — هل يمكنك توضيح ما قلته عن {topic}؟",
}

CONFLICT_QUESTIONS = {
    "en": "I noticed you gave different answers about {topic}: {values}. Which one is correct?",
    "ur": "آپ نے {topic} کے بارے میں مختلف جوابات دیے: {values}۔ کون سا درست ہے؟",
    "ar": "لاحظت أنك أعطيت إجابات مختلفة حول {topic}: {values}. أيهما صحيح؟",
}


def msg_id() -> str:
    return f"MSG-{uuid.uuid4().hex[:8].upper()}"


class TextMessageRequest(BaseModel):
    session_id: str
    text: str
    language: Optional[str] = None  # if known; otherwise auto-detect


class VitalSignsRequest(BaseModel):
    session_id: str
    temperature: Optional[float] = None
    pulse: Optional[int] = None
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    respiratory_rate: Optional[int] = None
    spo2: Optional[float] = None
    pain_score: Optional[int] = None
    gcs: Optional[int] = None
    avpu: Optional[str] = None

    @field_validator("avpu", mode="before")
    @classmethod
    def _valid_avpu(cls, v):
        # Empty means "not assessed" — stored as unknown, never as a default level.
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        canonical = {"alert": "Alert", "voice": "Voice", "pain": "Pain", "unresponsive": "Unresponsive"}
        key = str(v).strip().lower()
        if key not in canonical:
            raise ValueError("avpu must be one of Alert, Voice, Pain, Unresponsive")
        return canonical[key]


@router.post("/message/text")
async def send_text_message(
    body: TextMessageRequest,
    db: AsyncSession = Depends(get_db),
):
    """Process a typed patient message."""
    session = await _get_session(body.session_id, db)

    # Detect language if not provided
    lang = body.language or _detect_language(body.text)

    # Normalized English interpretation — the original is NEVER discarded or replaced
    # (spec §7/§15); this only adds a parallel translated_text field.
    translator = get_translation_service()
    translated = await translator.translate_to_english(body.text, lang)

    # Save message
    message = ConversationMessage(
        id=msg_id(),
        session_id=session.id,
        speaker="patient",
        original_text=body.text,
        translated_text=translated,
        detected_language=lang,
    )
    db.add(message)
    await db.flush()

    return await _process_message(session, message, lang, db, {"sub": "patient"})


@router.post("/message/audio")
async def send_audio_message(
    session_id: str = Form(...),
    audio: UploadFile = File(...),
    language: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Process a voice message — STT → extract → respond."""
    session = await _get_session(session_id, db)

    audio_bytes = await audio.read()

    # File validation (spec §32): size and extension allowlist before it ever reaches STT.
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file exceeds the 15MB limit")
    ext = os.path.splitext(audio.filename or "")[1].lower()
    if ext and ext not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Unsupported audio format: {ext}")

    stt_service = get_stt_service()

    try:
        transcript = await stt_service.transcribe(
            audio_bytes, filename=audio.filename or "audio.webm", expected_language=language,
        )
    except Exception as e:
        await audit.log(db, AuditAction.STT_FAILURE, session_id=session_id,
                        detail={"error": str(e)})
        # On STT failure → safe escalation (never a low-acuity assumption)
        return {
            "error": "speech_recognition_failed",
            "next_question": "I'm having difficulty hearing you. Please type your response or a nurse will assist you.",
            "high_acuity_trigger": True,
        }

    await audit.log(db, AuditAction.STT_TRANSCRIBED, session_id=session_id,
                    detail={"lang": transcript.detected_language, "text": transcript.text[:100]})

    translator = get_translation_service()
    translated = await translator.translate_to_english(transcript.text, transcript.detected_language)

    message = ConversationMessage(
        id=msg_id(),
        session_id=session.id,
        speaker="patient",
        original_text=transcript.text,
        translated_text=translated,
        stt_transcript=transcript.text,
        detected_language=transcript.detected_language,
        audio_file_path=audio.filename,
    )
    db.add(message)
    await db.flush()

    return await _process_message(session, message, transcript.detected_language, db, {"sub": "patient"})


@router.post("/vitals")
async def enter_vital_signs(
    body: VitalSignsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Nurse enters objective vital signs — clearly differentiated from patient-reported."""
    session = await _get_session(body.session_id, db)

    vitals = VitalSignsORM(
        session_id=session.id,
        temperature=body.temperature,
        pulse=body.pulse,
        systolic_bp=body.systolic_bp,
        diastolic_bp=body.diastolic_bp,
        respiratory_rate=body.respiratory_rate,
        spo2=body.spo2,
        pain_score=body.pain_score,
        gcs=body.gcs,
        avpu=body.avpu,
        entered_by=current_user.get("sub", "nurse"),
    )
    db.add(vitals)
    await db.commit()

    await audit.log(db, AuditAction.VITAL_SIGNS_ENTERED, session_id=session.id,
                    actor=current_user.get("sub", "nurse"),
                    detail=body.model_dump(exclude_none=True))

    return {"message": "Vital signs recorded", "source": "OBJECTIVELY_MEASURED"}


@router.post("/{session_id}/inactivity-alert")
async def report_inactivity(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Failure mode (spec §39): patient stops responding mid-interview.
    The client calls this after a period of no reply — it never invents a low-acuity
    result, it just flags the session for clinician attention.
    """
    session = await _get_session(session_id, db)
    await audit.log(db, AuditAction.PATIENT_INACTIVE, session_id=session.id,
                    detail={"reason": "No patient response within client-side inactivity window"})
    return {
        "message": "Inactivity recorded — a nurse has been notified to check on this patient.",
    }


@router.get("/{session_id}/transcript")
async def get_transcript(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return full conversation transcript with original + translated text."""
    result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session_id)
        .order_by(ConversationMessage.created_at)
    )
    messages = result.scalars().all()
    return [
        {
            "id": m.id,
            "speaker": m.speaker,
            "original_text": m.original_text,
            "translated_text": m.translated_text,
            "detected_language": m.detected_language,
            "created_at": m.created_at,
            "timestamp_seconds": m.timestamp_seconds,
        }
        for m in messages
    ]


# ── Internal helpers ───────────────────────────────────────────────────────────

async def _get_session(session_id: str, db: AsyncSession) -> TriageSession:
    result = await db.execute(
        select(TriageSession).where(TriageSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        import random
        vn = f"P-{random.randint(1000, 9999)}"
        patient = Patient(visit_number=vn, age=None, preferred_language="en")
        db.add(patient)
        await db.flush()
        session = TriageSession(id=session_id, patient_id=patient.id, session_number=1)
        db.add(session)
        await db.commit()
        await db.refresh(session)
    return session


def _detect_language(text: str) -> str:
    try:
        from langdetect import detect
        lang = detect(text)
        # Map common detected codes
        if lang in ("ur", "hi"):
            return "ur"
        if lang == "ar":
            return "ar"
        return "en"
    except Exception:
        return "en"


async def _get_conversation_history(session: TriageSession, db: AsyncSession) -> tuple:
    """Build OpenAI message history from DB, plus lookup dicts for the extractor."""
    result = await db.execute(
        select(ConversationMessage)
        .where(ConversationMessage.session_id == session.id)
        .order_by(ConversationMessage.created_at)
    )
    messages = result.scalars().all()
    history = []
    for m in messages:
        role = "user" if m.speaker == "patient" else "assistant"
        content = f"[{m.id}] {m.original_text}"
        history.append({"role": role, "content": content})

    msg_texts = {m.id: m.original_text for m in messages}
    translated_texts = {m.id: m.translated_text for m in messages if m.translated_text}
    session_start = session.started_at
    timestamps = {}
    for m in messages:
        if m.created_at and session_start:
            created = m.created_at if m.created_at.tzinfo else m.created_at.replace(tzinfo=timezone.utc)
            start = session_start if session_start.tzinfo else session_start.replace(tzinfo=timezone.utc)
            timestamps[m.id] = max(0.0, (created - start).total_seconds())
    return history, msg_texts, translated_texts, timestamps


async def _build_current_assessment(session_id: str, db: AsyncSession) -> ClinicalAssessment:
    """Reconstruct the ClinicalAssessment from stored facts."""
    from app.services.triage.models import ClinicalFact, Evidence, ChiefComplaint
    result = await db.execute(
        select(ClinicalFactORM).where(ClinicalFactORM.session_id == session_id)
    )
    facts_orm = result.scalars().all()

    assessment = ClinicalAssessment(session_id=session_id)

    for f in facts_orm:
        if f.is_hallucination_rejected:
            continue
        fact = ClinicalFact(
            fact_id=f.id,
            fact_type=f.fact_type,
            fact_key=f.fact_key,
            fact_value=f.fact_value,
            status=f.status,
            confidence=f.confidence,
            evidence=Evidence(
                message_id=f.evidence_message_id or "unknown",
                speaker="patient",
                original_text=f.evidence_text or "",
            ),
            source=f.source,
        )
        assessment.all_facts.append(fact)

    return assessment


async def _process_message(
    session: TriageSession,
    message: ConversationMessage,
    lang: str,
    db: AsyncSession,
    current_user: dict,
) -> dict:
    """Core pipeline: extract facts → guard → update assessment → check red flags."""

    history, msg_texts, translated_texts, timestamps = await _get_conversation_history(session, db)
    msg_texts[message.id] = message.original_text  # include current message
    if message.translated_text:
        translated_texts[message.id] = message.translated_text
    known_ids = set(msg_texts.keys())

    assessment = await _build_current_assessment(session.id, db)

    # LLM extraction
    conv_service = get_conversation_service()
    try:
        extraction = await conv_service.extract_and_respond(
            conversation_history=history,
            current_message_id=message.id,
            clinical_state=assessment,
            patient_language=lang,
        )
    except Exception as e:
        logger.error("LLM extraction failed: %s", e)
        await audit.log(db, AuditAction.LLM_FAILURE, session_id=session.id,
                        detail={"error": str(e)})
        return {
            "error": "extraction_failed",
            "next_question": "I'm having trouble. A nurse will assist you shortly.",
            "high_acuity_trigger": True,
        }

    if extraction.retrieved_sources:
        await audit.log(db, AuditAction.KNOWLEDGE_RETRIEVED, session_id=session.id,
                        detail={"sources": extraction.retrieved_sources})

    # Hallucination guard + merge
    extractor = get_fact_extractor()
    assessment, rejected_facts, new_conflicts = extractor.process_extraction(
        assessment, extraction, known_ids, msg_texts, translated_texts, timestamps,
    )

    # Persist new facts
    for fact in assessment.all_facts:
        existing = await db.execute(
            select(ClinicalFactORM).where(ClinicalFactORM.id == fact.fact_id)
        )
        if not existing.scalar_one_or_none():
            orm_fact = ClinicalFactORM(
                id=fact.fact_id,
                session_id=session.id,
                fact_type=fact.fact_type,
                fact_key=fact.fact_key,
                fact_value=fact.fact_value,
                status=fact.status,
                confidence=fact.confidence,
                evidence_message_id=fact.evidence.message_id,
                evidence_text=fact.evidence.original_text,
                is_contradicted=fact.is_contradicted,
                contradiction_detail=fact.contradiction_detail,
                source=fact.source,
            )
            db.add(orm_fact)

    # Persist + audit rejected facts (spec §34) — never silently discarded.
    for rf in rejected_facts:
        orm_rejected = ClinicalFactORM(
            session_id=session.id,
            fact_type=rf.fact_type,
            fact_key=rf.fact_key,
            fact_value=rf.fact_value,
            status=rf.status,
            confidence=rf.confidence,
            evidence_message_id=rf.evidence_message_id,
            evidence_text=msg_texts.get(rf.evidence_message_id, ""),
            is_hallucination_rejected=True,
            source="PATIENT_REPORTED",
        )
        db.add(orm_rejected)
        await audit.log(db, AuditAction.HALLUCINATION_REJECTED, session_id=session.id,
                        detail={"fact_key": rf.fact_key, "fact_value": rf.fact_value,
                                "confidence": rf.confidence})

    # Log conflicts
    for conflict in new_conflicts:
        await audit.log(db, AuditAction.CONTRADICTION_DETECTED, session_id=session.id,
                        detail={"field": conflict.field, "values": conflict.values})

    await db.commit()

    # Evaluate deterministic triage rules engine on updated assessment (spec §18/§45)
    from app.services.triage.engine import get_triage_engine, load_rules
    from app.services.triage.models import TriageColour as DomainTriageColour
    from app.models.models import TriageResult as TriageResultORM, TriageColour as ORMTriageColour

    rule_high_acuity = False
    rule_reason = None
    triage_res = None
    try:
        ruleset = load_rules()
        triage_engine = get_triage_engine()
        triage_res = triage_engine.evaluate(assessment, ruleset)
        if triage_res.colour in (DomainTriageColour.RED, DomainTriageColour.ORANGE):
            rule_high_acuity = True
            rule_reason = triage_res.triggered_rules[0].rule_description if triage_res.triggered_rules else "High acuity condition detected by deterministic rules"
    except Exception as e:
        logger.warning("Rules evaluation error during conversation processing: %s", e)

    is_high_acuity = rule_high_acuity or extraction.high_acuity_trigger
    acuity_reason = rule_reason or extraction.high_acuity_reason or "High acuity urgent finding"

    if is_high_acuity:
        session.status = "HIGH_ACUITY_INTERRUPTED"
        if triage_res:
            tr_orm = TriageResultORM(
                session_id=session.id,
                triage_level=triage_res.triage_level,
                colour=ORMTriageColour(triage_res.colour.value),
                category=triage_res.category.value,
                target_minutes=triage_res.target_assessment_minutes,
                triggered_rules=[r.model_dump() for r in triage_res.triggered_rules],
                rules_version=triage_res.rules_version,
                protocol=triage_res.protocol,
                ruleset_hash=triage_res.ruleset_hash,
                evaluated_at=triage_res.evaluated_at,
                ai_recommendation=ORMTriageColour(triage_res.colour.value),
                status="PENDING_REVIEW",
            )
            db.add(tr_orm)

        await audit.log(db, AuditAction.HIGH_ACUITY_TRIGGERED, session_id=session.id,
                        detail={"reason": acuity_reason, "deterministic_rule": rule_high_acuity})

    # Choose next question in patient's language
    if lang == "ur" and extraction.next_question_urdu:
        next_q = extraction.next_question_urdu
    elif lang == "ar" and extraction.next_question_arabic:
        next_q = extraction.next_question_arabic
    else:
        next_q = extraction.next_question

    # A detected contradiction or a low-confidence rejection must be asked about
    # explicitly — never silently resolved or dropped (spec §16/§17/§39).
    if new_conflicts:
        topic = new_conflicts[0].field.replace("_", " ")
        values = " / ".join(new_conflicts[0].values)
        next_q = CONFLICT_QUESTIONS.get(lang, CONFLICT_QUESTIONS["en"]).format(topic=topic, values=values)
    elif any(m.startswith("clarify:") for m in assessment.missing_information):
        topic = next(m for m in assessment.missing_information if m.startswith("clarify:")).split(":", 1)[1]
        next_q = CLARIFICATION_QUESTIONS.get(lang, CLARIFICATION_QUESTIONS["en"]).format(topic=topic.replace("_", " "))
        await audit.log(db, AuditAction.LOW_CONFIDENCE_CLARIFICATION, session_id=session.id,
                        detail={"topic": topic})

    # Save AI nurse response to DB so full conversation context is preserved for subsequent turns
    if next_q:
        ai_msg = ConversationMessage(
            id=msg_id(),
            session_id=session.id,
            speaker="ai_nurse",
            original_text=next_q,
            translated_text=extraction.next_question if lang != "en" else None,
            detected_language=lang,
        )
        db.add(ai_msg)

    await db.commit()

    return {
        "message_id": message.id,
        "detected_language": lang,
        "original_text": message.original_text,
        "translated_text": message.translated_text,
        "next_question": next_q,
        "next_question_en": extraction.next_question,
        "missing_information": assessment.missing_information,
        "conflicts": [c.model_dump() for c in assessment.conflicts],
        "high_acuity_trigger": is_high_acuity,
        "high_acuity_reason": acuity_reason,
        "conversation_complete": extraction.conversation_complete,
        "facts_extracted": len(assessment.all_facts),
        "facts_rejected": len(rejected_facts),
    }
