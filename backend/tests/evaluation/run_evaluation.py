"""
Automated Evaluation Runner.

Runs TWO passes over the 50 synthetic cases, because they test different things:

  PART 1 — Rules-Engine-Only Evaluation
    Gold-standard facts are fed directly into the deterministic triage engine.
    This isolates and validates the engine/rules logic itself, independent of
    extraction quality. It CANNOT tell you anything about how well the system
    understands a conversation — that is what Part 2 is for.

  PART 2 — End-to-End Pipeline Evaluation
    Each case's actual conversation text is played turn-by-turn through the real
    pipeline: LLM extraction -> hallucination guard -> fact merge -> engine. This
    is what spec §37/§38 actually asks for, and it is what makes Clinical Fact
    Precision/Recall, Hallucination Rate, and Question Efficiency measurable.

    By default Part 2 uses MockConversationService so the numbers are 100%
    reproducible without an API key. Its keyword matching only recognises a
    handful of English/Urdu-transliterated phrases, so accuracy on native
    Urdu/Arabic-script cases will legitimately be lower here than in Part 1 —
    that gap is real and expected; it is exactly the gap GPT-4o's language
    understanding is meant to close. Set EVAL_USE_REAL_LLM=1 with a valid
    OPENAI_API_KEY to re-run Part 2 against the real GPT-4o service instead.

Usage:
    cd backend
    python -m tests.evaluation.run_evaluation
    EVAL_USE_REAL_LLM=1 OPENAI_API_KEY=sk-... python -m tests.evaluation.run_evaluation
"""

from __future__ import annotations
import sys
import os
import time
import asyncio
from typing import List, Dict, Any, Set

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from app.services.triage.engine import TriageEngine, load_rules
from app.services.triage.models import (
    ClinicalAssessment, ClinicalFact, Evidence, TriageColour,
    ObjectiveVitalSigns, SymptomStatus, ClinicalValueStatus,
    PainAssessment, BreathingAssessment, BleedingAssessment,
    ConsciousnessAssessment, ChiefComplaint,
)
from app.services.extraction.extractor import ClinicalFactExtractor
from app.services.llm.openai_service import MockConversationService
from data.synthetic_cases.cases import SYNTHETIC_CASES

COLOUR_LEVEL = {"RED": 1, "ORANGE": 2, "YELLOW": 3, "GREEN": 4, "BLUE": 5, "UNKNOWN": 3}


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1 — Rules-Engine-Only Evaluation (gold facts -> engine)
# ═══════════════════════════════════════════════════════════════════════════════

