"""
ITranslationService - English normalisation of patient statements.

Spec §7/§15: the system must preserve BOTH the original patient statement AND a
normalized (English) clinical interpretation. The original is never discarded or
replaced - this service only ever ADDS a translated_text alongside it.

Failure mode (spec §39): translation must never block the pipeline. On any failure
the original text is preserved and used as-is.
"""

from __future__ import annotations
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class ITranslationService(ABC):
    @abstractmethod
    async def translate_to_english(self, text: str, source_language: str) -> str:
        ...


class OpenAITranslationService(ITranslationService):
    """LLM-based translation - used only to normalise text, never to decide acuity."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        import openai
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = model

    async def translate_to_english(self, text: str, source_language: str) -> str:
        if source_language == "en" or not text.strip():
            return text
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Translate the patient's clinical statement to English. "
                            "Return ONLY the translation, with no commentary, quotes, or preamble."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                temperature=0,
                timeout=15,
            )
            translated = response.choices[0].message.content
            return translated.strip() if translated else text
        except Exception as e:
            logger.warning("Translation failed (spec §39 translation failure) - preserving original text: %s", e)
            return text


class MockTranslationService(ITranslationService):
    """Small phrase-book translator for offline/dev use (no API key required)."""

    PHRASES = {
        "seene mein": "in the chest",
        "bohat tez dard": "very severe pain",
        "saans nahi": "no breathing",
        "بخار": "fever",
        "سینے میں درد": "chest pain",
        "سانس لینے میں تکلیف": "difficulty breathing",
        "الم في الصدر": "chest pain",
        "صعوبة في التنفس": "difficulty breathing",
    }

    async def translate_to_english(self, text: str, source_language: str) -> str:
        if source_language == "en" or not text.strip():
            return text
        lowered = text.lower()
        for phrase, english in self.PHRASES.items():
            if phrase.lower() in lowered:
                return english
        return f"[untranslated {source_language} text - translation service unavailable]"


def get_translation_service() -> ITranslationService:
    from app.core.config import get_settings
    settings = get_settings()

    if settings.TRANSLATION_PROVIDER == "openai" and settings.OPENAI_API_KEY:
        return OpenAITranslationService(settings.OPENAI_API_KEY, settings.OPENAI_TRANSLATION_MODEL)
    return MockTranslationService()
