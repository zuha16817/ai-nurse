"""
Hallucination Guard Tests.

Every clinical fact must have a supporting message ID.
Facts without evidence must be rejected.
"""

import pytest
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.services.extraction.extractor import HallucinationGuard
from app.services.triage.models import LLMExtractedFact, SymptomStatus


def make_extracted_fact(key: str, value: str, msg_id: str, confidence: float = 0.9) -> LLMExtractedFact:
    return LLMExtractedFact(
        fact_type="SYMPTOM",
        fact_key=key,
        fact_value=value,
        status=SymptomStatus.PRESENT,
        confidence=confidence,
        evidence_message_id=msg_id,
    )


@pytest.fixture
def guard():
    return HallucinationGuard()


@pytest.fixture
def known_messages():
    return {"MSG-001", "MSG-002", "MSG-003"}


@pytest.fixture
def conversation_texts():
    return {
        "MSG-001": "I have chest pain.",
        "MSG-002": "It started 20 minutes ago.",
        "MSG-003": "I'm having trouble breathing.",
    }


class TestHallucinationGuard:

    def test_valid_fact_passes(self, guard, known_messages, conversation_texts):
        fact = make_extracted_fact("chest_pain", "PRESENT", "MSG-001")
        valid, rejected = guard.validate([fact], known_messages, conversation_texts)
        assert len(valid) == 1
        assert len(rejected) == 0

    def test_nonexistent_message_id_rejected(self, guard, known_messages, conversation_texts):
        fact = make_extracted_fact("diabetes", "PRESENT", "MSG-FAKE-999")
        valid, rejected = guard.validate([fact], known_messages, conversation_texts)
        assert len(valid) == 0
        assert len(rejected) == 1

    def test_low_confidence_rejected(self, guard, known_messages, conversation_texts):
        fact = make_extracted_fact("chest_pain", "PRESENT", "MSG-001", confidence=0.2)
        valid, rejected = guard.validate([fact], known_messages, conversation_texts)
        assert len(valid) == 0
        assert len(rejected) == 1

    def test_multiple_facts_mixed(self, guard, known_messages, conversation_texts):
        facts = [
            make_extracted_fact("chest_pain", "PRESENT", "MSG-001", confidence=0.95),  # valid
            make_extracted_fact("breathing_difficulty", "PRESENT", "MSG-003", confidence=0.9),  # valid
            make_extracted_fact("diabetes", "PRESENT", "MSG-FAKE", confidence=0.9),  # rejected
            make_extracted_fact("hypertension", "PRESENT", "MSG-001", confidence=0.1),  # rejected (low conf)
        ]
        valid, rejected = guard.validate(facts, known_messages, conversation_texts)
        assert len(valid) == 2
        assert len(rejected) == 2

    def test_empty_facts_list(self, guard, known_messages, conversation_texts):
        valid, rejected = guard.validate([], known_messages, conversation_texts)
        assert valid == []
        assert rejected == []

    def test_all_facts_valid(self, guard, known_messages, conversation_texts):
        facts = [
            make_extracted_fact("chest_pain", "PRESENT", "MSG-001"),
            make_extracted_fact("onset", "20 minutes ago", "MSG-002"),
            make_extracted_fact("breathing_difficulty", "PRESENT", "MSG-003"),
        ]
        valid, rejected = guard.validate(facts, known_messages, conversation_texts)
        assert len(valid) == 3
        assert len(rejected) == 0

    def test_hallucination_example_from_spec(self, guard, known_messages, conversation_texts):
        """
        Spec §34 example:
        If the model says "Patient has diabetes" but diabetes was never reported → REJECTED.
        """
        diabetes_fact = make_extracted_fact("diabetes", "PRESENT", "MSG-INVENTED")
        valid, rejected = guard.validate([diabetes_fact], known_messages, conversation_texts)
        assert len(rejected) == 1
        assert len(valid) == 0

    def test_fabricated_fact_citing_unrelated_real_message_rejected(self, guard, known_messages, conversation_texts):
        """
        A hallucinated fact can cite a REAL message ID that has nothing to do with it.
        Checking only that the message exists (the old guard's only check) would let
        this through. The guard must also verify the message TEXT supports the fact.
        """
        # MSG-001 = "I have chest pain." - nothing about diabetes.
        diabetes_fact = make_extracted_fact("diabetes", "PRESENT", "MSG-001")
        valid, rejected = guard.validate([diabetes_fact], known_messages, conversation_texts)
        assert len(rejected) == 1
        assert len(valid) == 0

    def test_multiword_fact_key_with_space_is_still_matched(self, guard, known_messages, conversation_texts):
        """
        Regression test: a schema-conformant LLM is free to return human-readable
        fact keys like "abdominal cramp" (a space, not an underscore). The keyword
        fallback must split on whitespace too, or a real word like "cramp" never
        gets checked and a genuinely valid fact is wrongly rejected as a hallucination.
        """
        fact = make_extracted_fact("abdominal cramp", "bad", "MSG-001")  # MSG-001 = "I have chest pain."
        # Use text that actually mentions "cramp" so this proves the split, not the dictionary.
        texts = {**conversation_texts, "MSG-001": "I have a bad stomach cramp."}
        valid, rejected = guard.validate([fact], known_messages, texts)
        assert len(valid) == 1
        assert len(rejected) == 0

    def test_valid_fact_with_genuinely_supporting_text_still_passes(self, guard, known_messages, conversation_texts):
        """The content check must not be so strict that it rejects real, well-evidenced facts."""
        facts = [
            make_extracted_fact("chest_pain", "PRESENT", "MSG-001"),
            make_extracted_fact("onset", "20 minutes ago", "MSG-002"),
            make_extracted_fact("breathing_difficulty", "PRESENT", "MSG-003"),
        ]
        valid, rejected = guard.validate(facts, known_messages, conversation_texts)
        assert len(valid) == 3
        assert len(rejected) == 0
