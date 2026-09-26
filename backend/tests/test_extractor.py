"""
ClinicalFactExtractor tests.

Covers behaviour that HallucinationGuard tests and TriageEngine tests don't:
contradiction detection/persistence (spec §17), translation propagation
(spec §7/§15), and low-confidence rejections turning into a clarification
request rather than being silently dropped (spec §16/§39).
"""

import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.extraction.extractor import ClinicalFactExtractor
from app.services.triage.models import (
    ClinicalAssessment, LLMExtractedFact, LLMExtractionOutput, SymptomStatus,
)


def make_output(*facts: LLMExtractedFact, missing=None) -> LLMExtractionOutput:
    return LLMExtractionOutput(
        facts=list(facts),
        missing_information=missing or [],
        next_question="Next?",
    )


@pytest.fixture
def extractor():
    return ClinicalFactExtractor()


@pytest.fixture
def known_messages():
    return {"MSG-001", "MSG-002"}


class TestContradictionDetection:
    def test_conflicting_onset_values_detected_and_flagged(self, extractor, known_messages):
        assessment = ClinicalAssessment(session_id="S1")

        # Turn 1: "yesterday"
        turn1 = make_output(LLMExtractedFact(
            fact_type="ONSET", fact_key="onset", fact_value="yesterday",
            status=SymptomStatus.PRESENT, confidence=0.9, evidence_message_id="MSG-001",
        ))
        assessment, rejected1, conflicts1 = extractor.process_extraction(
            assessment, turn1, known_messages, {"MSG-001": "It started yesterday.", "MSG-002": "Actually one hour ago."},
        )
        assert conflicts1 == []
        assert rejected1 == []

        # Turn 2: contradicts turn 1
        turn2 = make_output(LLMExtractedFact(
            fact_type="ONSET", fact_key="onset", fact_value="one hour ago",
            status=SymptomStatus.PRESENT, confidence=0.9, evidence_message_id="MSG-002",
        ))
        assessment, rejected2, conflicts2 = extractor.process_extraction(
            assessment, turn2, known_messages, {"MSG-001": "It started yesterday.", "MSG-002": "Actually one hour ago."},
        )

        assert len(conflicts2) == 1
        assert conflicts2[0].field == "onset"
        assert set(conflicts2[0].values) == {"yesterday", "one hour ago"}

        # Must never silently drop the earlier value — both facts stay in the record.
        onset_facts = [f for f in assessment.all_facts if f.fact_key == "onset"]
        assert len(onset_facts) == 2

        # The new (contradicting) fact must be flagged, not silently merged.
        new_fact = next(f for f in onset_facts if f.fact_value == "one hour ago")
        assert new_fact.is_contradicted is True
        assert "yesterday" in new_fact.contradiction_detail
        assert "one hour ago" in new_fact.contradiction_detail

    def test_inconsistent_llm_phrasing_of_the_same_finding_is_not_a_contradiction(self, extractor, known_messages):
        """
        Regression test: an LLM extracting the same underlying fact across turns may
        phrase fact_value inconsistently — e.g. "leg cramps" on one turn, "PRESENT"
        on the next — without the patient having said anything contradictory. This
        must never be flagged as a conflict, or the conversation loops forever
        asking the patient to resolve a "contradiction" that doesn't exist.
        """
        assessment = ClinicalAssessment(session_id="S7")
        turn1 = make_output(LLMExtractedFact(
            fact_type="SYMPTOM", fact_key="leg_cramps", fact_value="leg cramps",
            status=SymptomStatus.PRESENT, confidence=0.9, evidence_message_id="MSG-001",
        ))
        assessment, _, conflicts1 = extractor.process_extraction(
            assessment, turn1, known_messages, {"MSG-001": "I have leg cramps.", "MSG-002": "In my calf, started 2 days ago."},
        )
        assert conflicts1 == []

        turn2 = make_output(LLMExtractedFact(
            fact_type="SYMPTOM", fact_key="leg_cramps", fact_value="PRESENT",
            status=SymptomStatus.PRESENT, confidence=0.9, evidence_message_id="MSG-002",
        ))
        _, _, conflicts2 = extractor.process_extraction(
            assessment, turn2, known_messages, {"MSG-001": "I have leg cramps.", "MSG-002": "In my calf, started 2 days ago."},
        )
        assert conflicts2 == []

    def test_genuine_status_flip_is_still_caught(self, extractor, known_messages):
        """A real reversal (patient says present, then says absent) must still be flagged,
        even though this is exactly the kind of case the fix above must not suppress."""
        assessment = ClinicalAssessment(session_id="S8")
        turn1 = make_output(LLMExtractedFact(
            fact_type="SYMPTOM", fact_key="chest_pain", fact_value="PRESENT",
            status=SymptomStatus.PRESENT, confidence=0.9, evidence_message_id="MSG-001",
        ))
        assessment, _, _ = extractor.process_extraction(
            assessment, turn1, known_messages, {"MSG-001": "I have chest pain.", "MSG-002": "Actually no chest pain."},
        )
        turn2 = make_output(LLMExtractedFact(
            fact_type="SYMPTOM", fact_key="chest_pain", fact_value="ABSENT",
            status=SymptomStatus.ABSENT, confidence=0.9, evidence_message_id="MSG-002",
        ))
        _, _, conflicts2 = extractor.process_extraction(
            assessment, turn2, known_messages, {"MSG-001": "I have chest pain.", "MSG-002": "Actually no chest pain."},
        )
        assert len(conflicts2) == 1
        assert conflicts2[0].field == "chest_pain"

    def test_unknown_status_does_not_count_as_a_contradiction(self, extractor, known_messages):
        assessment = ClinicalAssessment(session_id="S2")
        turn1 = make_output(LLMExtractedFact(
            fact_type="ONSET", fact_key="onset", fact_value="yesterday",
            status=SymptomStatus.PRESENT, confidence=0.9, evidence_message_id="MSG-001",
        ))
        assessment, _, _ = extractor.process_extraction(
            assessment, turn1, known_messages, {"MSG-001": "yesterday"},
        )
        turn2 = make_output(LLMExtractedFact(
            fact_type="ONSET", fact_key="onset", fact_value="not sure",
            status=SymptomStatus.UNCERTAIN, confidence=0.5, evidence_message_id="MSG-002",
        ))
        _, _, conflicts = extractor.process_extraction(
            assessment, turn2, known_messages, {"MSG-001": "yesterday", "MSG-002": "not sure"},
        )
        assert conflicts == []


