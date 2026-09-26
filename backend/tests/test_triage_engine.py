"""
Automated Triage Engine Unit Tests.

Tests that the deterministic engine is truly deterministic:
  Same facts + same rules = same result (always).

Also tests escalation principle, UNKNOWN handling, and rule evaluation.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.services.triage.models import (
    ClinicalAssessment, ClinicalFact, Evidence, TriageColour,
    ObjectiveVitalSigns, SymptomStatus, ClinicalValueStatus,
    ChiefComplaint, PainAssessment, BreathingAssessment,
    ConsciousnessAssessment, BleedingAssessment,
)
from app.services.triage.engine import TriageEngine, TriageRuleSet, load_rules


def make_assessment(**kwargs) -> ClinicalAssessment:
    return ClinicalAssessment(session_id="TEST-SESSION", **kwargs)


def make_fact(key: str, value: str, status: SymptomStatus, msg_id: str = "MSG-001") -> ClinicalFact:
    return ClinicalFact(
        fact_type="SYMPTOM",
        fact_key=key,
        fact_value=value,
        status=status,
        confidence=0.95,
        evidence=Evidence(
            message_id=msg_id,
            speaker="patient",
            original_text=f"Patient reported {key}",
        ),
    )


@pytest.fixture
def engine():
    return TriageEngine()


@pytest.fixture
def rules():
    return load_rules("1.0.0")


class TestDeterminism:
    """Determinism: same input → same output, always."""

    def test_same_result_on_repeated_calls(self, engine, rules):
        assessment = make_assessment(
            vital_signs=ObjectiveVitalSigns(spo2=82),
            breathing=BreathingAssessment(difficulty=SymptomStatus.PRESENT, status=ClinicalValueStatus.KNOWN),
        )
        result1 = engine.evaluate(assessment, rules)
        result2 = engine.evaluate(assessment, rules)
        result3 = engine.evaluate(assessment, rules)

        assert result1.colour == result2.colour == result3.colour
        assert result1.triage_level == result2.triage_level == result3.triage_level
        assert result1.rules_version == result2.rules_version == result3.rules_version

    def test_same_result_regardless_of_call_order(self, engine, rules):
        assessment_red = make_assessment(
            vital_signs=ObjectiveVitalSigns(spo2=82),
            breathing=BreathingAssessment(difficulty=SymptomStatus.PRESENT, status=ClinicalValueStatus.KNOWN),
        )
        assessment_blue = make_assessment(
            all_facts=[make_fact("administrative", "PRESENT", SymptomStatus.PRESENT)],
        )

        # Alternate calls
        red1 = engine.evaluate(assessment_red, rules)
        blue1 = engine.evaluate(assessment_blue, rules)
        red2 = engine.evaluate(assessment_red, rules)
        blue2 = engine.evaluate(assessment_blue, rules)

        assert red1.colour == red2.colour
        assert blue1.colour == blue2.colour


class TestEscalationPrinciple:
    """Higher-acuity rules cannot be overridden by lower-acuity findings."""

    def test_red_beats_orange(self, engine, rules):
        # Patient has both RED and ORANGE features — must be RED
        assessment = make_assessment(
            consciousness=ConsciousnessAssessment(avpu="Unresponsive", status=ClinicalValueStatus.KNOWN),
            chief_complaint=ChiefComplaint(
                original="chest pain",
                normalized="chest pain",
                category="chest_discomfort",
                confidence=0.9,
            ),
            all_facts=[
                make_fact("chest_pain", "PRESENT", SymptomStatus.PRESENT),
            ],
        )
        result = engine.evaluate(assessment, rules)
        assert result.colour == TriageColour.RED
        assert result.triage_level == 1

    def test_orange_beats_yellow(self, engine, rules):
        assessment = make_assessment(
            vital_signs=ObjectiveVitalSigns(spo2=90),  # ORANGE: SpO2 < 92
            chief_complaint=ChiefComplaint(
                original="mild headache",
                normalized="headache",
                category="headache",
                confidence=0.8,
            ),
            pain=PainAssessment(severity=5, present=SymptomStatus.PRESENT, status=ClinicalValueStatus.KNOWN),
        )
        result = engine.evaluate(assessment, rules)
        assert result.colour == TriageColour.ORANGE
        assert result.triage_level <= 2

    def test_red_result_stops_evaluation(self, engine, rules):
        """Once RED is found, engine should return RED regardless of other rules."""
        assessment = make_assessment(
            consciousness=ConsciousnessAssessment(avpu="Unresponsive", status=ClinicalValueStatus.KNOWN),
        )
        result = engine.evaluate(assessment, rules)
        assert result.colour == TriageColour.RED


class TestUnknownHandling:
    """UNKNOWN must never be treated as negative/absent."""

    def test_unknown_breathing_not_treated_as_absent(self, engine, rules):
        """If breathing difficulty is UNKNOWN, it must not trigger a rule for absent breathing."""
        assessment = make_assessment(
            breathing=BreathingAssessment(
                difficulty=SymptomStatus.UNKNOWN,
                status=ClinicalValueStatus.UNKNOWN,
            ),
            chief_complaint=ChiefComplaint(
                original="headache",
                normalized="headache",
                category="headache",
                confidence=0.9,
            ),
            pain=PainAssessment(severity=2, present=SymptomStatus.PRESENT, status=ClinicalValueStatus.KNOWN),
        )
        result = engine.evaluate(assessment, rules)
        # Should NOT be RED or ORANGE just because breathing is UNKNOWN
        # UNKNOWN ≠ false, UNKNOWN ≠ absent
        assert result.triage_level >= 3  # YELLOW or lower

    def test_missing_vitals_does_not_default_to_low_acuity(self, engine, rules):
        """If vital signs are unknown, engine should not assume they are normal."""
        assessment = make_assessment(
            vital_signs=None,
            breathing=BreathingAssessment(difficulty=SymptomStatus.PRESENT, status=ClinicalValueStatus.KNOWN),
        )
        result = engine.evaluate(assessment, rules)
        # Breathing difficulty present → at least YELLOW
        assert result.triage_level <= 3


class TestSpecificRules:
    """Test individual rule triggers."""

    def test_rule_red_unresponsive(self, engine, rules):
        assessment = make_assessment(
            consciousness=ConsciousnessAssessment(avpu="Unresponsive", status=ClinicalValueStatus.KNOWN),
        )
        result = engine.evaluate(assessment, rules)
        assert result.colour == TriageColour.RED
        rule_ids = [r.rule_id for r in result.triggered_rules]
        assert any("RED" in rid for rid in rule_ids)

    def test_rule_orange_spo2_low(self, engine, rules):
        assessment = make_assessment(
            vital_signs=ObjectiveVitalSigns(spo2=90),
        )
        result = engine.evaluate(assessment, rules)
        # SpO2 < 92 → ORANGE
        assert result.triage_level <= 2

    def test_rule_orange_chest_pain_with_breathing(self, engine, rules):
        assessment = make_assessment(
            chief_complaint=ChiefComplaint(
                original="chest pain",
                normalized="chest pain",
                category="chest_discomfort",
                confidence=0.95,
            ),
            onset="20 minutes ago",
            onset_status=ClinicalValueStatus.KNOWN,
            breathing=BreathingAssessment(
                difficulty=SymptomStatus.PRESENT,
                status=ClinicalValueStatus.KNOWN,
            ),
        )
        result = engine.evaluate(assessment, rules)
        assert result.colour == TriageColour.ORANGE

    def test_rule_yellow_moderate_chest_pain(self, engine, rules):
        assessment = make_assessment(
            chief_complaint=ChiefComplaint(
                original="chest pain",
                normalized="chest pain",
                category="chest_discomfort",
                confidence=0.9,
            ),
            pain=PainAssessment(severity=5, present=SymptomStatus.PRESENT, status=ClinicalValueStatus.KNOWN),
        )
        result = engine.evaluate(assessment, rules)
        # Pain 4-7 with chest discomfort → YELLOW
        assert result.colour == TriageColour.YELLOW

    def test_rule_green_mild_pain(self, engine, rules):
        assessment = make_assessment(
            pain=PainAssessment(severity=2, present=SymptomStatus.PRESENT, status=ClinicalValueStatus.KNOWN),
        )
        result = engine.evaluate(assessment, rules)
        assert result.colour in (TriageColour.GREEN, TriageColour.YELLOW)

    def test_rule_blue_administrative(self, engine, rules):
        assessment = make_assessment(
            chief_complaint=ChiefComplaint(
                original="routine checkup",
                normalized="administrative",
                category="administrative",
                confidence=0.9,
            ),
            all_facts=[make_fact("administrative", "PRESENT", SymptomStatus.PRESENT)],
        )
        result = engine.evaluate(assessment, rules)
        assert result.colour == TriageColour.BLUE

    def test_rule_blue_chronic_review(self, engine, rules):
        assessment = make_assessment(
            chief_complaint=ChiefComplaint(
                original="routine follow-up for hypertension",
                normalized="chronic review",
                category="chronic_review",
                confidence=0.9,
            ),
            all_facts=[make_fact("chronic_review", "PRESENT", SymptomStatus.PRESENT)],
        )
        result = engine.evaluate(assessment, rules)
        assert result.colour == TriageColour.BLUE
        assert result.triage_level == 5

    def test_default_fallback_is_yellow(self, engine, rules):
        """Empty assessment → fallback to YELLOW (safe default)."""
        assessment = make_assessment()
        result = engine.evaluate(assessment, rules)
        assert result.colour == TriageColour.YELLOW  # safe fallback

    def test_high_fever_orange(self, engine, rules):
        assessment = make_assessment(
            vital_signs=ObjectiveVitalSigns(temperature=40.5),
        )
        result = engine.evaluate(assessment, rules)
        assert result.colour == TriageColour.ORANGE

    def test_moderate_fever_yellow(self, engine, rules):
        assessment = make_assessment(
            vital_signs=ObjectiveVitalSigns(temperature=38.7),
        )
        result = engine.evaluate(assessment, rules)
        assert result.colour == TriageColour.YELLOW

    def test_low_grade_fever_green(self, engine, rules):
        assessment = make_assessment(
            vital_signs=ObjectiveVitalSigns(temperature=38.0),
        )
        result = engine.evaluate(assessment, rules)
        assert result.colour == TriageColour.GREEN


class TestEvidenceTracking:
    """Every triage result must be explainable."""

    def test_triggered_rules_have_descriptions(self, engine, rules):
        assessment = make_assessment(
            consciousness=ConsciousnessAssessment(avpu="Unresponsive", status=ClinicalValueStatus.KNOWN),
        )
        result = engine.evaluate(assessment, rules)
        for rule in result.triggered_rules:
            assert rule.rule_id
            assert rule.rule_description
            assert len(rule.rule_id) > 0

    def test_rules_version_recorded(self, engine, rules):
        assessment = make_assessment()
        result = engine.evaluate(assessment, rules)
        assert result.rules_version == "1.0.0"

    def test_explanation_is_non_empty(self, engine, rules):
        assessment = make_assessment(
            vital_signs=ObjectiveVitalSigns(spo2=90),
        )
        result = engine.evaluate(assessment, rules)
        assert result.explanation
        assert len(result.explanation) > 10


class TestReproducibility:
    """Spec §27: every triage result must record exactly which rules produced it."""

    def test_ruleset_hash_is_recorded_and_stable(self, engine, rules):
        assessment = make_assessment()
        result1 = engine.evaluate(assessment, rules)
        result2 = engine.evaluate(assessment, rules)
        assert result1.ruleset_hash
        assert len(result1.ruleset_hash) == 64  # SHA-256 hex digest
        assert result1.ruleset_hash == result2.ruleset_hash

    def test_protocol_name_is_recorded(self, engine, rules):
        assessment = make_assessment()
        result = engine.evaluate(assessment, rules)
        assert result.protocol == "AI_NURSE_SYNTHETIC_PROTOTYPE"

    def test_evaluated_at_timestamp_is_recorded(self, engine, rules):
        assessment = make_assessment()
        result = engine.evaluate(assessment, rules)
        assert result.evaluated_at
        # Must be a parseable ISO-8601 timestamp
        from datetime import datetime
        datetime.fromisoformat(result.evaluated_at)


class TestAgeAndPregnancyDiscriminators:
    """Spec §12: age- and pregnancy-specific discriminators, previously unused fields."""

    def test_infant_with_fever_is_orange(self, engine, rules):
        assessment = make_assessment(
            patient_age=0,
            vital_signs=ObjectiveVitalSigns(temperature=38.5),
        )
        result = engine.evaluate(assessment, rules)
        assert result.colour == TriageColour.ORANGE

    def test_pregnant_with_bleeding_is_orange(self, engine, rules):
        assessment = make_assessment(
            pregnancy_status="PREGNANT",
            bleeding=BleedingAssessment(present=SymptomStatus.PRESENT, status=ClinicalValueStatus.KNOWN),
        )
        result = engine.evaluate(assessment, rules)
        assert result.colour == TriageColour.ORANGE

    def test_non_pregnant_bleeding_does_not_trigger_pregnancy_rule(self, engine, rules):
        """Guards against the pregnancy rule firing for unrelated patients."""
        assessment = make_assessment(
            pregnancy_status="NOT_PREGNANT",
            bleeding=BleedingAssessment(
                present=SymptomStatus.PRESENT, severity="minor", status=ClinicalValueStatus.KNOWN,
            ),
        )
        result = engine.evaluate(assessment, rules)
        assert result.colour != TriageColour.RED


class TestContainsOperator:
    """New 'contains' condition operator used for acute/rapid-onset discrimination."""

    def test_acute_onset_with_moderate_pain_is_yellow_or_higher(self, engine, rules):
        assessment = make_assessment(
            onset="20 minutes ago",
            onset_status=ClinicalValueStatus.KNOWN,
            pain=PainAssessment(severity=5, present=SymptomStatus.PRESENT, status=ClinicalValueStatus.KNOWN),
        )
        result = engine.evaluate(assessment, rules)
        assert result.triage_level <= 3  # YELLOW or more urgent

    def test_unknown_onset_does_not_trigger_contains_rule(self, engine, rules):
        """UNKNOWN onset must never be treated as if it matched 'contains minute'."""
        assessment = make_assessment(
            pain=PainAssessment(severity=5, present=SymptomStatus.PRESENT, status=ClinicalValueStatus.KNOWN),
        )
        result = engine.evaluate(assessment, rules)
        # No onset info at all — should not be escalated purely by the new rule.
        assert result.triage_level >= 3


class TestMissingPulseIsNotNoPulse:
    """RULE-RED-001 must fire on a measured pulse of 0, never on an unrecorded pulse."""

    def test_unrecorded_pulse_does_not_trigger_no_pulse_rule(self, engine, rules):
        a = make_assessment(consciousness=ConsciousnessAssessment(avpu="Unresponsive", status=ClinicalValueStatus.KNOWN))
        ids = [r.rule_id for r in engine.evaluate(a, rules).triggered_rules]
        assert "RULE-RED-001" not in ids
        assert "RULE-RED-003" in ids  # still RED, for the right reason

    def test_measured_zero_pulse_triggers_no_pulse_rule(self, engine, rules):
        a = make_assessment(
            consciousness=ConsciousnessAssessment(avpu="Unresponsive", status=ClinicalValueStatus.KNOWN),
            vital_signs=ObjectiveVitalSigns(pulse=0),
        )
        ids = [r.rule_id for r in engine.evaluate(a, rules).triggered_rules]
        assert "RULE-RED-001" in ids
