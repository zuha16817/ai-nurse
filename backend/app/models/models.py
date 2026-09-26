"""
SQLAlchemy ORM models.

All clinical data tables for the AI Nurse system.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Integer, Float, Boolean,
    DateTime, ForeignKey, JSON, Text, Enum as SAEnum
)
from sqlalchemy.orm import relationship
from app.models.database import Base
import enum


def utcnow():
    return datetime.now(timezone.utc)


def new_id():
    return str(uuid.uuid4())


# ── Enums ─────────────────────────────────────────────────────────────────────

class TriageColour(str, enum.Enum):
    RED = "RED"
    ORANGE = "ORANGE"
    YELLOW = "YELLOW"
    GREEN = "GREEN"
    BLUE = "BLUE"
    UNKNOWN = "UNKNOWN"


class FactStatus(str, enum.Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"
    UNCERTAIN = "UNCERTAIN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class UserRole(str, enum.Enum):
    PATIENT = "patient"
    NURSE = "nurse"
    ADMIN = "admin"


# ── Users ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=new_id)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(SAEnum(UserRole), nullable=False, default=UserRole.NURSE)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)


# ── Patients ──────────────────────────────────────────────────────────────────

class Patient(Base):
    __tablename__ = "patients"

    id = Column(String, primary_key=True, default=new_id)
    visit_number = Column(String, unique=True, index=True)  # e.g. P-1032
    age = Column(Integer, nullable=True)
    biological_sex = Column(String, nullable=True)          # M / F / OTHER / UNKNOWN
    preferred_language = Column(String, default="en")       # en / ur / ar
    arrival_time = Column(DateTime(timezone=True), default=utcnow)
    arrival_method = Column(String, nullable=True)          # walk-in / ambulance / etc.
    pregnancy_status = Column(String, default="UNKNOWN")    # PREGNANT / NOT_PREGNANT / UNKNOWN / NA
    is_synthetic = Column(Boolean, default=False)           # for evaluation dataset
    created_at = Column(DateTime(timezone=True), default=utcnow)

    sessions = relationship("TriageSession", back_populates="patient")


# ── Triage Sessions ───────────────────────────────────────────────────────────

class TriageSession(Base):
    __tablename__ = "triage_sessions"

    id = Column(String, primary_key=True, default=new_id)
    patient_id = Column(String, ForeignKey("patients.id"), nullable=False)
    session_number = Column(Integer, default=1)             # increments on re-triage
    started_at = Column(DateTime(timezone=True), default=utcnow)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, default="IN_PROGRESS")          # IN_PROGRESS | AWAITING_REVIEW | COMPLETED

    patient = relationship("Patient", back_populates="sessions")
    messages = relationship("ConversationMessage", back_populates="session", order_by="ConversationMessage.created_at")
    clinical_facts = relationship("ClinicalFact", back_populates="session")
    triage_results = relationship("TriageResult", back_populates="session", order_by="TriageResult.created_at")
    vital_signs = relationship("VitalSigns", back_populates="session")
    audit_logs = relationship("AuditLog", back_populates="session", order_by="AuditLog.created_at")


# ── Conversation Messages ─────────────────────────────────────────────────────

class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(String, primary_key=True, default=new_id)   # MSG-xxx
    session_id = Column(String, ForeignKey("triage_sessions.id"), nullable=False)
    speaker = Column(String, nullable=False)                 # "patient" | "ai_nurse"
    original_text = Column(Text, nullable=False)             # never discarded
    translated_text = Column(Text, nullable=True)            # normalised English
    detected_language = Column(String, nullable=True)        # ISO 639-1
    audio_file_path = Column(String, nullable=True)          # path to original audio
    stt_transcript = Column(Text, nullable=True)             # raw STT output
    created_at = Column(DateTime(timezone=True), default=utcnow)
    timestamp_seconds = Column(Float, nullable=True)         # seconds from session start

    session = relationship("TriageSession", back_populates="messages")


# ── Clinical Facts ────────────────────────────────────────────────────────────

class ClinicalFact(Base):
    __tablename__ = "clinical_facts"

    id = Column(String, primary_key=True, default=new_id)   # FACT-xxx
    session_id = Column(String, ForeignKey("triage_sessions.id"), nullable=False)
    fact_type = Column(String, nullable=False)               # SYMPTOM | HISTORY | MEDICATION | etc.
    fact_key = Column(String, nullable=False)                # e.g. "breathing_difficulty"
    fact_value = Column(String, nullable=False)              # e.g. "PRESENT"
    status = Column(SAEnum(FactStatus), default=FactStatus.UNKNOWN)
    confidence = Column(Float, nullable=True)
    evidence_message_id = Column(String, ForeignKey("conversation_messages.id"), nullable=True)
    evidence_text = Column(Text, nullable=True)              # exact quote from patient
    is_hallucination_rejected = Column(Boolean, default=False)
    is_contradicted = Column(Boolean, default=False)
    contradiction_detail = Column(Text, nullable=True)
    source = Column(String, default="PATIENT_REPORTED")      # PATIENT_REPORTED | OBJECTIVELY_MEASURED
    created_at = Column(DateTime(timezone=True), default=utcnow)

    session = relationship("TriageSession", back_populates="clinical_facts")


# ── Vital Signs ───────────────────────────────────────────────────────────────

class VitalSigns(Base):
    __tablename__ = "vital_signs"

    id = Column(String, primary_key=True, default=new_id)
    session_id = Column(String, ForeignKey("triage_sessions.id"), nullable=False)
    temperature = Column(Float, nullable=True)               # °C
    pulse = Column(Integer, nullable=True)                   # bpm
    systolic_bp = Column(Integer, nullable=True)
    diastolic_bp = Column(Integer, nullable=True)
    respiratory_rate = Column(Integer, nullable=True)        # breaths/min
    spo2 = Column(Float, nullable=True)                      # %
    pain_score = Column(Integer, nullable=True)              # 0-10
    gcs = Column(Integer, nullable=True)                     # Glasgow Coma Scale
    avpu = Column(String, nullable=True)                     # Alert/Voice/Pain/Unresponsive
    entered_by = Column(String, nullable=True)               # nurse username
    recorded_at = Column(DateTime(timezone=True), default=utcnow)

    session = relationship("TriageSession", back_populates="vital_signs")


# ── Triage Results ────────────────────────────────────────────────────────────

class TriageResult(Base):
    __tablename__ = "triage_results"

    id = Column(String, primary_key=True, default=new_id)
    session_id = Column(String, ForeignKey("triage_sessions.id"), nullable=False)
    triage_level = Column(Integer, nullable=False)           # 1-5
    colour = Column(SAEnum(TriageColour), nullable=False)
    category = Column(String, nullable=False)                # IMMEDIATE | VERY_URGENT | etc.
    target_minutes = Column(Integer, nullable=False)
    triggered_rules = Column(JSON, nullable=False, default=list)  # [{ruleId, evidenceIds}]
    rules_version = Column(String, nullable=False)           # e.g. "1.0.0"
    protocol = Column(String, nullable=True)                 # e.g. "AI_NURSE_SYNTHETIC_PROTOTYPE"
    ruleset_hash = Column(String, nullable=True)              # SHA-256 of the exact rules YAML used
    evaluated_at = Column(String, nullable=True)              # ISO-8601, set by the engine
    ai_recommendation = Column(SAEnum(TriageColour), nullable=True)

    # Human-in-the-loop
    clinician_decision = Column(SAEnum(TriageColour), nullable=True)
    override_reason = Column(Text, nullable=True)
    reviewed_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    is_override = Column(Boolean, default=False)
    status = Column(String, default="PENDING_REVIEW")        # PENDING_REVIEW | CONFIRMED | OVERRIDDEN

    created_at = Column(DateTime(timezone=True), default=utcnow)

    session = relationship("TriageSession", back_populates="triage_results")


# ── Audit Logs ────────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=new_id)
    session_id = Column(String, ForeignKey("triage_sessions.id"), nullable=True)
    actor = Column(String, nullable=True)                    # username or "system"
    action = Column(String, nullable=False)                  # e.g. "TRIAGE_COMPUTED"
    detail = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    session = relationship("TriageSession", back_populates="audit_logs")
