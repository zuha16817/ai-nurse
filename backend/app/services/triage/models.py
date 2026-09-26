"""
Pydantic domain models for clinical assessment and triage.

These are the core data structures that flow through the system:
  Conversation → ClinicalAssessment → TriageEngine → TriageResult
"""

from __future__ import annotations
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field
import uuid


def new_fact_id() -> str:
    return f"FACT-{uuid.uuid4().hex[:8].upper()}"


def new_evidence_id() -> str:
    return f"EVID-{uuid.uuid4().hex[:8].upper()}"


# ── Value states ───────────────────────────────────────────────────────────────

class ClinicalValueStatus(str, Enum):
    """Unknown information must NEVER be coerced to a negative finding."""
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    UNCERTAIN = "UNCERTAIN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SymptomStatus(str, Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    UNKNOWN = "UNKNOWN"
    UNCERTAIN = "UNCERTAIN"


# ── Evidence ───────────────────────────────────────────────────────────────────

class Evidence(BaseModel):
    evidence_id: str = Field(default_factory=new_evidence_id)
    message_id: str                          # must resolve to a real ConversationMessage
    speaker: str                             # "patient" | "ai_nurse" | "nurse"
    timestamp_seconds: Optional[float] = None
    original_text: str                       # original patient statement — never discarded
    translated_text: Optional[str] = None   # English normalisation


# ── Clinical Facts ─────────────────────────────────────────────────────────────

class ClinicalFact(BaseModel):
    """
    Every extracted clinical fact must carry evidence.
    Facts without evidence must be REJECTED (hallucination guard).
    """
    fact_id: str = Field(default_factory=new_fact_id)
    fact_type: str                           # SYMPTOM | ONSET | HISTORY | MEDICATION | VITAL
    fact_key: str                            # e.g. "breathing_difficulty"
    fact_value: str                          # e.g. "PRESENT"
    status: SymptomStatus = SymptomStatus.UNKNOWN
    confidence: Optional[float] = None
    evidence: Evidence                       # mandatory — no evidence → rejected
    source: str = "PATIENT_REPORTED"        # PATIENT_REPORTED | OBJECTIVELY_MEASURED
    is_contradicted: bool = False
    contradiction_detail: Optional[str] = None


# ── Chief Complaint ────────────────────────────────────────────────────────────

class ChiefComplaint(BaseModel):
    original: str
    normalized: Optional[str] = None
    confidence: float = 0.0
    category: Optional[str] = None          # breathing_problem | chest_discomfort | etc.


# ── Pain Assessment ────────────────────────────────────────────────────────────

class PainAssessment(BaseModel):
    present: SymptomStatus = SymptomStatus.UNKNOWN
    severity: Optional[int] = None          # 0-10
    location: Optional[str] = None
    character: Optional[str] = None         # sharp | dull | crushing | burning
    radiation: Optional[str] = None
    status: ClinicalValueStatus = ClinicalValueStatus.UNKNOWN


# ── Breathing Assessment ───────────────────────────────────────────────────────

class BreathingAssessment(BaseModel):
    difficulty: SymptomStatus = SymptomStatus.UNKNOWN
    rate: Optional[int] = None              # breaths per minute
    wheeze: SymptomStatus = SymptomStatus.UNKNOWN
    stridor: SymptomStatus = SymptomStatus.UNKNOWN
    status: ClinicalValueStatus = ClinicalValueStatus.UNKNOWN


# ── Consciousness ──────────────────────────────────────────────────────────────

class ConsciousnessAssessment(BaseModel):
    avpu: Optional[str] = None              # Alert | Voice | Pain | Unresponsive
    gcs: Optional[int] = None
    confusion: SymptomStatus = SymptomStatus.UNKNOWN
    status: ClinicalValueStatus = ClinicalValueStatus.UNKNOWN


# ── Bleeding ──────────────────────────────────────────────────────────────────

class BleedingAssessment(BaseModel):
    present: SymptomStatus = SymptomStatus.UNKNOWN
    site: Optional[str] = None
    severity: Optional[str] = None         # minor | moderate | severe | uncontrolled
    status: ClinicalValueStatus = ClinicalValueStatus.UNKNOWN


# ── Vital Signs (objective) ────────────────────────────────────────────────────

class ObjectiveVitalSigns(BaseModel):
    temperature: Optional[float] = None     # °C
    pulse: Optional[int] = None
    systolic_bp: Optional[int] = None
    diastolic_bp: Optional[int] = None
    respiratory_rate: Optional[int] = None
    spo2: Optional[float] = None            # %
    pain_score: Optional[int] = None        # 0-10
    gcs: Optional[int] = None
    avpu: Optional[str] = None
    entered_by: Optional[str] = None        # nurse username
    source: str = "OBJECTIVELY_MEASURED"


# ── Conflict ──────────────────────────────────────────────────────────────────

class ConflictRecord(BaseModel):
    field: str
    values: List[str]
    message_ids: List[str]
    detected_at: Optional[str] = None


