"""
Deterministic Triage Engine — ITriageEngine implementation.

KEY PRINCIPLE (spec §45):
  LLM = Understand + Extract + Converse
  NOT LLM = Decide clinical urgency

This engine is a pure function:
  Same ClinicalAssessment + same TriageRuleSet = same TriageResult (always)
No LLM calls are made here.
"""

from __future__ import annotations
from typing import List, Optional, Any, Dict
from datetime import datetime, timezone
import yaml
import os
import hashlib
import logging

from app.services.triage.models import (
    ClinicalAssessment,
    TriageResult,
    TriageColour,
    TriageCategory,
    TriggeredRule,
    COLOUR_TO_LEVEL,
    COLOUR_TO_MINUTES,
    COLOUR_TO_CATEGORY,
    SymptomStatus,
)
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ── Rule loading ───────────────────────────────────────────────────────────────

class TriageRuleSet:
    def __init__(
        self,
        version: str,
        rules: List[dict],
        description: str = "",
        protocol: str = "AI_NURSE_SYNTHETIC_PROTOTYPE",
        target_minutes: Optional[Dict[str, int]] = None,
        ruleset_hash: str = "",
    ):
        self.version = version
        self.description = description
        self.protocol = protocol
        self.ruleset_hash = ruleset_hash
        # Institutional target times (spec §3) — configurable per rule-set file,
        # falling back to the spec's reference values if the YAML doesn't override them.
        self.target_minutes: Dict[TriageColour, int] = dict(COLOUR_TO_MINUTES)
        for colour_str, minutes in (target_minutes or {}).items():
            try:
                self.target_minutes[TriageColour(colour_str)] = int(minutes)
            except ValueError:
                logger.warning("Ignoring unknown colour in target_minutes: %s", colour_str)
        # Sort by priority descending (highest priority evaluated first)
        self.rules = sorted(rules, key=lambda r: r.get("priority", 0), reverse=True)


def load_rules(version: str = None) -> TriageRuleSet:
    """Load triage rules from versioned YAML file."""
    version = version or settings.TRIAGE_RULES_VERSION
    rules_dir = settings.TRIAGE_RULES_DIR
    path = os.path.join(rules_dir, f"synthetic_rules_v{version}.yaml")

    if not os.path.exists(path):
        raise FileNotFoundError(f"Triage rules file not found: {path}")

    with open(path, "rb") as f:
        raw_bytes = f.read()

    # Reproducibility (spec §27): hash the exact bytes that produced this rule set so an
    # old triage decision can be proven against the rules that existed at the time.
    ruleset_hash = hashlib.sha256(raw_bytes).hexdigest()
    data = yaml.safe_load(raw_bytes.decode("utf-8"))

    return TriageRuleSet(
        version=data["version"],
        description=data.get("description", ""),
        protocol=data.get("protocol", "AI_NURSE_SYNTHETIC_PROTOTYPE"),
        target_minutes=data.get("target_minutes"),
        rules=data["rules"],
        ruleset_hash=ruleset_hash,
    )


# ── Condition evaluator ────────────────────────────────────────────────────────

def _resolve_field(assessment: ClinicalAssessment, field: str) -> Any:
    """
    Resolve a dotted field path on a ClinicalAssessment.
    e.g. "vital_signs.spo2", "breathing.difficulty", "chief_complaint.category"
    """
    if field == "vital_signs.temperature" and assessment.vital_signs and assessment.vital_signs.temperature is not None:
        return assessment.vital_signs.temperature
    if field == "vital_signs.temperature" and assessment.temperature is not None:
        return assessment.temperature

    parts = field.split(".")
    obj: Any = assessment

    for part in parts:
        if obj is None:
            return None
        if isinstance(obj, dict):
            obj = obj.get(part)
        elif hasattr(obj, part):
            obj = getattr(obj, part)
        elif part.startswith("symptoms."):
            # Special case: look up a named symptom in the symptoms list
            key = part.replace("symptoms.", "")
            obj = _find_symptom(assessment, key)
        else:
            return None

    # Unwrap enum values
    if hasattr(obj, "value"):
        return obj.value
    return obj


def _find_symptom(assessment: ClinicalAssessment, key: str) -> Optional[str]:
    """Find a symptom by key in the facts list."""
    for fact in assessment.all_facts:
        if fact.fact_key == key:
            return fact.status.value if hasattr(fact.status, "value") else fact.status
    return None


def _resolve_field_smart(assessment: ClinicalAssessment, field: str) -> Any:
    """Handle 'symptoms.xxx' specially, otherwise standard dotted resolve."""
    if field.startswith("symptoms."):
        key = field[len("symptoms."):]
        return _find_symptom(assessment, key)
    return _resolve_field(assessment, field)