def build_assessment_from_case(case: dict) -> ClinicalAssessment:
    """
    Construct a ClinicalAssessment directly from a case's gold-standard facts.
    This tests the RULES ENGINE ONLY — see module docstring. The full
    conversation -> extraction -> engine path is exercised in Part 2 below.
    """
    session_id = case["case_id"]
    vitals_data = case.get("vital_signs", {})
    gold = case.get("gold_standard", {})
    expected_facts = gold.get("expectedFacts", [])

    assessment = ClinicalAssessment(session_id=session_id, patient_age=case.get("age"))

    # Build vital signs from case definition
    if vitals_data:
        assessment.vital_signs = ObjectiveVitalSigns(
            spo2=vitals_data.get("spo2"),
            pulse=vitals_data.get("pulse"),
            temperature=vitals_data.get("temperature"),
            systolic_bp=vitals_data.get("systolic_bp"),
            diastolic_bp=vitals_data.get("diastolic_bp"),
            respiratory_rate=vitals_data.get("respiratory_rate"),
            gcs=vitals_data.get("gcs"),
            avpu=vitals_data.get("avpu"),
        )
        if vitals_data.get("temperature"):
            assessment.temperature = vitals_data["temperature"]

    # Build facts from gold standard
    COMPLAINT_MAP = {
        "chest_pain": "chest_discomfort",
        "chest_discomfort": "chest_discomfort",
        "breathing_difficulty": "breathing_problem",
        "abdominal_pain": "abdominal_complaint",
        "headache": "headache",
        "fever": "fever",
        "bleeding": "bleeding",
        "injury": "injury",
        "stroke_symptoms": "neurological_symptoms",
        "general_weakness": "general_weakness",
        "anaphylaxis": "allergic_symptoms",
        "administrative": "administrative",
        "chronic_review": "chronic_review",
    }

    for i, f in enumerate(expected_facts):
        key = f.get("fact_key", "")
        val = f.get("fact_value", "PRESENT")
        status_str = f.get("status", "PRESENT")
        status = SymptomStatus(status_str) if status_str in SymptomStatus.__members__ else SymptomStatus.PRESENT

        fact = ClinicalFact(
            fact_type="SYMPTOM",
            fact_key=key,
            fact_value=val,
            status=status,
            confidence=0.95,
            evidence=Evidence(
                message_id=f"MSG-{i+1:03d}",
                speaker="patient",
                original_text=f"Patient reported {key}: {val}",
            ),
        )
        assessment.all_facts.append(fact)

        # Update structured fields
        if key == "pain_severity":
            try:
                assessment.pain = PainAssessment(
                    severity=int(val),
                    present=SymptomStatus.PRESENT,
                    status=ClinicalValueStatus.KNOWN,
                )
            except ValueError:
                pass
        elif key in ("chest_pain", "chest_discomfort"):
            assessment.pain.present = SymptomStatus.PRESENT
        elif key == "breathing_difficulty":
            assessment.breathing = BreathingAssessment(
                difficulty=status,
                status=ClinicalValueStatus.KNOWN,
            )
        elif key == "bleeding":
            assessment.bleeding = BleedingAssessment(
                present=status,
                status=ClinicalValueStatus.KNOWN,
            )
        elif key == "bleeding_severity":
            assessment.bleeding.severity = val
        elif key == "consciousness_avpu":
            assessment.consciousness = ConsciousnessAssessment(
                avpu=val,
                status=ClinicalValueStatus.KNOWN,
            )
        elif key == "confusion":
            assessment.consciousness.confusion = status
        elif key == "onset":
            assessment.onset = val
            assessment.onset_status = ClinicalValueStatus.KNOWN

        # Set chief complaint category
        if key in COMPLAINT_MAP and status == SymptomStatus.PRESENT:
            if assessment.chief_complaint is None:
                assessment.chief_complaint = ChiefComplaint(
                    original=key,
                    normalized=key.replace("_", " "),
                    category=COMPLAINT_MAP[key],
                    confidence=0.95,
                )

    # Handle AVPU from vitals
    if vitals_data.get("avpu"):
        assessment.consciousness = ConsciousnessAssessment(
            avpu=vitals_data["avpu"],
            status=ClinicalValueStatus.KNOWN,
        )

    # Handle GCS < 10 → AVPU Pain
    if vitals_data.get("gcs") and vitals_data["gcs"] < 10:
        if not assessment.consciousness.avpu:
            assessment.consciousness = ConsciousnessAssessment(
                avpu="Pain",
                gcs=vitals_data["gcs"],
                status=ClinicalValueStatus.KNOWN,
            )

    return assessment


class EvaluationResult:
    def __init__(self, case_id: str, expected: str, predicted: str,
                 latency_ms: float, is_adversarial: bool, adversarial_type: str = ""):
        self.case_id = case_id
        self.expected = expected
        self.predicted = predicted
        self.expected_level = COLOUR_LEVEL.get(expected, 3)
        self.predicted_level = COLOUR_LEVEL.get(predicted, 3)
        self.latency_ms = latency_ms
        self.is_adversarial = is_adversarial
        self.adversarial_type = adversarial_type

    @property
    def is_exact_match(self) -> bool:
        return self.expected == self.predicted

    @property
    def is_under_triage(self) -> bool:
        """Predicted lower urgency (higher level number) than gold standard."""
        return self.predicted_level > self.expected_level

    @property
    def is_over_triage(self) -> bool:
        """Predicted higher urgency (lower level number) than gold standard."""
        return self.predicted_level < self.expected_level

    @property
    def is_severe_under_triage(self) -> bool:
        """Downgraded by 2 or more categories — most safety-critical error."""
        return (self.predicted_level - self.expected_level) >= 2

    @property
    def is_high_acuity(self) -> bool:
        return self.expected in ("RED", "ORANGE")

    @property
    def is_high_acuity_detected(self) -> bool:
        return self.predicted in ("RED", "ORANGE")