# ── Full Clinical Assessment ───────────────────────────────────────────────────

class ClinicalAssessment(BaseModel):
    """
    Progressive clinical state built from the conversation.
    Unknown values remain UNKNOWN — never guessed.
    """
    session_id: str
    patient_age: Optional[int] = None
    patient_language: str = "en"
    pregnancy_status: str = "UNKNOWN"

    chief_complaint: Optional[ChiefComplaint] = None
    symptoms: List[ClinicalFact] = Field(default_factory=list)
    onset: Optional[str] = None
    onset_status: ClinicalValueStatus = ClinicalValueStatus.UNKNOWN

    pain: PainAssessment = Field(default_factory=PainAssessment)
    breathing: BreathingAssessment = Field(default_factory=BreathingAssessment)
    bleeding: BleedingAssessment = Field(default_factory=BleedingAssessment)
    consciousness: ConsciousnessAssessment = Field(default_factory=ConsciousnessAssessment)

    temperature: Optional[float] = None
    vital_signs: Optional[ObjectiveVitalSigns] = None

    medical_history: List[ClinicalFact] = Field(default_factory=list)
    medications: List[ClinicalFact] = Field(default_factory=list)
    allergies: List[ClinicalFact] = Field(default_factory=list)

    # Evidence and conflicts
    all_facts: List[ClinicalFact] = Field(default_factory=list)
    conflicts: List[ConflictRecord] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)

    # LLM extraction metadata
    extraction_confidence: float = 0.0
    rules_version: str = "1.0.0"


# ── LLM Structured Output Schema ──────────────────────────────────────────────

class LLMExtractedFact(BaseModel):
    """Schema that GPT-4o must return — validated before use."""
    fact_type: str
    fact_key: str
    fact_value: str
    status: SymptomStatus
    confidence: float
    evidence_message_id: str               # must be a real message ID


class LLMExtractionOutput(BaseModel):
    """
    Validated structured output from the LLM.
    Free text NEVER becomes a clinical fact directly.
    """
    facts: List[LLMExtractedFact]
    missing_information: List[str]
    conflicts_detected: List[Dict[str, Any]] = Field(default_factory=list)
    next_question: Optional[str] = None
    next_question_urdu: Optional[str] = None
    next_question_arabic: Optional[str] = None
    high_acuity_trigger: bool = False
    high_acuity_reason: Optional[str] = None
    conversation_complete: bool = False
    # Populated after the LLM call by the RAG layer (spec §28) — not requested from the
    # LLM itself, so retrieval provenance can't be fabricated by the model.
    retrieved_sources: List[Dict[str, Any]] = Field(default_factory=list)


# ── Triage Output ──────────────────────────────────────────────────────────────

class TriageColour(str, Enum):
    RED = "RED"
    ORANGE = "ORANGE"
    YELLOW = "YELLOW"
    GREEN = "GREEN"
    BLUE = "BLUE"
    UNKNOWN = "UNKNOWN"


class TriageCategory(str, Enum):
    IMMEDIATE = "IMMEDIATE"
    VERY_URGENT = "VERY_URGENT"
    URGENT = "URGENT"
    STANDARD = "STANDARD"
    NON_URGENT = "NON_URGENT"


COLOUR_TO_LEVEL = {
    TriageColour.RED: 1,
    TriageColour.ORANGE: 2,
    TriageColour.YELLOW: 3,
    TriageColour.GREEN: 4,
    TriageColour.BLUE: 5,
}

COLOUR_TO_MINUTES = {
    TriageColour.RED: 0,
    TriageColour.ORANGE: 10,
    TriageColour.YELLOW: 60,
    TriageColour.GREEN: 120,
    TriageColour.BLUE: 240,
}

COLOUR_TO_CATEGORY = {
    TriageColour.RED: TriageCategory.IMMEDIATE,
    TriageColour.ORANGE: TriageCategory.VERY_URGENT,
    TriageColour.YELLOW: TriageCategory.URGENT,
    TriageColour.GREEN: TriageCategory.STANDARD,
    TriageColour.BLUE: TriageCategory.NON_URGENT,
}


class TriggeredRule(BaseModel):
    rule_id: str
    rule_description: str
    evidence_ids: List[str]
    fact_ids: List[str]


class TriageResult(BaseModel):
    """
    Output of the deterministic triage engine.
    Same facts + same rules version = same result (deterministic).
    """
    triage_level: int
    colour: TriageColour
    category: TriageCategory
    target_assessment_minutes: int
    triggered_rules: List[TriggeredRule]
    rules_version: str
    protocol: str = "AI_NURSE_SYNTHETIC_PROTOTYPE"
    ruleset_hash: str = ""                  # SHA-256 of the rules YAML — proves which exact
                                             # rule content produced this result (spec §27)
    evaluated_at: str = ""                  # ISO-8601 timestamp, set by the engine
    is_high_acuity_interrupted: bool = False
    explanation: str = ""                   # human-readable summary
