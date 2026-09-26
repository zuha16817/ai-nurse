# AI Nurse System Architecture Document

## Executive Summary

The **AI Nurse - Conversational Patient Triage & Severity Assessment System** is a production-grade clinical decision support prototype designed to assist Emergency Department (ED) staff in prioritizing patient urgency.

The core architectural invariant mandated by safety governance (Spec §45) is:

$$\text{LLM} = \text{Understand} + \text{Extract} + \text{Converse} \quad \neq \quad \text{Decide Clinical Urgency}$$

Clinical severity is decided **exclusively by a deterministic, versioned rules engine** operating on evidence-backed, structured clinical facts.

---

## Architectural Data Flow

```
+-------------------+
|    Patient UI     | (Voice / Text - English, Urdu, Arabic)
+---------+---------+
          |
          | Speech / Audio
          v
+-------------------+
|  Whisper STT      | -> ISpeechToTextService (preserves original audio & verbatim transcript)
+---------+---------+
          |
          | Verbatim Transcript + Message ID
          v
+-------------------+
|  Translation      | -> ITranslationService (English normalisation - original text
|  Service          |    is preserved alongside it, never replaced)
+---------+---------+
          |
          v
+-------------------+
| Curated Knowledge | -> IProtocolKnowledgeService (RAG, Spec §28). Retrieves
| Retrieval (RAG)   |    provenanced reference passages {document, version, section,
|                   |    publication_date} and injects them as a clearly-labelled
|                   |    system message - never presented as patient-reported fact.
+---------+---------+
          |
          v
+-------------------+
| LLM Fact Extract  | -> IClinicalConversationService (Swappable: Gemini / GPT-4o / Groq / Ollama;
|                   |    outputs strictly validated JSON)
+---------+---------+
          |
          | Extracted Facts (with message ID references) + retrieved_sources
          v
+-------------------+
| Hallucination     | -> Verifies every fact cites a real message ID in conversation.
| Guard             |    Rejects unsupported facts; detects contradictory patient statements.
+---------+---------+
          |
          | Validated ClinicalAssessment
          v
+-------------------+
| Deterministic     | -> ITriageEngine (Evaluates synthetic rules v1.0.0; RED -> BLUE)
| Triage Engine     |    Same facts + same rules version = same result (100% deterministic).
|                   |    Every result records {protocol, ruleset_hash, evaluated_at} so a
|                   |    past decision is provably reproducible against the exact rules
|                   |    content that produced it (Spec §27).
+---------+---------+
          |
          | AI Recommendation (RED/ORANGE/YELLOW/GREEN/BLUE) + Triggered Rule Evidence
          v
+-------------------+
| Human-in-the-Loop | -> Clinician confirms or overrides recommendation.
| Nurse UI          |    Overrides require documented reason and are written to audit trail.
+---------+---------+
          |
          |
+-------------------+
| Immutable Audit   | -> Full provenance answering: What patient said, what rule triggered,
| Log               |    what machine recommended, what clinician decided.
+-------------------+
```

---

## Key Design Patterns & Abstractions

### 1. Service Interfaces & Provider Independence (Spec §25, §26)
All external AI dependencies are abstracted behind abstract Python interfaces:
- `ISpeechToTextService` -> `OpenAIWhisperSTT` / `MockSTT`
- `IClinicalConversationService` -> `OpenAIGPT4oConversationService` (Supports Gemini, GPT-4o, Groq, Ollama) / `MockConversationService`
- `ITranslationService` -> `OpenAITranslationService` / `MockTranslationService`
- `ITriageEngine` -> `TriageEngine`
- `IProtocolKnowledgeService` -> `ChromaKnowledgeService` / `InMemoryKnowledgeService`
- `IAuditService` -> `AuditService`

AI providers can be replaced via environment variables (`STT_PROVIDER`, `LLM_PROVIDER`, `TRANSLATION_PROVIDER`) without modifying business or clinical triage logic. No route handler calls an external AI API directly - every call goes through a `get_*_service()` factory that reads these settings.

### 2. Evidence Provenance & Traceability (Spec §15, §40)
Every clinical fact maintains an `evidence` block referencing the exact `message_id` and timestamp of the patient's verbatim statement. The original transcript is never discarded or mutated.

### 3. Safety Bias Guards (Spec #34, §38)
- **Hallucination Guard**: Rejects facts generated without supporting verbatim patient evidence.
- **Anchoring Bias Guard**: Ensures patient quotes of third-party opinions ("my GP said it's just acidity") do not suppress high-acuity symptom extraction.
- **Contradiction Detection**: Flags conflicting statements across interview turns instead of silently overwriting.
- **Red-Flag Interruption**: Triggers immediate safety alerts if high-acuity discriminators (e.g. chest pain + SpO2 < 92%) are satisfied during interview.