def run_evaluation() -> List[EvaluationResult]:
    engine = TriageEngine()
    rules = load_rules("1.0.0")
    results: List[EvaluationResult] = []

    print(f"\n{'='*70}")
    print(f"  PART 1 — RULES-ENGINE-ONLY EVALUATION (gold facts -> engine)")
    print(f"  Rules version: {rules.version}  |  Ruleset hash: {rules.ruleset_hash[:16]}...")
    print(f"  Total cases: {len(SYNTHETIC_CASES)}")
    print(f"{'='*70}\n")

    for case in SYNTHETIC_CASES:
        case_id = case["case_id"]
        expected_severity = case["gold_standard"]["expectedSeverity"]
        is_adversarial = case.get("adversarial", False)
        adversarial_type = case.get("adversarial_type", "")

        # Build assessment from case definition
        assessment = build_assessment_from_case(case)

        # Time the engine
        t0 = time.perf_counter()
        result = engine.evaluate(assessment, rules)
        latency_ms = (time.perf_counter() - t0) * 1000

        predicted = result.colour.value
        match = "✓" if predicted == expected_severity else "✗"
        adv_tag = f" [{adversarial_type}]" if is_adversarial else ""

        print(f"  {match} {case_id}{adv_tag}")
        print(f"      Expected: {expected_severity:6s}  Predicted: {predicted:6s}  "
              f"({latency_ms:.1f}ms)")
        if predicted != expected_severity:
            diff = COLOUR_LEVEL.get(predicted, 3) - COLOUR_LEVEL.get(expected_severity, 3)
            tag = "⚠ UNDER-TRIAGE" if diff > 0 else "△ OVER-TRIAGE"
            if diff >= 2:
                tag = "🚨 SEVERE UNDER-TRIAGE"
            print(f"      ** {tag} (delta={diff:+d}) **")

        results.append(EvaluationResult(
            case_id=case_id,
            expected=expected_severity,
            predicted=predicted,
            latency_ms=latency_ms,
            is_adversarial=is_adversarial,
            adversarial_type=adversarial_type,
        ))

    return results


def compute_metrics(results: List[EvaluationResult]) -> Dict[str, Any]:
    n = len(results)
    exact = sum(1 for r in results if r.is_exact_match)
    under = sum(1 for r in results if r.is_under_triage)
    over = sum(1 for r in results if r.is_over_triage)
    severe_under = sum(1 for r in results if r.is_severe_under_triage)
    high_acuity_cases = [r for r in results if r.is_high_acuity]
    high_acuity_detected = sum(1 for r in high_acuity_cases if r.is_high_acuity_detected)
    latencies = [r.latency_ms for r in results]

    return {
        "total_cases": n,
        "triage_accuracy": exact / n if n else 0,
        "exact_matches": exact,
        "under_triage_count": under,
        "under_triage_rate": under / n if n else 0,
        "over_triage_count": over,
        "over_triage_rate": over / n if n else 0,
        "severe_under_triage_count": severe_under,
        "severe_under_triage_rate": severe_under / n if n else 0,
        "high_acuity_recall": high_acuity_detected / len(high_acuity_cases) if high_acuity_cases else 0,
        "high_acuity_cases_total": len(high_acuity_cases),
        "high_acuity_cases_detected": high_acuity_detected,
        "avg_latency_ms": sum(latencies) / len(latencies) if latencies else 0,
        "min_latency_ms": min(latencies) if latencies else 0,
        "max_latency_ms": max(latencies) if latencies else 0,
        "adversarial_cases": sum(1 for r in results if r.is_adversarial),
        "adversarial_correct": sum(1 for r in results if r.is_adversarial and r.is_exact_match),
    }


