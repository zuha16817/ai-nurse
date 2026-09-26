"""
Clinical Fact Extractor + Hallucination Guard.

Every clinical fact extracted by the LLM must:
1. Have a supporting message_id that exists in the conversation.
2. Have a non-empty evidence_text from that message.
3. Have confidence > threshold.

Facts that fail this check are REJECTED and logged.
"""

from __future__ import annotations
import logging
import re
import uuid
from typing import List, Set, Tuple, Optional

from app.services.triage.models import (
    ClinicalAssessment,
    ClinicalFact,
    Evidence,
    LLMExtractionOutput,
    LLMExtractedFact,
    ConflictRecord,
    SymptomStatus,
    ChiefComplaint,
    PainAssessment,
    BreathingAssessment,
    BleedingAssessment,
    ConsciousnessAssessment,
    ClinicalValueStatus,
)

logger = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.4  # Reject facts below this confidence

# Multilingual keyword map used to verify that a fact's cited evidence text actually
# supports the fact (spec §34). Citing a real message ID is not enough on its own —
# a hallucinated fact could point at a real message about something unrelated. This is
# a lightweight, explainable substring check (appropriate for a prototype guard), not a
# full NLI model — see docs/evaluation_report.md for its measured limitations.
FACT_KEY_KEYWORDS: dict[str, list[str]] = {
    "chest_pain": ["chest pain", "chest", "seene", "sadr", "sadar", "صدر"],
    "chest_discomfort": ["chest", "seene", "sadr", "صدر"],
    "breathing_difficulty": ["breath", "saans", "tanaffus", "تنفس", "سانس"],
    "shortness_of_breath": ["breath", "saans", "tanaffus", "تنفس", "سانس"],
    "wheeze": ["wheez"],
    "stridor": ["stridor"],
    "bleeding": ["bleed", "blood", "khoon", "دم", "خون"],
    "bleeding_severity": ["bleed", "blood", "khoon", "دم", "خون"],
    "consciousness_avpu": ["conscious", "respond", "unresponsive", "confus", "voice", "pain", "wake"],
    "confusion": ["confus", "disorient", "where am i"],
    "fever": ["fever", "bukhar", "humma", "temperature", "حمى", "بخار"],
    "temperature": ["fever", "temperature", "degree", "حمى", "بخار"],
    "headache": ["headache", "head", "sar dard", "suda", "صداع", "سر درد"],
    "abdominal_pain": ["stomach", "abdomen", "abdominal", "pet", "batn", "بطن", "پیٹ"],
    "injury": ["injury", "hurt", "fell", "fracture", "cut", "wound", "zakhm", "زخم"],
    "stroke_symptoms": ["face", "arm", "speech", "droop", "stroke", "weakness"],
    "anaphylaxis": ["swell", "throat", "allerg", "rash", "hives", "تورم", "حلق"],
    "general_weakness": ["weak", "tired", "fatigue", "dizzy", "kamzori", "کمزوری", "ضعف"],
    "administrative": ["checkup", "prescription", "certificate", "vaccin", "results", "renewal", "نسخہ", "شهادة"],
    "chronic_review": ["follow-up", "followup", "routine", "chronic", "review", "regular", "متابعة", "چیک اپ"],
    "onset": ["ago", "minute", "hour", "day", "today", "yesterday", "start", "began", "since",
              "duration", "morning", "suddenly", "منذ", "کل", "شروع", "اچانک"],
    "pain_severity": [],  # validated numerically below
}


_NON_SUBSTANTIVE_VALUES = {"present", "absent", "unknown", "uncertain", "true", "false", "yes", "no"}


def _is_substantive_value(fact_key: str, value: str) -> bool:
    """
    Is this fact_value actual distinguishing content (an onset time, a severity
    number, a location) rather than just a restatement of presence/absence?

    An LLM is not a controlled vocabulary: for a simple "is this symptom present"
    fact it might put "PRESENT" in fact_value on one turn and the symptom's own
    name (e.g. "leg cramps") on another. Comparing those raw strings for equality
    would flag that formatting inconsistency as a patient contradiction — it isn't
    one. Only compare fact_value when it actually carries information beyond "yes,
    this is present" (e.g. onset="yesterday" vs onset="one hour ago" IS meaningful).
    """
    v = (value or "").strip().lower()
    if not v or v in _NON_SUBSTANTIVE_VALUES:
        return False
    key_words = set(re.split(r"[\s_-]+", fact_key.lower()))
    value_words = set(re.split(r"[\s_-]+", v))
    if value_words and value_words.issubset(key_words):
        return False  # the value just echoes the key itself — not new information
    return True


