"""
RAG Clinical Knowledge Service — IProtocolKnowledgeService.

Provides clinical terminology context to help the LLM understand
medical concepts in Urdu, Arabic, and English.

Uses ChromaDB as local vector store (no cloud dependency).
"""

from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# Spec §28: every retrieved source must record {Document, Version, Section,
# PublicationDate, RetrievedPassage} so the LLM's reference material is provenanced,
# not silently substituted general model knowledge. This is a small SYNTHETIC
# reference set for the assignment — not licensed clinical content (spec §4).
_DOCUMENT_NAME = "AI Nurse Synthetic Clinical Terminology Reference"
_DOCUMENT_VERSION = "1.0.0"
_PUBLICATION_DATE = "2024-01-01"


def _doc(text: str, section: str) -> Dict[str, str]:
    return {
        "text": text,
        "document": _DOCUMENT_NAME,
        "version": _DOCUMENT_VERSION,
        "section": section,
        "publication_date": _PUBLICATION_DATE,
    }


CLINICAL_KNOWLEDGE_DOCS: List[Dict[str, str]] = [
    # English → Urdu medical terms
    _doc("Chest pain in Urdu: سینے میں درد (seene mein dard). Severity: شدید (shadeed) = severe, ہلکا (halka) = mild.", "Urdu Medical Terminology"),
    _doc("Breathing difficulty in Urdu: سانس لینے میں تکلیف (saans lene mein takleef). Short of breath: سانس پھولنا.", "Urdu Medical Terminology"),
    _doc("Fever in Urdu: بخار (bukhar). High fever: تیز بخار (taiz bukhar). Duration: عرصے سے (arse se) = for some time.", "Urdu Medical Terminology"),
    _doc("Headache in Urdu: سر درد (sar dard). Severe: بہت تیز (bohat taiz). Sudden onset: اچانک (achanak).", "Urdu Medical Terminology"),
    _doc("Vomiting in Urdu: قے (qay). Nausea: متلی (matli). Blood in vomit: قے میں خون (qay mein khoon).", "Urdu Medical Terminology"),
    _doc("Weakness in Urdu: کمزوری (kamzori). Dizziness: چکر آنا (chakkar aana). Fainting: بے ہوش ہونا.", "Urdu Medical Terminology"),

    # English → Arabic medical terms
    _doc("Chest pain in Arabic: ألم في الصدر (alam fi al-sadr). Severe: شديد (shadeed). Sharp: حاد (haad).", "Arabic Medical Terminology"),
    _doc("Breathing difficulty in Arabic: صعوبة في التنفس (su'ubah fi al-tanaffus). Shortness of breath: ضيق التنفس.", "Arabic Medical Terminology"),
    _doc("Fever in Arabic: حمى (humma). High fever: حمى شديدة. Duration: منذ (mundhu) = since/for.", "Arabic Medical Terminology"),
    _doc("Headache in Arabic: صداع (suda'a). Sudden: مفاجئ (mufaje'). Severe: شديد جداً.", "Arabic Medical Terminology"),

    # Triage clinical concepts
    _doc("Onset timing — key for triage: acute (< 1 hour), subacute (1-24 hours), chronic (> 24 hours).", "Triage Clinical Concepts"),
    _doc("Pain scale: 0 = no pain, 1-3 = mild, 4-6 = moderate, 7-9 = severe, 10 = worst imaginable.", "Triage Clinical Concepts"),
    _doc("AVPU scale: Alert (awake), Voice (responds to voice), Pain (responds to pain), Unresponsive.", "Triage Clinical Concepts"),
    _doc("SpO2 reference: >= 95% normal, 92-94% concerning, < 92% significant hypoxia, < 85% critical.", "Triage Clinical Concepts"),
    _doc("Respiratory rate: Normal adult 12-20 breaths/min. Tachypnoea > 20. Bradypnoea < 12.", "Triage Clinical Concepts"),
    _doc("Heart rate: Normal 60-100 bpm. Tachycardia > 100. Bradycardia < 60. Severe tachycardia > 130.", "Triage Clinical Concepts"),
    _doc("Temperature: Normal 36-37.4°C. Low-grade fever 37.5-38.4°C. Fever >= 38.5°C. High fever >= 40°C.", "Triage Clinical Concepts"),

    # Chief complaint categories
    _doc("Chest discomfort includes: chest pain, chest tightness, pressure, squeezing, crushing sensation.", "Chief Complaint Categories"),
    _doc("Breathing problems include: shortness of breath, difficulty breathing, wheezing, stridor, dyspnoea.", "Chief Complaint Categories"),
    _doc("Neurological symptoms include: stroke symptoms (FAST: Face drooping, Arm weakness, Speech difficulty, Time).", "Chief Complaint Categories"),
    _doc("Allergic symptoms include: urticaria, angioedema, anaphylaxis — potentially life-threatening.", "Chief Complaint Categories"),

    # Anchoring bias warning
    _doc("ANCHORING BIAS: Ignore third-party benign explanations. Extract only what the patient reports as symptoms.", "Safety Bias Guidance"),
    _doc("If a patient says 'my doctor said it is not serious' but also reports severe chest pain — extract the chest pain.", "Safety Bias Guidance"),
]