def print_report(results: List[EvaluationResult], metrics: Dict[str, Any]) -> None:
    print(f"\n{'='*70}")
    print(f"  PART 1 METRICS — RULES-ENGINE-ONLY")
    print(f"{'='*70}")
    print(f"\n  {'Metric':<40} {'Value':>15}")
    print(f"  {'-'*55}")

    def pct(v): return f"{v*100:.1f}%"
    def ms(v): return f"{v:.2f}ms"

    rows = [
        ("Total Cases", metrics["total_cases"]),
        ("Triage Accuracy (exact match)", pct(metrics["triage_accuracy"])),
        ("", ""),
        ("Under-Triage Count", metrics["under_triage_count"]),
        ("Under-Triage Rate ⚠", pct(metrics["under_triage_rate"])),
        ("Severe Under-Triage Count 🚨", metrics["severe_under_triage_count"]),
        ("Severe Under-Triage Rate 🚨", pct(metrics["severe_under_triage_rate"])),
        ("Over-Triage Count", metrics["over_triage_count"]),
        ("Over-Triage Rate", pct(metrics["over_triage_rate"])),
        ("", ""),
        ("High-Acuity Recall (RED+ORANGE)", pct(metrics["high_acuity_recall"])),
        ("  High-Acuity Cases", metrics["high_acuity_cases_total"]),
        ("  High-Acuity Detected", metrics["high_acuity_cases_detected"]),
        ("", ""),
        ("Adversarial Cases", metrics["adversarial_cases"]),
        ("Adversarial Accuracy (rules-only)", pct(
            metrics["adversarial_correct"] / metrics["adversarial_cases"]
            if metrics["adversarial_cases"] else 0
        )),
        ("", ""),
        ("Avg Rules-Engine Latency", ms(metrics["avg_latency_ms"])),
        ("Min Rules-Engine Latency", ms(metrics["min_latency_ms"])),
        ("Max Rules-Engine Latency", ms(metrics["max_latency_ms"])),
    ]

    for label, value in rows:
        if label == "":
            print()
            continue
        print(f"  {label:<40} {str(value):>15}")

    print(f"\n{'='*70}")

    # Safety assessment
    print("\n  SAFETY ASSESSMENT (Part 1):")
    if metrics["severe_under_triage_count"] == 0:
        print("  ✓ PASS — No severe under-triage cases detected")
    else:
        print(f"  ✗ FAIL — {metrics['severe_under_triage_count']} severe under-triage case(s) detected!")

    if metrics["high_acuity_recall"] >= 0.95:
        print(f"  ✓ PASS — High-acuity recall {metrics['high_acuity_recall']*100:.1f}% (≥ 95%)")
    else:
        print(f"  ✗ FAIL — High-acuity recall {metrics['high_acuity_recall']*100:.1f}% (< 95% threshold)")

    if metrics["under_triage_rate"] <= 0.10:
        print(f"  ✓ PASS — Under-triage rate {metrics['under_triage_rate']*100:.1f}% (≤ 10%)")
    else:
        print(f"  ✗ WARN — Under-triage rate {metrics['under_triage_rate']*100:.1f}% (> 10% threshold)")

    print(f"\n  Note: Part 1 tests the RULES ENGINE only (gold facts fed in directly).")
    print(f"        See PART 2 below for full conversation -> extraction -> engine accuracy,")
    print(f"        Clinical Fact Precision/Recall, Hallucination Rate, and Question Efficiency.\n")


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2 — End-to-End Pipeline Evaluation (conversation -> extraction -> guard -> engine)
# ═══════════════════════════════════════════════════════════════════════════════

