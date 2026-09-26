"""
RAG / Clinical Knowledge Layer tests (spec §28).

Every retrieved passage must carry provenance metadata - a document, version,
section and publication date - so the LLM's reference material is never
indistinguishable from its own unverified general knowledge.
"""

import pytest
import sys, os, asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.rag.knowledge import InMemoryKnowledgeService, CLINICAL_KNOWLEDGE_DOCS


@pytest.fixture
def service():
    return InMemoryKnowledgeService()


class TestKnowledgeProvenance:
    def test_seed_documents_all_carry_required_metadata(self):
        required = {"text", "document", "version", "section", "publication_date"}
        for doc in CLINICAL_KNOWLEDGE_DOCS:
            assert required.issubset(doc.keys())
            assert doc["text"]
            assert doc["section"]

    def test_query_returns_provenanced_results(self, service):
        results = asyncio.run(service.query("chest pain seene mein dard", n_results=3))
        assert len(results) > 0
        for r in results:
            assert "text" in r
            assert "document" in r
            assert "version" in r
            assert "section" in r
            assert "publication_date" in r

    def test_irrelevant_query_returns_no_forced_matches(self, service):
        results = asyncio.run(service.query("xyzabc123nonsense", n_results=3))
        assert results == []

    def test_query_never_raises_on_internal_failure(self, service):
        """Knowledge retrieval failure (spec §39) must degrade to an empty list,
        never propagate and block the conversation pipeline."""
        results = asyncio.run(service.query("", n_results=3))
        assert results == []