def _fact_supported_by_text(fact_key: str, fact_value: str, text: str) -> bool:
    """
    Spec §34: FACT -> Supporting Patient Statement -> VALID; without support -> REJECT.

    A fabricated fact citing a REAL-but-unrelated message must still be caught —
    checking only that the message ID exists (as the previous guard did) is not enough.
    """
    if not text:
        return False
    text_lower = text.lower()

    # Numeric values (pain score, GCS, etc.) — accept if the literal number is present.
    if fact_value and str(fact_value).strip().isdigit() and str(fact_value) in text:
        return True

    keywords = FACT_KEY_KEYWORDS.get(fact_key)
    if keywords:
        return any(kw.lower() in text_lower for kw in keywords)

    # Unknown fact_key — fall back to checking the key's own words appear in the text.
    # This is what catches an arbitrary invented fact (e.g. "diabetes") citing text
    # that never mentions it. Split on ANY separator (space, underscore, hyphen) —
    # a schema-conformant LLM is free to return human-readable keys like
    # "abdominal cramp" rather than the "abdominal_cramp" style the keyword
    # dictionary above assumes; splitting on "_" alone would treat that whole
    # phrase as one unmatchable token and wrongly reject a valid fact.
    words = [w for w in re.split(r"[\s_-]+", fact_key) if len(w) >= 4]
    if not words:
        return True  # nothing meaningful to check against — don't over-reject
    return any(w.lower() in text_lower for w in words)


class HallucinationGuard:
    """
    Validates that every LLM-extracted fact has a real, textually-supporting message.

    Invariant: FACT → Supporting Patient Statement → VALID
               Without evidence → REJECT
    """

    def validate(
        self,
        extracted_facts: List[LLMExtractedFact],
        known_message_ids: Set[str],
        conversation_messages: dict,  # message_id -> text
    ) -> Tuple[List[LLMExtractedFact], List[LLMExtractedFact]]:
        """
        Returns (valid_facts, rejected_facts).
        """
        valid = []
        rejected = []

        for fact in extracted_facts:
            rejection_reason = None
            evidence_text = conversation_messages.get(fact.evidence_message_id, "")

            # Check 1: evidence message must exist
            if fact.evidence_message_id not in known_message_ids:
                rejection_reason = f"Message {fact.evidence_message_id!r} not found in conversation"

            # Check 2: confidence threshold
            elif fact.confidence < CONFIDENCE_THRESHOLD:
                rejection_reason = f"Confidence {fact.confidence:.2f} below threshold {CONFIDENCE_THRESHOLD}"

            # Check 3: the cited message text must actually support the fact —
            # citing a real message that has nothing to do with the fact is still a
            # hallucination.
            elif not _fact_supported_by_text(fact.fact_key, fact.fact_value, evidence_text):
                rejection_reason = (
                    f"Evidence text for {fact.evidence_message_id!r} does not appear "
                    f"to support fact_key={fact.fact_key!r}"
                )

            if rejection_reason:
                logger.warning(
                    "HALLUCINATION REJECTED: fact_key=%s, value=%s, reason=%s",
                    fact.fact_key, fact.fact_value, rejection_reason,
                )
                rejected.append(fact)
            else:
                valid.append(fact)

        if rejected:
            logger.warning(
                "%d/%d facts rejected by hallucination guard",
                len(rejected), len(extracted_facts),
            )

        return valid, rejected