class TestTranslationPropagation:
    def test_translated_text_attached_to_evidence(self, extractor, known_messages):
        assessment = ClinicalAssessment(session_id="S3")
        output = make_output(LLMExtractedFact(
            fact_type="SYMPTOM", fact_key="chest_pain", fact_value="PRESENT",
            status=SymptomStatus.PRESENT, confidence=0.9, evidence_message_id="MSG-001",
        ))
        assessment, _, _ = extractor.process_extraction(
            assessment, output, known_messages,
            conversation_messages={"MSG-001": "Seene mein dard hai."},
            translated_messages={"MSG-001": "There is chest pain."},
        )
        fact = assessment.all_facts[0]
        assert fact.evidence.original_text == "Seene mein dard hai."
        assert fact.evidence.translated_text == "There is chest pain."

    def test_original_text_never_discarded_when_no_translation_available(self, extractor, known_messages):
        assessment = ClinicalAssessment(session_id="S4")
        output = make_output(LLMExtractedFact(
            fact_type="SYMPTOM", fact_key="fever", fact_value="PRESENT",
            status=SymptomStatus.PRESENT, confidence=0.9, evidence_message_id="MSG-001",
        ))
        assessment, _, _ = extractor.process_extraction(
            assessment, output, known_messages,
            conversation_messages={"MSG-001": "I have a fever."},
        )
        fact = assessment.all_facts[0]
        assert fact.evidence.original_text == "I have a fever."
        assert fact.evidence.translated_text is None


class TestLowConfidenceClarification:
    def test_low_confidence_rejection_produces_clarification_marker(self, extractor, known_messages):
        """
        A fact rejected only for low confidence must not be silently dropped —
        it should surface as something to ask about again (spec §16/§39), distinct
        from missing-message rejections which are pure hallucinations.
        """
        assessment = ClinicalAssessment(session_id="S5")
        output = make_output(LLMExtractedFact(
            fact_type="SYMPTOM", fact_key="dizziness", fact_value="PRESENT",
            status=SymptomStatus.PRESENT, confidence=0.1, evidence_message_id="MSG-001",
        ))
        assessment, rejected, _ = extractor.process_extraction(
            assessment, output, known_messages, {"MSG-001": "I feel a bit dizzy maybe."},
        )
        assert len(rejected) == 1
        assert "clarify:dizziness" in assessment.missing_information

    def test_missing_message_rejection_does_not_produce_clarification_marker(self, extractor, known_messages):
        """A pure hallucination (fabricated message ID) is a rejection, not a
        'please repeat yourself' clarification — the two must not be conflated."""
        assessment = ClinicalAssessment(session_id="S6")
        output = make_output(LLMExtractedFact(
            fact_type="SYMPTOM", fact_key="diabetes", fact_value="PRESENT",
            status=SymptomStatus.PRESENT, confidence=0.9, evidence_message_id="MSG-INVENTED",
        ))
        assessment, rejected, _ = extractor.process_extraction(
            assessment, output, known_messages, {"MSG-001": "I have chest pain."},
        )
        assert len(rejected) == 1
        assert not any(m.startswith("clarify:") for m in assessment.missing_information)