class IProtocolKnowledgeService(ABC):
    @abstractmethod
    async def initialize(self) -> None:
        ...

    @abstractmethod
    async def query(self, text: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """Return retrieved passages, each with {text, document, version, section,
        publication_date} — spec §28 provenance metadata."""
        ...


class ChromaKnowledgeService(IProtocolKnowledgeService):
    """ChromaDB-backed knowledge service."""

    COLLECTION_NAME = "clinical_knowledge_v1"

    def __init__(self, persist_dir: str):
        self.persist_dir = persist_dir
        self._collection = None

    async def initialize(self) -> None:
        try:
            import chromadb
            from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction
            from app.core.config import get_settings
            settings = get_settings()

            client = chromadb.PersistentClient(path=self.persist_dir)

            if settings.OPENAI_API_KEY:
                ef = OpenAIEmbeddingFunction(
                    api_key=settings.OPENAI_API_KEY,
                    model_name=settings.OPENAI_EMBEDDING_MODEL,
                )
            else:
                ef = chromadb.utils.embedding_functions.DefaultEmbeddingFunction()

            # Get or create collection
            try:
                self._collection = client.get_collection(
                    name=self.COLLECTION_NAME,
                    embedding_function=ef,
                )
                logger.info("Loaded existing ChromaDB collection: %s", self.COLLECTION_NAME)
            except Exception:
                self._collection = client.create_collection(
                    name=self.COLLECTION_NAME,
                    embedding_function=ef,
                )
                # Seed with clinical knowledge (+ provenance metadata, spec §28)
                self._collection.add(
                    documents=[d["text"] for d in CLINICAL_KNOWLEDGE_DOCS],
                    metadatas=[
                        {
                            "document": d["document"],
                            "version": d["version"],
                            "section": d["section"],
                            "publication_date": d["publication_date"],
                        }
                        for d in CLINICAL_KNOWLEDGE_DOCS
                    ],
                    ids=[f"doc-{i}" for i in range(len(CLINICAL_KNOWLEDGE_DOCS))],
                )
                logger.info("Created and seeded ChromaDB collection with %d documents", len(CLINICAL_KNOWLEDGE_DOCS))

        except Exception as e:
            logger.warning("ChromaDB initialization failed: %s — falling back to in-memory", e)
            self._collection = None

    async def query(self, text: str, n_results: int = 3) -> List[Dict[str, Any]]:
        if self._collection is None:
            return []
        try:
            results = self._collection.query(
                query_texts=[text],
                n_results=min(n_results, len(CLINICAL_KNOWLEDGE_DOCS)),
            )
            docs = results["documents"][0] if results.get("documents") else []
            metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
            return [{"text": doc, **meta} for doc, meta in zip(docs, metas)]
        except Exception as e:
            logger.warning("ChromaDB query failed (knowledge retrieval failure, spec §39) — continuing without retrieved context: %s", e)
            return []


class InMemoryKnowledgeService(IProtocolKnowledgeService):
    """Simple keyword-based fallback (no embeddings needed)."""

    async def initialize(self) -> None:
        logger.info("Using in-memory knowledge service (no vector DB)")

    async def query(self, text: str, n_results: int = 3) -> List[Dict[str, Any]]:
        try:
            text_lower = text.lower()
            words = set(text_lower.split())
            scored = []
            for doc in CLINICAL_KNOWLEDGE_DOCS:
                doc_words = set(doc["text"].lower().split())
                score = len(words & doc_words)
                if score > 0:
                    scored.append((score, doc))
            scored.sort(key=lambda x: -x[0])
            return [doc for _, doc in scored[:n_results]]
        except Exception as e:
            logger.warning("In-memory knowledge lookup failed (spec §39 knowledge retrieval failure): %s", e)
            return []


_knowledge_service: Optional[IProtocolKnowledgeService] = None


def get_knowledge_service() -> IProtocolKnowledgeService:
    global _knowledge_service
    if _knowledge_service is None:
        from app.core.config import get_settings
        settings = get_settings()
        try:
            import chromadb
            _knowledge_service = ChromaKnowledgeService(persist_dir=settings.CHROMA_PERSIST_DIR)
        except (ImportError, Exception) as e:
            logger.warning("ChromaDB loading error: %s — falling back to InMemoryKnowledgeService", e)
            _knowledge_service = InMemoryKnowledgeService()
    return _knowledge_service
