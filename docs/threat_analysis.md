# AI Nurse Threat & Failure Mode Analysis

This document analyzes potential threat vectors, clinical failure modes, and safety controls engineered into the system per Spec §32, §38, and §39.

---

## 1. Safety & Failure Mode Matrix (Spec §39)

| Failure Mode | Root Cause | System Defense / Mitigations | System Result |
|---|---|---|---|
| **STT Failure** | Background noise, low audio signal, network drop | Catches STT API exception; presents UI prompt for text input or nurse escalation | Safe escalation to clinician review |
| **LLM Timeout** | API latency or outage (> 30s) | Timeout catch block triggers `_safe_escalation_output()` | Auto-flags case as `high_acuity_trigger=True` for nurse review |
| **Invalid LLM JSON** | LLM outputs non-JSON or invalid schema | Pydantic validation error caught | Triggers fallback safe escalation response |
| **Hallucination** | LLM invents facts (e.g., claims patient has diabetes) | `HallucinationGuard` verifies (1) the cited message ID exists, (2) confidence exceeds threshold, AND (3) the cited message TEXT actually supports the fact via a keyword/content check — citing a real-but-unrelated message is not enough to pass | Fact is REJECTED, persisted with `is_hallucination_rejected=True`, and audited via `HALLUCINATION_REJECTED` |
| **Low-Confidence Extraction** | Ambiguous or partially-transcribed patient statement | Facts rejected only for low confidence are distinguished from hallucinations and turned into a `clarify:<field>` marker | Triggers an explicit clarification question rather than silently dropping the information |
| **Clinical Contradiction** | Patient changes answer (e.g. onset 1 hour vs yesterday) | `_detect_contradictions()` flags conflicting values; both values are kept (never silently overwritten) and the contradicting fact is marked `is_contradicted` | Flags conflict, immediately asks a clarification question, presents both values in the audit trail |
| **Translation Failure** | Translation provider error/timeout | `ITranslationService` catches the error and falls back to the original text | Original patient statement is preserved and used; nothing is blocked |
| **Knowledge Retrieval Failure** | RAG vector store or embedding call fails | `IProtocolKnowledgeService.query()` catches internal errors and returns an empty result | Conversation continues without injected reference context — never blocks or crashes the pipeline |
| **Patient Stops Responding** | Patient disengages mid-interview | Client-side inactivity timer calls `/conversations/{id}/inactivity-alert` after 60s of silence | Session flagged (`PATIENT_INACTIVE` audit event) for a nurse to check on the patient — no low-acuity result is invented |
| **Objective Vitals Not Reaching the Engine** *(fixed during hardening — see note below)* | `_rebuild_assessment` only populated `vital_signs`, never `consciousness`, from nurse-entered AVPU/GCS | Nurse-entered AVPU/GCS are now explicitly merged into `assessment.consciousness` after fact-derived fields, so objective measurement always outranks patient-reported values for the same field | RED/ORANGE consciousness discriminators (e.g. `RULE-RED-003`) now correctly fire on nurse-entered readings, not only on conversation-extracted ones |
| **Prompt Injection** | Patient types adversarial text trying to bypass triage | System prompt enforces strict JSON output schema; LLM does not execute actions or decide acuity; retrieved RAG context is clearly labelled as reference material, not instructions | Injection attempt ignored by deterministic rules engine |
| **Rules Engine Exception** | Invalid rule definition or missing schema field | Exception handler catches engine error | System defaults to safe YELLOW/ORANGE priority for staff review |
| **Unauthenticated Access to Clinical Actions** *(fixed during hardening)* | `confirm`/`override`/`reassess`/`/staff/*` previously had no auth dependency | All clinician-decision endpoints now require `require_role("nurse", "admin")`; a missing/invalid token returns 401/403 before any data is read or written | A clinical transcript or triage decision can no longer be read or changed by an unauthenticated caller |
| **Excessive Request Rate** | Automated or runaway client hammering the API | `RateLimitMiddleware` (in-memory sliding window, configurable via `RATE_LIMIT_PER_MINUTE`) | Requests beyond the configured rate return `429 Too Many Requests` |

> **Note on the hardening pass:** the two rows above marked *(fixed during hardening)* were discovered via live end-to-end testing rather than static review — the AVPU gap in particular meant a nurse-entered "Unresponsive" reading recorded correctly in the database but never actually influenced the RED discriminator that is supposed to act on it. Both are now covered by regression tests (`tests/test_vitals_reach_engine.py`, endpoint-level checks in the smoke test).

---

## 2. Adversarial & Bias Test Matrix (Spec §38)

1. **Anchoring Bias**: Patient says *"My GP told me it is probably just acidity."*
   - *Defense*: Extractor focuses exclusively on reported symptoms (chest pain), ignoring third-party diagnostic opinions.
2. **Missing Information**: Key vital signs or onset details absent.
   - *Defense*: Missing fields remain `UNKNOWN` and are never assumed `false` or negative.
3. **Long Conversation & Distractors**: Patient talks about weather, family, etc. for 30 turns.
   - *Defense*: Provenance tracking retains all historical extracted facts across the session timeline.
4. **Speech Recognition Errors**: Mistranscription of critical medical terms.
   - *Defense*: Low-confidence extraction triggers explicit clarification questions.

All seven adversarial categories required by spec §38 (anchoring, missing information, contradiction, translation error, speech recognition error, long conversation, distractor information) exist as labelled cases in `backend/data/synthetic_cases/cases.py` and are run through `backend/tests/evaluation/run_evaluation.py` Part 2, which plays each case's actual conversation text through the real extraction pipeline rather than pre-supplying gold facts — see `docs/evaluation_report.md` for the measured (not assumed) results and its documented limitations.

---

## 3. Security Controls (Spec §32)

| Control | Implementation |
|---|---|
| Authentication | JWT bearer tokens (`python-jose`), issued by `/api/auth/token` |
| Role-based authorization | `require_role("nurse", "admin")` dependency on every endpoint that reads or changes a clinical decision (`confirm`, `override`, `reassess`, `escalate`, all of `/staff`, `/audit`) |
| Password storage | bcrypt via `passlib` (never plaintext or reversible encryption) |
| Rate limiting | `RateLimitMiddleware` — in-memory sliding window, `RATE_LIMIT_PER_MINUTE` configurable |
| Request/file validation | Pydantic schema validation on every request body; audio uploads capped at 15MB with an extension allowlist |
| Secret management | `SECRET_KEY` required via environment (`docker-compose.yml` fails fast with `${SECRET_KEY:?...}` if unset — no silent fallback to the insecure default in production) |
| Prompt-injection guard | Retrieved RAG passages are wrapped in a clearly-labelled "reference material" system message, separate from patient content; the LLM's output is never trusted as free text — only validated structured JSON is accepted |
| AI-provider timeout/retry | `timeout=30` on LLM calls, `timeout=15` on translation calls; `openai.APITimeoutError`/`openai.APIError` caught and mapped to safe-escalation output, never a raised exception reaching the patient |
| Logging discipline | SQL `echo` disabled unconditionally; audit-log `logger.info` calls no longer include `detail` (which may contain patient statements) — that content lives only in the access-restricted `audit_logs` table |
| Trusted-host enforcement | `TrustedHostMiddleware` wired up (`ALLOWED_HOSTS` setting) — previously imported but never applied |
