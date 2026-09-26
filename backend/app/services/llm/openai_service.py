"""
LLM Conversation Service - IClinicalConversationService.

GPT-4o is used ONLY for:
  1. Understanding patient language
  2. Extracting structured clinical facts (JSON output only)
  3. Generating the next conversational question

GPT-4o does NOT:
 - Decide triage acuity
 - Hallucinate clinical facts (all facts must cite a message ID)
 - Accept or reject patient urgency based on third-party opinions (anchoring guard)
"""

from __future__ import annotations
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import List, Optional

from app.services.triage.models import (
    ClinicalAssessment,
    LLMExtractionOutput,
    LLMExtractedFact,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a clinical information extraction assistant for an AI nurse triage system.

Your ONLY job is to:
1. Extract structured clinical facts from patient conversation messages.
2. Identify what information is still missing.
3. Detect contradictions in what the patient has said.
4. Generate the next appropriate clinical question.

CRITICAL RULES:
- You MUST return ONLY valid JSON matching the schema below.
- You MUST use top-level key "facts" containing a list of fact objects. Do NOT use top-level keys like "symptoms".
- Every extracted fact MUST include the exact message_id it came from.
- If a fact is NOT explicitly stated by the patient, do NOT include it.
- Unknown information stays UNKNOWN - never assume absent means negative.
- Do NOT decide triage urgency. That is done by a separate deterministic system.
- Do NOT lower urgency assessment because a patient quotes another person's opinion (anchoring bias guard).
- If the patient says something like "my GP said it's just acidity" but also reports chest pain - extract the chest pain fact. Do not suppress it.
- Detect contradictions: if the patient gives conflicting answers for the same field, flag the conflict.
- You MUST provide a specific clinical follow-up question in "next_question" (e.g. asking location, onset, or severity of reported symptoms).

Output schema (return ONLY this JSON, no markdown, no preamble):
{
  "facts": [
    {
      "fact_type": "SYMPTOM|ONSET|HISTORY|MEDICATION|ALLERGY|VITAL",
      "fact_key": "string (e.g. breathing_difficulty, chest_pain, cramps, fever)",
      "fact_value": "string (e.g. PRESENT, ABSENT, severe, sharp)",
      "status": "PRESENT|ABSENT|UNKNOWN|UNCERTAIN",
      "confidence": 0.0-1.0,
      "evidence_message_id": "MSG-ID from the conversation"
    }
  ],
  "missing_information": ["onset", "pain_severity", ...],
  "conflicts_detected": [
    {"field": "onset", "values": ["yesterday", "1 hour ago"], "message_ids": ["MSG-1", "MSG-3"]}
  ],
  "next_question": "English question to ask next (null if complete)",
  "next_question_urdu": "Urdu translation of next question (null if not applicable)",
  "next_question_arabic": "Arabic translation of next question (null if not applicable)",
  "high_acuity_trigger": false,
  "high_acuity_reason": null,
  "conversation_complete": false
}

When high_acuity_trigger is true, set high_acuity_reason to a brief description.
Set conversation_complete to true only when sufficient information has been collected.
"""


def _last_patient_message(conversation_history: List[dict]) -> str:
    """Return the most recent patient utterance, stripped of its '[MSG-ID] ' prefix."""
    for msg in reversed(conversation_history):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            return content.split("] ", 1)[-1] if content.startswith("[") else content
    return ""


def _last_assistant_message(conversation_history: List[dict]) -> str:
    """Return the most recent AI Nurse question, stripped of its '[MSG-ID] ' prefix."""
    for msg in reversed(conversation_history):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            return content.split("] ", 1)[-1] if content.startswith("[") else content
    return ""


# Strict JSON Schema for structured-output-capable providers (OpenAI, Gemini via its
# OpenAI-compatible endpoint, and others that support `response_format: json_schema`).
# This is the REAL fix for a provider returning an ad-hoc shape like {"symptoms": [...]}
# instead of the contract below - schema-mode forces conformance at the API level
# rather than relying on prompt wording + post-hoc normalization.
#
# `conflicts_detected` and `retrieved_sources` are intentionally excluded: the former
# is not consumed downstream (contradiction detection runs independently on merged
# facts), and the latter is populated by the app itself after the call, never by the
# model - both already have safe Pydantic defaults.
EXTRACTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fact_type": {"type": "string", "enum": ["SYMPTOM", "ONSET", "HISTORY", "MEDICATION", "ALLERGY", "VITAL"]},
                    "fact_key": {"type": "string"},
                    "fact_value": {"type": "string"},
                    "status": {"type": "string", "enum": ["PRESENT", "ABSENT", "UNKNOWN", "UNCERTAIN"]},
                    "confidence": {"type": "number"},
                    "evidence_message_id": {"type": "string"},
                },
                "required": ["fact_type", "fact_key", "fact_value", "status", "confidence", "evidence_message_id"],
                "additionalProperties": False,
            },
        },
        "missing_information": {"type": "array", "items": {"type": "string"}},
        "next_question": {"type": ["string", "null"]},
        "next_question_urdu": {"type": ["string", "null"]},
        "next_question_arabic": {"type": ["string", "null"]},
        "high_acuity_trigger": {"type": "boolean"},
        "high_acuity_reason": {"type": ["string", "null"]},
        "conversation_complete": {"type": "boolean"},
    },
    "required": [
        "facts", "missing_information", "next_question", "next_question_urdu",
        "next_question_arabic", "high_acuity_trigger", "high_acuity_reason", "conversation_complete",
    ],
    "additionalProperties": False,
}


class IClinicalConversationService(ABC):
    @abstractmethod
    async def extract_and_respond(
        self,
        conversation_history: List[dict],
        current_message_id: str,
        clinical_state: ClinicalAssessment,
        patient_language: str = "en",
    ) -> LLMExtractionOutput:
        ...


class OpenAIGPT4oConversationService(IClinicalConversationService):
    """GPT-4o conversation service with strict JSON output only."""

    def __init__(self, api_key: str, model: str = "gpt-4o", base_url: Optional[str] = None):
        import openai
        kwargs = {"api_key": api_key or "dummy-key"}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = openai.AsyncOpenAI(**kwargs)
        self.model = model

    async def extract_and_respond(
        self,
        conversation_history: List[dict],
        current_message_id: str,
        clinical_state: ClinicalAssessment,
        patient_language: str = "en",
    ) -> LLMExtractionOutput:
        import openai

        # RAG (spec §28): retrieve curated clinical reference material rather than
        # letting the model substitute its own general knowledge for the approved
        # protocol. Retrieval failure must never block the conversation - an empty
        # result just means no reference context is injected this turn (spec §39).
        retrieved: List[dict] = []
        try:
            from app.services.rag.knowledge import get_knowledge_service
            last_patient_text = _last_patient_message(conversation_history)
            if last_patient_text:
                knowledge_service = get_knowledge_service()
                retrieved = await knowledge_service.query(last_patient_text, n_results=3)
        except Exception as e:
            logger.warning("Knowledge retrieval failed - continuing without reference context: %s", e)
            retrieved = []

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "system",
                "content": (
                    f"Current clinical state (facts extracted so far):\n"
                    f"{json.dumps(clinical_state.model_dump(exclude={'all_facts'}), default=str, indent=2)}"
                ),
            },
        ]

        if retrieved:
            reference_lines = "\n".join(
                f"- [{r.get('section', 'reference')} v{r.get('version', '?')} "
                f"({r.get('publication_date', 'undated')})] {r.get('text', '')}"
                for r in retrieved
            )
            messages.append({
                "role": "system",
                "content": (
                    "Approved clinical reference material (use only if directly relevant; "
                    "do not substitute this for facts the patient actually reported):\n"
                    f"{reference_lines}"
                ),
            })

        messages += conversation_history

        # Attempt 1: strict JSON-schema mode. This is the real fix for providers
        # (Gemini's OpenAI-compatible endpoint in particular) that otherwise return
        # an ad-hoc shape like {"symptoms": [...]} instead of the required contract - 
        # schema mode forces conformance at the API level, not just via prompt wording.
        data = None
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "clinical_extraction", "schema": EXTRACTION_JSON_SCHEMA, "strict": True},
                },
                temperature=0.1,
                timeout=30,
            )
            data = self._parse_json_content(response.choices[0].message.content)
        except Exception as e:
            logger.warning("Structured json_schema call failed (%s) - retrying with looser json_object mode", e)

        # Attempt 2: looser "valid JSON, any shape" mode, for providers that don't
        # support schema-constrained output at all. Normalize whatever comes back.
        if data is None:
            try:
                response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    timeout=30,
                )
                data = self._parse_json_content(response.choices[0].message.content)
                data = self._normalize_loose_response(data, current_message_id)
            except Exception as e:
                logger.warning("json_object fallback also failed (%s) - using MockConversationService", e)
                mock = MockConversationService()
                return await mock.extract_and_respond(conversation_history, current_message_id, clinical_state, patient_language)

        try:
            data.setdefault("conflicts_detected", [])
            output = LLMExtractionOutput(**data)
        except Exception as e:
            logger.error("LLM output failed validation even after normalization: %s | data: %s", e, str(data)[:300])
            return self._safe_escalation_output()

        # Anti-repeat safeguard (spec §8/§39): if the model produced no new facts
        # AND its proposed next_question is (near-)identical to the question it just
        # asked, do not let the conversation loop forever - hand off to a clinician
        # with whatever has been gathered so far, rather than repeating indefinitely.
        last_ai_question = _last_assistant_message(conversation_history).strip().lower()
        proposed_question = (output.next_question or "").strip().lower()
        if not output.facts and proposed_question and last_ai_question and proposed_question == last_ai_question:
            output.next_question = "Thank you. A nurse will follow up with you shortly to go over the details."
            output.next_question_urdu = "شکریہ۔ نرس جلد آپ سے تفصیلات پر بات کرے گی۔"
            output.next_question_arabic = "شكراً لك. ستتابع معك ممرضة قريباً لمناقشة التفاصيل."
            output.conversation_complete = True
            if "STALLED_CONVERSATION" not in output.missing_information:
                output.missing_information.append("STALLED_CONVERSATION")

        # Attach retrieval provenance AFTER the LLM call - never requested from the
        # model itself, so it can't be fabricated (spec §28).
        output.retrieved_sources = [
            {
                "document": r.get("document"),
                "version": r.get("version"),
                "section": r.get("section"),
                "publication_date": r.get("publication_date"),
                "retrieved_passage": r.get("text"),
            }
            for r in retrieved
        ]
        return output

    @staticmethod
    def _parse_json_content(raw_content: Optional[str]) -> dict:
        """Strip an occasional markdown code fence and parse JSON. Raises on failure - 
        callers decide whether that means falling back to a looser mode or Mock."""
        raw = (raw_content or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```", 1)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0].strip()
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError(f"Expected a JSON object, got {type(data).__name__}")
        return data

    @staticmethod
    def _normalize_loose_response(data: dict, current_message_id: str) -> dict:
        """
        Best-effort normalization for providers that ignored the requested schema
        and returned their own shape (only reached when strict schema mode itself
        isn't supported at all - see Attempt 1 above). Handles the shapes actually
        observed in practice; anything still unrecognized just yields zero facts
        rather than raising, so the conversation degrades gracefully instead of
        crashing.
        """
        if "facts" not in data:
            raw_symptoms = data.get("symptoms") or data.get("findings") or []
            facts = []
            for item in raw_symptoms:
                if isinstance(item, dict):
                    key = item.get("symptom") or item.get("name") or item.get("fact_key") or "symptom"
                    value = item.get("severity") or item.get("value") or item.get("fact_value") or "PRESENT"
                    facts.append({
                        "fact_type": "SYMPTOM",
                        "fact_key": str(key).lower().replace(" ", "_"),
                        "fact_value": str(value),
                        "status": "PRESENT",
                        "confidence": 0.7,  # lower than a schema-conformant extraction - the shape itself was unreliable
                        "evidence_message_id": current_message_id,
                    })
                elif isinstance(item, str):
                    facts.append({
                        "fact_type": "SYMPTOM",
                        "fact_key": item.lower().replace(" ", "_"),
                        "fact_value": "PRESENT",
                        "status": "PRESENT",
                        "confidence": 0.7,
                        "evidence_message_id": current_message_id,
                    })
            data["facts"] = facts

        data.setdefault("missing_information", [])
        data.setdefault("high_acuity_trigger", False)
        data.setdefault("conversation_complete", False)
        data.setdefault("next_question_urdu", None)
        data.setdefault("next_question_arabic", None)
        data.setdefault("high_acuity_reason", None)

        if not data.get("next_question"):
            if data["facts"]:
                fk = data["facts"][0].get("fact_key", "symptom").replace("_", " ")
                data["next_question"] = f"When did the {fk} start, and how severe is it on a scale of 1 to 10?"
            else:
                data["next_question"] = "Could you describe what symptoms or trouble you are experiencing today?"

        return data

    def _safe_escalation_output(self) -> LLMExtractionOutput:
        """On any LLM failure, return a safe state that triggers clinician review."""
        return LLMExtractionOutput(
            facts=[],
            missing_information=["LLM_FAILURE_ESCALATE_TO_CLINICIAN"],
            next_question="I'm having trouble understanding. A nurse will assist you shortly.",
            high_acuity_trigger=True,
            high_acuity_reason="LLM failure - safe escalation to clinician review",
            conversation_complete=False,
        )


class MockConversationService(IClinicalConversationService):
    """
    Dynamic, context-aware clinical conversation mock service.
    Extracts symptoms, onset, and severity dynamically from patient text
    when running without an external LLM API key.
    """

    async def extract_and_respond(
        self,
        conversation_history,
        current_message_id: str,
        clinical_state: ClinicalAssessment,
        patient_language: str = "en",
    ) -> LLMExtractionOutput:
        # Find latest patient message (prefix-stripped, so keyword matching isn't
        # polluted by the "[MSG-ID] " evidence marker)
        last_msg = _last_patient_message(conversation_history).lower()

        facts: List[LLMExtractedFact] = []
        missing_info: List[str] = []
        next_q = "What brings you to the hospital today?"
        next_q_ur = "آپ کو آج کیا تکلیف ہے؟"
        next_q_ar = "ما الذي أحضرك إلى المستشفى اليوم؟"
        high_acuity = False
        high_reason = None
        complete = False

        # Keyword symptom matching (English, Romanized Urdu/Arabic, and native Urdu/Arabic script)
        if any(w in last_msg for w in ["shoulder", "kandhay", "کاندھے", "كتف"]):
            facts.append(LLMExtractedFact(
                fact_type="SYMPTOM", fact_key="pain_severity", fact_value="5",
                status="PRESENT", confidence=0.9, evidence_message_id=current_message_id
            ))
            facts.append(LLMExtractedFact(
                fact_type="SYMPTOM", fact_key="shoulder_pain", fact_value="PRESENT",
                status="PRESENT", confidence=0.95, evidence_message_id=current_message_id
            ))
            next_q = "When did the shoulder pain start, and does it spread anywhere else?"
            next_q_ur = "کاندھے کا درد کب شروع ہوا؟"
            next_q_ar = "متى بدأ ألم الكتف؟"

        elif any(w in last_msg for w in ["chest", "seene", "sadr", "سینے", "صدر", "الصدر"]):
            facts.append(LLMExtractedFact(
                fact_type="SYMPTOM", fact_key="chest_pain", fact_value="PRESENT",
                status="PRESENT", confidence=0.95, evidence_message_id=current_message_id
            ))
            if any(w in last_msg for w in ["severe", "bohat", "tez", "شدید", "بہت", "شديد"]):
                facts.append(LLMExtractedFact(
                    fact_type="SYMPTOM", fact_key="pain_severity", fact_value="8",
                    status="PRESENT", confidence=0.9, evidence_message_id=current_message_id
                ))
            next_q = "When did the chest pain start, and are you having any difficulty breathing?"
            next_q_ur = "سینے کا درد کب شروع ہوا اور کیا سانس میں تکلیف ہے؟"
            next_q_ar = "متى بدأ ألم الصدر وهل تعاني من صعوبة في التنفس؟"

        elif any(w in last_msg for w in ["breath", "saans", "tanaffus", "سانس", "تنفس", "التنفس"]):
            facts.append(LLMExtractedFact(
                fact_type="SYMPTOM", fact_key="breathing_difficulty", fact_value="PRESENT",
                status="PRESENT", confidence=0.95, evidence_message_id=current_message_id
            ))
            next_q = "How long have you had difficulty breathing?"
            next_q_ur = "سانس میں تکلیف کب سے ہے؟"
            next_q_ar = "منذ متى تعاني من صعوبة في التنفس؟"
            high_acuity = True
            high_reason = "Breathing difficulty reported by patient"

        elif any(w in last_msg for w in ["headache", "sar dard", "suda", "سر", "صداع", "رأس"]):
            facts.append(LLMExtractedFact(
                fact_type="SYMPTOM", fact_key="headache", fact_value="PRESENT",
                status="PRESENT", confidence=0.95, evidence_message_id=current_message_id
            ))
            if any(w in last_msg for w in ["severe", "bohat", "tez", "شدید", "بہت", "شديد"]):
                facts.append(LLMExtractedFact(
                    fact_type="SYMPTOM", fact_key="pain_severity", fact_value="8",
                    status="PRESENT", confidence=0.9, evidence_message_id=current_message_id
                ))
            next_q = "On a scale of 1 to 10, how severe is your headache?"
            next_q_ur = "1 سے 10 کے پیمانے پر، سر درد کتنا شدید ہے؟"
            next_q_ar = "على مقياس من 1 إلى 10، ما مدى شدة الصداع؟"

        elif any(w in last_msg for w in ["fever", "bukhar", "humma", "بخار", "حمى"]):
            facts.append(LLMExtractedFact(
                fact_type="SYMPTOM", fact_key="fever", fact_value="PRESENT",
                status="PRESENT", confidence=0.95, evidence_message_id=current_message_id
            ))
            next_q = "How many days have you had the fever?"
            next_q_ur = "بخار کتنے دنوں سے ہے؟"
            next_q_ar = "منذ كم يوم تعاني من الحمى؟"

        elif any(w in last_msg for w in ["bleed", "khoon", "خون", "نزيف", "دم"]):
            facts.append(LLMExtractedFact(
                fact_type="SYMPTOM", fact_key="bleeding", fact_value="PRESENT",
                status="PRESENT", confidence=0.95, evidence_message_id=current_message_id
            ))
            next_q = "Where is the bleeding and has it stopped?"
            next_q_ur = "خون کہاں سے نکل رہا ہے اور کیا یہ رک گیا ہے؟"
            next_q_ar = "من أين ينزف وهل توقف النزيف؟"
            high_acuity = True
            high_reason = "Bleeding reported"

        elif any(w in last_msg for w in ["stomach", "abdomen", "abdominal", "belly", "pet dard", "batn", "پیٹ", "معدة", "بطن"]):
            facts.append(LLMExtractedFact(
                fact_type="SYMPTOM", fact_key="abdominal_pain", fact_value="PRESENT",
                status="PRESENT", confidence=0.9, evidence_message_id=current_message_id
            ))
            next_q = "How long have you had the abdominal pain, and how severe is it on a scale of 1 to 10?"
            next_q_ur = "پیٹ کا درد کب سے ہے اور یہ کتنا شدید ہے؟"
            next_q_ar = "منذ متى تعاني من ألم البطن وما مدى شدته؟"

        elif any(w in last_msg for w in ["injury", "injured", "fell", "fracture", "wound", "zakhm", "چوٹ", "إصابة", "جرح"]):
            facts.append(LLMExtractedFact(
                fact_type="SYMPTOM", fact_key="injury", fact_value="PRESENT",
                status="PRESENT", confidence=0.9, evidence_message_id=current_message_id
            ))
            next_q = "How did the injury happen, and how severe is the pain from 1 to 10?"
            next_q_ur = "چوٹ کیسے لگی اور درد کتنا شدید ہے؟"
            next_q_ar = "كيف حدثت الإصابة وما مدى شدة الألم؟"

        elif any(w in last_msg for w in ["weak", "dizzy", "tired", "fatigue", "kamzori", "کمزوری", "دوخار", "دوار"]):
            facts.append(LLMExtractedFact(
                fact_type="SYMPTOM", fact_key="general_weakness", fact_value="PRESENT",
                status="PRESENT", confidence=0.85, evidence_message_id=current_message_id
            ))
            next_q = "How long have you been feeling this way?"
            next_q_ur = "آپ کب سے یہ محسوس کر رہے ہیں؟"
            next_q_ar = "منذ متى تشعر بذلك؟"

        elif any(w in last_msg for w in ["cramp", "cramps", "thigh", "spasm", "knee", "joint", "leg", "arm", "back", "neck", "shoulder", "hip", "foot", "ankle", "hand", "wrist", "pain", "hurt", "ache", "dard", "درد", "ألم"]):
            body_part = "pain"
            for bp in ["thigh cramps", "thigh cramp", "thigh", "cramps", "cramp", "knee joint", "knee", "joint", "shoulder", "back", "leg", "arm", "neck", "hip", "foot", "ankle", "hand", "wrist"]:
                if bp in last_msg:
                    body_part = f"{bp}" if ("cramp" in bp or "spasm" in bp) else f"{bp} pain"
                    break

            facts.append(LLMExtractedFact(
                fact_type="SYMPTOM", fact_key="pain_severity", fact_value="4",
                status="PRESENT", confidence=0.9, evidence_message_id=current_message_id
            ))
            facts.append(LLMExtractedFact(
                fact_type="SYMPTOM", fact_key="joint_pain" if "joint" in body_part or "knee" in body_part else "general_pain", fact_value="PRESENT",
                status="PRESENT", confidence=0.9, evidence_message_id=current_message_id
            ))

            if body_part != "pain":
                next_q = f"When did your {body_part} start, and how severe is it on a scale of 1 to 10?"
                next_q_ur = f"{body_part} کا درد کب شروع ہوا اور یہ کتنا شدید ہے؟"
                next_q_ar = f"متى بدأ ألم {body_part} وما مدى شدته؟"
            else:
                next_q = "Where is the pain located, when did it start, and how severe is it on a scale of 1 to 10?"
                next_q_ur = "درد کہاں ہو رہا ہے اور یہ کتنا شدید ہے؟"
                next_q_ar = "أين يوجد الألم ومتى بدأ وما مدى شدته؟"

        elif any(w in last_msg for w in ["certificate", "prescription", "paperwork", "form", "admin", "administrative"]):
            facts.append(LLMExtractedFact(
                fact_type="HISTORY", fact_key="administrative", fact_value="PRESENT",
                status="PRESENT", confidence=0.95, evidence_message_id=current_message_id
            ))
            next_q = "Thank you. Your administrative request has been recorded."
            complete = True

        elif any(w in last_msg for w in ["routine", "checkup", "chronic", "regular review", "follow-up", "followup", "review"]):
            facts.append(LLMExtractedFact(
                fact_type="HISTORY", fact_key="chronic_review", fact_value="PRESENT",
                status="PRESENT", confidence=0.95, evidence_message_id=current_message_id
            ))
            next_q = "Thank you. Your routine chronic condition review visit has been recorded."
            complete = True

        elif (
            any(re.search(r'\b' + re.escape(w) + r'\b', last_msg) for w in ["begin", "okay", "hello", "hi", "hey", "salam", "السلام", "مرحبا", "ہیلو"])
            or "name is" in last_msg or "my name" in last_msg
        ) and not any(w in last_msg for w in ["ago", "minute", "hour", "started", "since", "day", "week", "month", "year", "ہفتوں", "ہفتے", "دن", "منذ"]):
            next_q = "Hello! Please describe what symptoms or health trouble you are experiencing today."
            next_q_ur = "سلام! براہ کرم بتائیں کہ آج آپ کو کیا تکلیف یا علامات پیش آ رہی ہیں؟"
            next_q_ar = "مرحباً! يرجى وصف الأعراض أو المشاكل الصحية التي تعاني منها اليوم."

        elif any(w in last_msg for w in [
            "ago", "minute", "hour", "day", "min", "se", "started", "since",
            "week", "month", "year", "yesterday", "today",
            "ہفتوں", "ہفتے", "دن", "گھنٹے", "منٹ", "ماہ", "سال", "سے", "پہلے", "آج", "کل",
            "منذ", "ساعة", "ساعات", "أسبوع", "أسابيع", "أيام", "يوم", "شهر", "أشهر", "سنة", "سنوات",
        ]):
            facts.append(LLMExtractedFact(
                fact_type="ONSET", fact_key="onset", fact_value=last_msg,
                status="PRESENT", confidence=0.9, evidence_message_id=current_message_id
            ))
            next_q = "Thank you. Is the pain getting worse, improving, or staying the same?"
            next_q_ur = "شکریہ۔ کیا درد مزید بڑھ رہا ہے، بہتر ہو رہا ہے، یا ویسا ہی ہے؟"
            next_q_ar = "شكراً لك. هل الألم يزداد سوءاً، أم يتحسن، أم يظل كما هو؟"
            complete = True

        else:
            # Generic response asking for details. If we've already asked this once
            # (i.e. the patient's previous reply also didn't match a known pattern),
            # do NOT loop forever - accept what we have and hand off to a clinician
            # rather than repeating the same question indefinitely (spec §39).
            already_asked_generic = any(
                msg.get("role") == "assistant" and "how long this has been happening" in msg.get("content", "").lower()
                for msg in conversation_history[:-1]
            )
            if already_asked_generic:
                next_q = "Thank you. A nurse will follow up with you shortly to go over the details."
                next_q_ur = "شکریہ۔ نرس جلد آپ سے تفصیلات پر بات کرے گی۔"
                next_q_ar = "شكراً لك. ستتابع معك ممرضة قريباً لمناقشة التفاصيل."
                complete = True
            else:
                next_q = "Can you tell me more about how long this has been happening and how severe it is?"
                next_q_ur = "کیا آپ بتا سکتے ہیں کہ یہ کب سے ہو رہا ہے اور کتنا شدید ہے؟"
                next_q_ar = "هل يمكنك إخباري منذ متى يحدث هذا ومدى شدته؟"

        return LLMExtractionOutput(
            facts=facts,
            missing_information=missing_info,
            conflicts_detected=[],
            next_question=next_q,
            next_question_urdu=next_q_ur,
            next_question_arabic=next_q_ar,
            high_acuity_trigger=high_acuity,
            high_acuity_reason=high_reason,
            conversation_complete=complete,
        )


def get_conversation_service() -> IClinicalConversationService:
    from app.core.config import get_settings
    settings = get_settings()

    if settings.LLM_PROVIDER in ("openai_gpt4o", "openai_compatible", "groq", "gemini", "openrouter", "ollama"):
        if not settings.OPENAI_API_KEY and not settings.OPENAI_BASE_URL and settings.LLM_PROVIDER != "ollama":
            logger.warning("No API key or base URL - using MockConversationService")
            return MockConversationService()
        return OpenAIGPT4oConversationService(
            api_key=settings.OPENAI_API_KEY,
            model=settings.OPENAI_LLM_MODEL,
            base_url=settings.OPENAI_BASE_URL or None,
        )
    elif settings.LLM_PROVIDER == "mock":
        return MockConversationService()
    else:
        raise ValueError(f"Unknown LLM provider: {settings.LLM_PROVIDER}")
