"""
STT Service Interface and OpenAI Whisper implementation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import logging
import tempfile
import os

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    text: str                       # original transcript in detected language
    detected_language: str          # ISO 639-1 code
    duration_seconds: float
    confidence: float = 1.0         # Whisper doesn't expose this directly


class ISpeechToTextService(ABC):
    @abstractmethod
    async def transcribe(
        self, audio_bytes: bytes, filename: str = "audio.webm", expected_language: str = None,
    ) -> TranscriptionResult:
        """
        Transcribe audio bytes to text.

        `expected_language` is a hint only - real STT (Whisper) auto-detects and
        ignores it. It exists so the offline Mock, which cannot actually process
        audio, can still respect the language the patient selected in the UI
        instead of always returning the same hardcoded language.
        """
        ...


class OpenAIWhisperSTT(ISpeechToTextService):
    """
    OpenAI Whisper STT implementation.
    Supports: English, Urdu, Arabic, and 99 other languages.
    """

    def __init__(self, api_key: str, model: str = "whisper-1"):
        import openai
        self.client = openai.AsyncOpenAI(api_key=api_key)
        self.model = model

    async def transcribe(
        self, audio_bytes: bytes, filename: str = "audio.webm", expected_language: str = None,
    ) -> TranscriptionResult:
        import openai

        # Write to temp file (Whisper needs a file object)
        suffix = os.path.splitext(filename)[1] or ".webm"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as audio_file:
                response = await self.client.audio.transcriptions.create(
                    model=self.model,
                    file=audio_file,
                    response_format="verbose_json",
                    # Let Whisper auto-detect language
                )

            detected_lang = getattr(response, "language", "en") or "en"
            # Normalize to ISO 639-1
            lang_map = {"urdu": "ur", "arabic": "ar", "english": "en"}
            detected_lang = lang_map.get(detected_lang.lower(), detected_lang[:2])

            duration = getattr(response, "duration", 0.0) or 0.0
            text = response.text.strip()

            # Never log transcript content to ordinary application logs (spec §31) - 
            # the text itself belongs only in the access-restricted audit trail.
            logger.info("STT: lang=%s, duration=%.1fs, length=%d chars", detected_lang, duration, len(text))

            return TranscriptionResult(
                text=text,
                detected_language=detected_lang,
                duration_seconds=float(duration),
            )

        except openai.APITimeoutError:
            logger.error("STT timeout - escalating to text fallback")
            raise
        except openai.APIError as e:
            logger.error("STT API error: %s", e)
            if "insufficient_quota" in str(e) or "credit_balance_exhausted" in str(e):
                logger.warning("Whisper STT quota exhausted - falling back to MockSTT")
                mock = MockSTT()
                return await mock.transcribe(audio_bytes, filename, expected_language)
            raise
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)


class MockSTT(ISpeechToTextService):
    """
    Mock STT for testing without API keys.

    Cannot actually process the recorded audio - it always returns one of a fixed
    set of canned phrases. To avoid the confusing appearance of "detecting" a
    language you never spoke, it uses the patient's selected UI language as a hint
    (`expected_language`) rather than always defaulting to one language regardless
    of what was selected.
    """

    CANNED_PHRASES = {
        "en": [
            "[Mock Voice Recording] I have severe chest pain and trouble breathing.",
            "[Mock Voice Recording] The pain started about 30 minutes ago.",
            "[Mock Voice Recording] It feels like a heavy pressure, about 8 out of 10.",
        ],
        "ur": [
            "[Mock Voice Recording] Mujhe seene mein dard ho raha hai.",
            "[Mock Voice Recording] Yeh dard adhay ghantay pehle shuru hua tha.",
        ],
        "ar": [
            "[Mock Voice Recording] أشعر بألم شديد في الصدر.",
            "[Mock Voice Recording] بدأ الألم منذ حوالي نصف ساعة.",
        ],
    }

    _call_count = 0

    async def transcribe(
        self, audio_bytes: bytes, filename: str = "audio.webm", expected_language: str = None,
    ) -> TranscriptionResult:
        lang = expected_language if expected_language in self.CANNED_PHRASES else "en"
        phrases = self.CANNED_PHRASES[lang]
        idx = MockSTT._call_count % len(phrases)
        MockSTT._call_count += 1

        return TranscriptionResult(
            text=phrases[idx],
            detected_language=lang,
            duration_seconds=3.0,
        )


def get_stt_service() -> ISpeechToTextService:
    from app.core.config import get_settings
    settings = get_settings()

    if settings.STT_PROVIDER == "openai_whisper":
        if not settings.OPENAI_API_KEY:
            logger.warning("No OpenAI API key - falling back to MockSTT")
            return MockSTT()
        return OpenAIWhisperSTT(api_key=settings.OPENAI_API_KEY, model=settings.OPENAI_STT_MODEL)
    elif settings.STT_PROVIDER == "mock":
        return MockSTT()
    else:
        raise ValueError(f"Unknown STT provider: {settings.STT_PROVIDER}")
