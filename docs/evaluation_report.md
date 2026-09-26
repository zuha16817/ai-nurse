# Quantitative AI Evaluation Report

Reproduce this report at any time:
```bash
cd backend
python -m tests.evaluation.run_evaluation
```

The runner performs **two distinct passes** over the same 50-case synthetic dataset
(`backend/data/synthetic_cases/cases.py`), because they measure different things.
Conflating them was a prior gap in this report - see the note at the end of each
section.

---

## Part 1 - Rules-Engine-Only Evaluation

Gold-standard facts are fed **directly** into the deterministic triage engine,
bypassing conversation/extraction entirely. This isolates and validates the rules
engine and escalation logic in `backend/app/services/triage/engine.py`.

| Metric | Target | Measured | Result |
|---|---|---|---|
| Total Cases | ≥ 50 | 50 | ✓ |
| Triage Accuracy (exact match) | > 85% | **96.0%** (48/50) | ✓ PASS |
| Under-Triage Rate | < 10% | **0.0%** (0/50) | ✓ PASS |
| Severe Under-Triage Rate | 0% | **0.0%** (0/50) | ✓ PASS |
| Over-Triage Rate | < 15% | **4.0%** (2/50) | ✓ PASS |
| High-Acuity Recall (RED/ORANGE) | > 95% | **100.0%** (20/20) | ✓ PASS |
| Adversarial Accuracy (rules-only) | > 80% | **90.0%** (9/10) | ✓ PASS |
| Rules-Engine Latency (avg) | < 50ms | **~0.08ms** | ✓ PASS |

**What this proves:** the escalation logic itself is safe (zero under-triage, zero
severe under-triage, perfect high-acuity recall) and fast. **What it does NOT
prove:** anything about whether the system correctly *extracts* those facts from a
real conversation - that requires Part 2.

---

## Part 2 - End-to-End Pipeline Evaluation

Each case's actual `conversation` text is played turn-by-turn through the real
pipeline: LLM extraction → hallucination guard → fact merge → engine. This is what
spec §37/§38 actually ask for.

| Metric | Measured (MockConversationService) |
|---|---|
| End-to-End Triage Accuracy | **36.0%** |
| End-to-End Under-Triage Rate | **30.0%** |
| End-to-End High-Acuity Recall | **40.0%** |
| Adversarial Accuracy (end-to-end) | **40.0%** |
| **Clinical Fact Precision** (avg) | **41.3%** |
| **Clinical Fact Recall** (avg) | **33.7%** |
| **Hallucination Rate** (cases with an unsupported fact accepted) | **2.0%** (1/50) |
| Contradiction Detection Rate | 0.0% (1 case had an expected conflict) |
| **Question Efficiency** (avg patient turns/case) | **1.2** |
| Avg LLM/Extraction Latency | ~0.02ms (Mock - see caveat) |
| Avg Rules-Engine Latency | ~0.05ms |
| Avg Total Pipeline Latency | ~0.07ms |

### Why these numbers are much lower than Part 1 - read before quoting them

`MockConversationService` exists so this evaluation is 100% reproducible without an
API key. It only pattern-matches a handful of English words and Urdu/Arabic
**Romanized transliterations** (e.g. `"seene"`, `"bukhar"`) - it does not understand
native Urdu/Arabic **script**, and it extracts at most one intent per message (a
single `elif` chain). Consequently:

- Cases written in actual Urdu/Arabic script mostly extract nothing.
- A message like *"I have severe chest pain and I'm short of breath"* only yields
  `chest_pain`, never `breathing_difficulty`, because the mock's branches are
  mutually exclusive.
- The one contradiction case (`CASE-ORANGE-009`) triggers the mock's "conversation
  complete" flag on its first turn (an onset phrase), so its second, contradicting
  turn is never reached - the contradiction detector itself is separately unit
  tested and proven correct (`tests/test_extractor.py`) against this exact scenario.

**This is a Mock limitation, not a rules-engine defect** - Part 1 already shows the
engine itself is accurate given correct facts. This pass exists to prove the wiring
(conversation → extraction → guard → engine) is real, exercised, and its metrics are
actually computed - not to claim representative multilingual accuracy.

**For representative numbers, rerun against the real LLM:**
```bash
EVAL_USE_REAL_LLM=1 OPENAI_API_KEY=sk-... python -m tests.evaluation.run_evaluation
```
GPT-4o understands native script, extracts multiple facts per message via
structured JSON, and does not share the mock's single-intent limitation - Part 2
accuracy against it should track much closer to Part 1.

### Prior version of this report overstated two figures - corrected here
- ~~Hallucination Rate: 0.0% (Guarded)~~ - nothing was actually measuring this
  before; it was inferred from the guard's existence. It is now genuinely computed
  (2.0%, 1/50) by checking whether any fact accepted into the record matches a
  case's `forbiddenUnsupportedFacts`.
- Cost figures below are relabelled as **estimates**, not measurements (see below).

---

## Not Measured In This Offline Harness

| Metric | Why | Where to get it |
|---|---|---|
| STT Accuracy | Requires live audio fixtures + Whisper API access | Manual QA against recorded Urdu/Arabic/English clinical phrases |
| Cost per triage/100/1,000 | Requires measured token counts from real API calls | See estimate below - explicitly not a measurement |

### Cost (Estimate, not measured)
Based on published OpenAI GPT-4o + Whisper rates, assuming an average 4-turn
conversation:
- **Estimated cost per triage session**: ~$0.012 USD
- **Estimated cost per 100 triages**: ~$1.20 USD
- **Estimated cost per 1,000 triages**: ~$12.00 USD

No token accounting exists in the codebase yet - a real measurement would wrap the
OpenAI client calls in `backend/app/services/llm/openai_service.py` and
`backend/app/services/stt/whisper.py` with usage tracking.

---

## Safety-Critical Findings (unchanged by the above - these are the load-bearing claims)

1. **Zero severe under-triage** in the rules engine (Part 1) - the single most
   safety-sensitive failure mode in emergency triage.
2. **100% high-acuity recall** (Part 1) - every RED/ORANGE gold case was correctly
   identified once its facts were known.
3. **The LLM cannot set severity through any code path** - traced and unit-tested
   independently of this evaluation (see `docs/architecture.md` and
   `backend/tests/test_triage_engine.py`).
4. **Regression coverage added during hardening**: a live end-to-end smoke test
   uncovered that nurse-entered objective AVPU/GCS readings were recorded but never
   reached the rules engine's consciousness discriminators (only conversation-derived
   values did). This is now fixed and covered by
   `backend/tests/test_vitals_reach_engine.py`.