class PipelineCaseResult:
    def __init__(self, case_id: str, expected: str, predicted: str, is_adversarial: bool,
                 adversarial_type: str, precision: float, recall: float,
                 hallucinated: bool, turns: int, llm_ms: float, rules_ms: float,
                 conflict_expected: bool, conflict_detected: bool):
        self.case_id = case_id
        self.expected = expected
        self.predicted = predicted
        self.expected_level = COLOUR_LEVEL.get(expected, 3)
        self.predicted_level = COLOUR_LEVEL.get(predicted, 3)
        self.is_adversarial = is_adversarial
        self.adversarial_type = adversarial_type
        self.precision = precision
        self.recall = recall
        self.hallucinated = hallucinated
        self.turns = turns
        self.llm_ms = llm_ms
        self.rules_ms = rules_ms
        self.conflict_expected = conflict_expected
        self.conflict_detected = conflict_detected

    @property
    def is_exact_match(self) -> bool:
        return self.expected == self.predicted

    @property
    def is_under_triage(self) -> bool:
        return self.predicted_level > self.expected_level

    @property
    def is_high_acuity(self) -> bool:
        return self.expected in ("RED", "ORANGE")

    @property
    def is_high_acuity_detected(self) -> bool:
        return self.predicted in ("RED", "ORANGE")


async def _run_case_through_pipeline(case: dict, engine: TriageEngine, rules, conv_service) -> PipelineCaseResult:
    """Play a case's conversation turn-by-turn through the real extraction pipeline."""
    fact_extractor = ClinicalFactExtractor()
    assessment = ClinicalAssessment(session_id=case["case_id"], patient_age=case.get("age"))

    vitals_data = case.get("vital_signs", {})
    if vitals_data:
        assessment.vital_signs = ObjectiveVitalSigns(**{
            k: v for k, v in vitals_data.items()
            if k in ObjectiveVitalSigns.model_fields
        })
        if vitals_data.get("temperature"):
            assessment.temperature = vitals_data["temperature"]

    history: List[dict] = []
    msg_texts: Dict[str, str] = {}
    known_ids: Set[str] = set()
    all_rejected = []
    turns = 0
    llm_ms_total = 0.0
    msg_counter = 0

    for turn in case["conversation"]:
        msg_counter += 1
        mid = f"MSG-{msg_counter:03d}"
        text = turn.get("text", "")
        known_ids.add(mid)
        msg_texts[mid] = text
        role = "user" if turn["speaker"] == "patient" else "assistant"
        history.append({"role": role, "content": f"[{mid}] {text}"})

        if turn["speaker"] != "patient" or not text:
            continue

        turns += 1
        t0 = time.perf_counter()
        extraction = await conv_service.extract_and_respond(
            conversation_history=history,
            current_message_id=mid,
            clinical_state=assessment,
            patient_language=case.get("language", "en"),
        )
        llm_ms_total += (time.perf_counter() - t0) * 1000

        assessment, rejected, _conflicts = fact_extractor.process_extraction(
            assessment, extraction, known_ids, msg_texts,
        )
        all_rejected.extend(rejected)

        if extraction.conversation_complete:
            break

    t0 = time.perf_counter()
    result = engine.evaluate(assessment, rules)
    rules_ms = (time.perf_counter() - t0) * 1000

    gold = case.get("gold_standard", {})
    expected_keys = {f.get("fact_key") for f in gold.get("expectedFacts", []) if f.get("fact_key")}
    extracted_keys = {f.fact_key for f in assessment.all_facts}
    forbidden = set(gold.get("forbiddenUnsupportedFacts", []))

    overlap = expected_keys & extracted_keys
    precision = len(overlap) / len(extracted_keys) if extracted_keys else (1.0 if not expected_keys else 0.0)
    recall = len(overlap) / len(expected_keys) if expected_keys else 1.0

    hallucinated = any(
        f.fact_key in forbidden or str(f.fact_value) in forbidden
        for f in assessment.all_facts
    )

    conflict_expected = bool(gold.get("conflictsExpected"))
    conflict_detected = len(assessment.conflicts) > 0

    return PipelineCaseResult(
        case_id=case["case_id"],
        expected=gold.get("expectedSeverity", "UNKNOWN"),
        predicted=result.colour.value,
        is_adversarial=case.get("adversarial", False),
        adversarial_type=case.get("adversarial_type", ""),
        precision=precision,
        recall=recall,
        hallucinated=hallucinated,
        turns=turns,
        llm_ms=llm_ms_total,
        rules_ms=rules_ms,
        conflict_expected=conflict_expected,
        conflict_detected=conflict_detected,
    )