class ClinicalFactExtractor:
    """
    Merges new LLM-extracted facts into the ClinicalAssessment.

    - Runs hallucination guard on every batch.
    - Detects contradictions.
    - Updates structured assessment fields.
    - Tracks all evidence.
    """

    def __init__(self):
        self.guard = HallucinationGuard()

    def process_extraction(
        self,
        assessment: ClinicalAssessment,
        extraction: LLMExtractionOutput,
        known_message_ids: Set[str],
        conversation_messages: dict,  # message_id -> original_text
        translated_messages: Optional[dict] = None,  # message_id -> English normalisation
        message_timestamps: Optional[dict] = None,   # message_id -> seconds since session start
    ) -> Tuple[ClinicalAssessment, List[LLMExtractedFact], List[ConflictRecord]]:
        """
        Merge extracted facts into the assessment, after the hallucination check.

        Returns (assessment, rejected_facts, new_conflicts_this_turn) — callers must not
        silently drop rejected_facts/new_conflicts: spec §34 requires rejections to be
        auditable, and §17 requires conflicts to trigger a clarification question rather
        than being resolved silently.
        """
        translated_messages = translated_messages or {}
        message_timestamps = message_timestamps or {}

        # 1. Hallucination guard
        valid_facts, rejected_facts = self.guard.validate(
            extraction.facts,
            known_message_ids,
            conversation_messages,
        )

        # 2. Convert to domain ClinicalFacts
        new_facts: List[ClinicalFact] = []
        for raw in valid_facts:
            evidence_text = conversation_messages.get(raw.evidence_message_id, "")
            fact = ClinicalFact(
                fact_type=raw.fact_type,
                fact_key=raw.fact_key,
                fact_value=raw.fact_value,
                status=raw.status,
                confidence=raw.confidence,
                evidence=Evidence(
                    message_id=raw.evidence_message_id,
                    speaker="patient",
                    original_text=evidence_text,
                    translated_text=translated_messages.get(raw.evidence_message_id),
                    timestamp_seconds=message_timestamps.get(raw.evidence_message_id),
                ),
                source="PATIENT_REPORTED",
            )
            new_facts.append(fact)

        # 3. Contradiction detection — never silently pick one value (spec §17)
        conflicts = self._detect_contradictions(assessment.all_facts, new_facts)
        for conflict in conflicts:
            assessment.conflicts.append(conflict)
            logger.warning("Contradiction detected: field=%s, values=%s", conflict.field, conflict.values)

        # 4. Mark contradicted facts (persisted downstream, never dropped)
        contradicted: dict = {c.field: c for c in conflicts}
        for fact in new_facts:
            conflict = contradicted.get(fact.fact_key)
            if conflict:
                fact.is_contradicted = True
                fact.contradiction_detail = f"Conflicting values reported: {', '.join(conflict.values)}"

        # 5. Merge into assessment
        assessment.all_facts.extend(new_facts)
        assessment.missing_information = list(extraction.missing_information)

        # Low-confidence rejections must prompt clarification, not silent omission
        # (spec §16/§39 "low extraction confidence"). Never treat a rejected fact
        # as a negative finding — just mark it as something to ask about again.
        for rf in rejected_facts:
            if rf.confidence is not None and rf.confidence < CONFIDENCE_THRESHOLD:
                marker = f"clarify:{rf.fact_key}"
                if marker not in assessment.missing_information:
                    assessment.missing_information.append(marker)

        # 6. Update structured fields from new facts
        self._update_structured_fields(assessment, new_facts)

        # 7. Update chief complaint if detected
        self._update_chief_complaint(assessment, new_facts, extraction)

        return assessment, rejected_facts, conflicts

    def _detect_contradictions(
        self,
        existing_facts: List[ClinicalFact],
        new_facts: List[ClinicalFact],
    ) -> List[ConflictRecord]:
        """Detect when the same field has been given conflicting values."""
        conflicts = []
        existing_by_key = {f.fact_key: f for f in existing_facts if f.status != SymptomStatus.UNKNOWN}

        for new_fact in new_facts:
            key = new_fact.fact_key
            if key not in existing_by_key:
                continue
            old_fact = existing_by_key[key]
            if new_fact.status in (SymptomStatus.UNKNOWN, SymptomStatus.UNCERTAIN):
                continue

            # A genuine flip between reported present/absent for the same symptom
            # is always worth flagging, regardless of how fact_value is phrased.
            status_conflict = (
                old_fact.status != new_fact.status
                and old_fact.status not in (SymptomStatus.UNKNOWN, SymptomStatus.UNCERTAIN)
            )
            # Beyond that, only compare fact_value when both sides carry actual
            # distinguishing content (see _is_substantive_value) — otherwise this
            # just flags the LLM's own inconsistent phrasing as a patient contradiction.
            value_conflict = (
                old_fact.fact_value != new_fact.fact_value
                and _is_substantive_value(key, old_fact.fact_value)
                and _is_substantive_value(key, new_fact.fact_value)
            )

            if status_conflict or value_conflict:
                conflicts.append(ConflictRecord(
                    field=key,
                    values=[old_fact.fact_value, new_fact.fact_value],
                    message_ids=[
                        old_fact.evidence.message_id,
                        new_fact.evidence.message_id,
                    ],
                ))

        return conflicts

    def _update_structured_fields(
        self,
        assessment: ClinicalAssessment,
        new_facts: List[ClinicalFact],
    ) -> None:
        """Update the high-level structured fields from new facts."""
        for fact in new_facts:
            key = fact.fact_key
            val = fact.fact_value

            # Pain
            if key == "pain_severity":
                try:
                    assessment.pain.severity = int(val)
                    assessment.pain.present = SymptomStatus.PRESENT
                    assessment.pain.status = ClinicalValueStatus.KNOWN
                except ValueError:
                    pass
            elif key == "chest_pain" and fact.status == SymptomStatus.PRESENT:
                assessment.pain.present = SymptomStatus.PRESENT

            # Breathing
            elif key == "breathing_difficulty":
                assessment.breathing.difficulty = fact.status
                assessment.breathing.status = ClinicalValueStatus.KNOWN
            elif key == "wheeze":
                assessment.breathing.wheeze = fact.status
            elif key == "stridor":
                assessment.breathing.stridor = fact.status

            # Bleeding
            elif key == "bleeding":
                assessment.bleeding.present = fact.status
                if assessment.bleeding.present == SymptomStatus.PRESENT:
                    assessment.bleeding.status = ClinicalValueStatus.KNOWN
            elif key == "bleeding_severity":
                assessment.bleeding.severity = val

            # Consciousness
            elif key == "consciousness_avpu":
                assessment.consciousness.avpu = val
                assessment.consciousness.status = ClinicalValueStatus.KNOWN
            elif key == "confusion":
                assessment.consciousness.confusion = fact.status

            # Temperature
            elif key == "temperature":
                try:
                    assessment.temperature = float(val)
                except ValueError:
                    pass

            # Onset
            elif key == "onset":
                assessment.onset = val
                assessment.onset_status = ClinicalValueStatus.KNOWN

    def _update_chief_complaint(
        self,
        assessment: ClinicalAssessment,
        new_facts: List[ClinicalFact],
        extraction: LLMExtractionOutput,
    ) -> None:
        """Update chief complaint category if a complaint-type fact is found."""
        COMPLAINT_MAP = {
            "chest_pain": "chest_discomfort",
            "chest_discomfort": "chest_discomfort",
            "breathing_difficulty": "breathing_problem",
            "shortness_of_breath": "breathing_problem",
            "abdominal_pain": "abdominal_complaint",
            "headache": "headache",
            "fever": "fever",
            "bleeding": "bleeding",
            "injury": "injury",
            "stroke_symptoms": "neurological_symptoms",
            "general_weakness": "general_weakness",
            "allergy": "allergic_symptoms",
            "anaphylaxis": "allergic_symptoms",
            "chronic_review": "chronic_review",
            "administrative": "administrative",
            "prescription": "administrative",
            "checkup": "administrative",
            "certificate": "administrative",
            "routine_review": "chronic_review",
            "followup": "chronic_review",
        }

        for fact in new_facts:
            if fact.fact_key in COMPLAINT_MAP and fact.status == SymptomStatus.PRESENT:
                if assessment.chief_complaint is None:
                    assessment.chief_complaint = ChiefComplaint(
                        original=fact.evidence.original_text,
                        normalized=fact.fact_key.replace("_", " "),
                        confidence=fact.confidence or 0.8,
                        category=COMPLAINT_MAP[fact.fact_key],
                    )
                elif assessment.chief_complaint.category is None:
                    assessment.chief_complaint.category = COMPLAINT_MAP[fact.fact_key]


def get_fact_extractor() -> ClinicalFactExtractor:
    return ClinicalFactExtractor()