def _evaluate_condition(assessment: ClinicalAssessment, condition: dict) -> bool:
    """Evaluate a single condition against the clinical assessment."""
    field = condition["field"]
    operator = condition["operator"]
    expected = condition["value"]

    actual = _resolve_field_smart(assessment, field)

    # If actual is None/UNKNOWN and expected is not null — condition fails
    # (UNKNOWN is never treated as a negative finding — it's just unknown)
    if actual is None and expected is not None:
        return False

    if operator == "equals":
        if expected is None:
            return actual is None
        return str(actual) == str(expected)

    elif operator == "not_equals":
        return str(actual) != str(expected)

    elif operator == "in":
        return str(actual) in [str(v) for v in expected]

    elif operator == "not_in":
        return str(actual) not in [str(v) for v in expected]

    elif operator == "less_than":
        try:
            return float(actual) < float(expected)
        except (TypeError, ValueError):
            return False

    elif operator == "less_than_or_equal":
        try:
            return float(actual) <= float(expected)
        except (TypeError, ValueError):
            return False

    elif operator == "greater_than":
        try:
            return float(actual) > float(expected)
        except (TypeError, ValueError):
            return False

    elif operator == "greater_than_or_equal":
        try:
            return float(actual) >= float(expected)
        except (TypeError, ValueError):
            return False

    elif operator == "between":
        try:
            lo, hi = float(expected[0]), float(expected[1])
            return lo <= float(actual) <= hi
        except (TypeError, ValueError, IndexError):
            return False

    elif operator == "contains":
        try:
            return str(expected).lower() in str(actual).lower()
        except (TypeError, ValueError):
            return False

    logger.warning("Unknown operator: %s", operator)
    return False


# ── Engine ─────────────────────────────────────────────────────────────────────

class TriageEngine:
    """
    Deterministic triage engine.

    Evaluates rules in priority order (highest first).
    Returns the first rule set whose colour matches, honouring escalation:
      RED > ORANGE > YELLOW > GREEN > BLUE

    No LLM calls. No randomness. Pure function.
    """

    def evaluate(
        self,
        assessment: ClinicalAssessment,
        rule_set: TriageRuleSet,
    ) -> TriageResult:
        triggered_rules: List[TriggeredRule] = []
        best_colour: Optional[TriageColour] = None

        # Evaluate rules in priority order
        for rule in rule_set.rules:
            conditions = rule.get("conditions", [])

            # Skip fallback rules with empty conditions during main evaluation
            if not conditions:
                continue

            if all(_evaluate_condition(assessment, c) for c in conditions):
                colour = TriageColour(rule["colour"])

                # Collect evidence IDs for triggered facts
                evidence_ids = self._collect_evidence_ids(assessment, conditions)
                fact_ids = self._collect_fact_ids(assessment, conditions)

                triggered_rules.append(
                    TriggeredRule(
                        rule_id=rule["id"],
                        rule_description=rule["description"],
                        evidence_ids=evidence_ids,
                        fact_ids=fact_ids,
                    )
                )

                # Escalation principle: take highest acuity (lowest level number)
                if best_colour is None or COLOUR_TO_LEVEL[colour] < COLOUR_TO_LEVEL[best_colour]:
                    best_colour = colour

                # Optimisation: RED is the highest possible — stop early
                if best_colour == TriageColour.RED:
                    break

        if best_colour is None:
            # Fallback if no specific rule matched
            best_colour = TriageColour.YELLOW
            triggered_rules.append(
                TriggeredRule(
                    rule_id="RULE-DEFAULT",
                    rule_description="Insufficient information — default safe escalation",
                    evidence_ids=[],
                    fact_ids=[],
                )
            )
            best_colour = TriageColour.YELLOW  # safe default

        level = COLOUR_TO_LEVEL[best_colour]
        category = COLOUR_TO_CATEGORY[best_colour]
        minutes = rule_set.target_minutes.get(best_colour, COLOUR_TO_MINUTES[best_colour])

        explanation = self._build_explanation(best_colour, triggered_rules, minutes)

        logger.info(
            "Triage result: %s (level %d) | %d rule(s) triggered | rules v%s",
            best_colour.value, level, len(triggered_rules), rule_set.version,
        )

        return TriageResult(
            triage_level=level,
            colour=best_colour,
            category=category,
            target_assessment_minutes=minutes,
            triggered_rules=triggered_rules,
            rules_version=rule_set.version,
            protocol=rule_set.protocol,
            ruleset_hash=rule_set.ruleset_hash,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
            explanation=explanation,
        )

    def _collect_evidence_ids(
        self, assessment: ClinicalAssessment, conditions: List[dict]
    ) -> List[str]:
        """Find evidence IDs for facts relevant to the triggered conditions."""
        ids = []
        for cond in conditions:
            field = cond["field"]
            for fact in assessment.all_facts:
                if fact.fact_key in field:
                    ids.append(fact.evidence.evidence_id)
        return list(set(ids))

    def _collect_fact_ids(
        self, assessment: ClinicalAssessment, conditions: List[dict]
    ) -> List[str]:
        ids = []
        for cond in conditions:
            field = cond["field"]
            for fact in assessment.all_facts:
                if fact.fact_key in field:
                    ids.append(fact.fact_id)
        return list(set(ids))

    def _build_explanation(
        self,
        colour: TriageColour,
        triggered_rules: List[TriggeredRule],
        target_minutes: int,
    ) -> str:
        lines = [
            f"TRIAGE RECOMMENDATION: {colour.value}",
            f"Category: {COLOUR_TO_CATEGORY[colour].value}",
            f"Target assessment: {target_minutes} minutes",
            "",
            "Evidence contributing to assessment:",
        ]
        for rule in triggered_rules:
            lines.append(f"  ✓ {rule.rule_description}")
            for eid in rule.evidence_ids[:3]:
                lines.append(f"      Evidence: {eid}")
        return "\n".join(lines)


# Singleton instance
_engine = TriageEngine()


def get_triage_engine() -> TriageEngine:
    return _engine