async def run_pipeline_evaluation(use_real_llm: bool = False) -> List[PipelineCaseResult]:
    engine = TriageEngine()
    rules = load_rules("1.0.0")

    if use_real_llm:
        from app.core.config import get_settings
        from app.services.llm.openai_service import OpenAIGPT4oConversationService
        settings = get_settings()
        if not settings.OPENAI_API_KEY:
            print("  EVAL_USE_REAL_LLM=1 but no OPENAI_API_KEY is set — falling back to MockConversationService.\n")
            conv_service = MockConversationService()
        else:
            conv_service = OpenAIGPT4oConversationService(settings.OPENAI_API_KEY, settings.OPENAI_LLM_MODEL)
    else:
        conv_service = MockConversationService()

    print(f"\n{'='*70}")
    print(f"  PART 2 — END-TO-END PIPELINE EVALUATION")
    print(f"  Conversation service: {conv_service.__class__.__name__}")
    print(f"  Total cases: {len(SYNTHETIC_CASES)}")
    print(f"{'='*70}\n")

    results = []
    for case in SYNTHETIC_CASES:
        r = await _run_case_through_pipeline(case, engine, rules, conv_service)
        match = "✓" if r.is_exact_match else "✗"
        adv_tag = f" [{r.adversarial_type}]" if r.is_adversarial else ""
        print(f"  {match} {r.case_id}{adv_tag}  expected={r.expected:6s} predicted={r.predicted:6s} "
              f"P={r.precision:.2f} R={r.recall:.2f} turns={r.turns}"
              f"{'  🚫 HALLUCINATION' if r.hallucinated else ''}")
        results.append(r)

    return results


def compute_pipeline_metrics(results: List[PipelineCaseResult]) -> Dict[str, Any]:
    n = len(results)
    exact = sum(1 for r in results if r.is_exact_match)
    under = sum(1 for r in results if r.is_under_triage)
    high_acuity_cases = [r for r in results if r.is_high_acuity]
    high_acuity_detected = sum(1 for r in high_acuity_cases if r.is_high_acuity_detected)
    adversarial = [r for r in results if r.is_adversarial]
    conflict_cases = [r for r in results if r.conflict_expected]

    avg_precision = sum(r.precision for r in results) / n if n else 0
    avg_recall = sum(r.recall for r in results) / n if n else 0
    hallucination_cases = sum(1 for r in results if r.hallucinated)
    avg_turns = sum(r.turns for r in results) / n if n else 0
    avg_llm_ms = sum(r.llm_ms for r in results) / n if n else 0
    avg_rules_ms = sum(r.rules_ms for r in results) / n if n else 0

    return {
        "total_cases": n,
        "e2e_accuracy": exact / n if n else 0,
        "e2e_under_triage_rate": under / n if n else 0,
        "e2e_high_acuity_recall": high_acuity_detected / len(high_acuity_cases) if high_acuity_cases else 0,
        "adversarial_cases": len(adversarial),
        "adversarial_accuracy": (sum(1 for r in adversarial if r.is_exact_match) / len(adversarial)) if adversarial else 0,
        "clinical_fact_precision": avg_precision,
        "clinical_fact_recall": avg_recall,
        "hallucination_cases": hallucination_cases,
        "hallucination_rate": hallucination_cases / n if n else 0,
        "question_efficiency_avg_turns": avg_turns,
        "contradiction_cases_total": len(conflict_cases),
        "contradiction_detection_rate": (
            sum(1 for r in conflict_cases if r.conflict_detected) / len(conflict_cases)
            if conflict_cases else None
        ),
        "avg_llm_ms": avg_llm_ms,
        "avg_rules_ms": avg_rules_ms,
        "avg_total_ms": avg_llm_ms + avg_rules_ms,
    }


def print_pipeline_report(metrics: Dict[str, Any], used_real_llm: bool) -> None:
    def pct(v): return f"{v*100:.1f}%" if v is not None else "N/A"
    def ms(v): return f"{v:.2f}ms"

    print(f"\n{'='*70}")
    print(f"  PART 2 METRICS — END-TO-END PIPELINE ({'GPT-4o' if used_real_llm else 'Mock service'})")
    print(f"{'='*70}\n")

    rows = [
        ("Total Cases", metrics["total_cases"]),
        ("End-to-End Triage Accuracy", pct(metrics["e2e_accuracy"])),
        ("End-to-End Under-Triage Rate ⚠", pct(metrics["e2e_under_triage_rate"])),
        ("End-to-End High-Acuity Recall", pct(metrics["e2e_high_acuity_recall"])),
        ("", ""),
        ("Adversarial Cases", metrics["adversarial_cases"]),
        ("Adversarial Accuracy (end-to-end)", pct(metrics["adversarial_accuracy"])),
        ("", ""),
        ("Clinical Fact Precision (avg)", pct(metrics["clinical_fact_precision"])),
        ("Clinical Fact Recall (avg)", pct(metrics["clinical_fact_recall"])),
        ("Hallucination Rate (cases)", pct(metrics["hallucination_rate"])),
        ("  Hallucinated Cases", metrics["hallucination_cases"]),
        ("", ""),
        ("Contradiction Detection Rate", pct(metrics["contradiction_detection_rate"])),
        ("  Cases With Expected Conflict", metrics["contradiction_cases_total"]),
        ("", ""),
        ("Question Efficiency (avg turns/case)", f"{metrics['question_efficiency_avg_turns']:.1f}"),
        ("", ""),
        ("Avg LLM/Extraction Latency", ms(metrics["avg_llm_ms"])),
        ("Avg Rules-Engine Latency", ms(metrics["avg_rules_ms"])),
        ("Avg Total Pipeline Latency", ms(metrics["avg_total_ms"])),
    ]
    for label, value in rows:
        if label == "":
            print()
            continue
        print(f"  {label:<40} {str(value):>15}")

    print(f"\n{'='*70}")
    if not used_real_llm:
        print("""
  NOTE ON THIS RUN'S NUMBERS (read before quoting them):
  MockConversationService only pattern-matches a handful of English words and
  Urdu/Arabic ROMANIZED transliterations (e.g. "seene", "bukhar") — it does not
  understand native Urdu/Arabic SCRIPT. Cases written in actual Urdu/Arabic script
  will mostly fail to extract anything here, which is expected and is a Mock
  limitation, not a rules-engine defect (Part 1 already validates the engine
  itself against clean gold facts). This pass exists to prove the wiring —
  conversation -> extraction -> guard -> engine — is real and measurable.

  For representative multilingual accuracy, rerun with a real OpenAI key:
      EVAL_USE_REAL_LLM=1 OPENAI_API_KEY=sk-... python -m tests.evaluation.run_evaluation
""")
    print("  NOT MEASURED IN THIS OFFLINE HARNESS (documented here rather than guessed):")
    print("    - STT Accuracy — requires live audio fixtures + Whisper API access.")
    print("    - Per-service Cost — requires measured token counts from real API calls;")
    print("      docs/evaluation_report.md gives a published-pricing ESTIMATE instead,")
    print("      explicitly labelled as such (not a measurement).")
    print()


if __name__ == "__main__":
    # PART 1
    results = run_evaluation()
    metrics = compute_metrics(results)
    print_report(results, metrics)

    # PART 2
    use_real_llm = os.environ.get("EVAL_USE_REAL_LLM") == "1"
    pipeline_results = asyncio.run(run_pipeline_evaluation(use_real_llm=use_real_llm))
    pipeline_metrics = compute_pipeline_metrics(pipeline_results)
    print_pipeline_report(pipeline_metrics, used_real_llm=use_real_llm and bool(
        os.environ.get("OPENAI_API_KEY")
    ))
