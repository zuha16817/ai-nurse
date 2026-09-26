"""
Regression test for a critical bug found during manual end-to-end testing:
nurse-entered objective AVPU/GCS vitals were recorded in the database but never
actually reached `ClinicalAssessment.consciousness` - only `vital_signs` - so
discriminators like RULE-RED-003 ("consciousness.avpu equals Unresponsive")
silently never fired for objectively-measured consciousness readings, only for
values that happened to come from conversation-extracted facts.

This is exactly the kind of defect that unit tests miss (they construct
ClinicalAssessment directly, bypassing the DB-reconstruction path) and that only
surfaces when the real API path is exercised end-to-end.
"""

import pytest
import pytest_asyncio
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.models.database import Base
from app.models.models import TriageSession, Patient, VitalSigns, ClinicalFact as ClinicalFactORM
from app.api.triage import _rebuild_assessment


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
class TestVitalsReachTheEngine:
    async def test_objective_avpu_reaches_consciousness_field(self, db_session):
        patient = Patient(visit_number="P-TEST-1")
        db_session.add(patient)
        await db_session.flush()

        session = TriageSession(patient_id=patient.id)
        db_session.add(session)
        await db_session.flush()

        vitals = VitalSigns(session_id=session.id, avpu="Unresponsive", entered_by="nurse_test")
        db_session.add(vitals)
        await db_session.commit()

        assessment = await _rebuild_assessment(session.id, db_session)

        # This is the field the deterministic rules engine actually reads.
        assert assessment.consciousness.avpu == "Unresponsive"
        # And it must also still be visible as the objective measurement itself.
        assert assessment.vital_signs.avpu == "Unresponsive"

    async def test_objective_gcs_reaches_consciousness_field(self, db_session):
        patient = Patient(visit_number="P-TEST-2")
        db_session.add(patient)
        await db_session.flush()
        session = TriageSession(patient_id=patient.id)
        db_session.add(session)
        await db_session.flush()

        vitals = VitalSigns(session_id=session.id, gcs=6, entered_by="nurse_test")
        db_session.add(vitals)
        await db_session.commit()

        assessment = await _rebuild_assessment(session.id, db_session)
        assert assessment.consciousness.gcs == 6

    async def test_objective_avpu_overrides_stale_patient_reported_value(self, db_session):
        """
        Objectively-measured consciousness must win over an earlier patient-reported
        value for the same field - never the other way around.
        """
        patient = Patient(visit_number="P-TEST-3")
        db_session.add(patient)
        await db_session.flush()
        session = TriageSession(patient_id=patient.id)
        db_session.add(session)
        await db_session.flush()

        # A stale/lower-acuity patient-reported fact from earlier in the conversation.
        fact = ClinicalFactORM(
            session_id=session.id, fact_type="SYMPTOM", fact_key="consciousness_avpu",
            fact_value="Alert", status="PRESENT", confidence=0.8, source="PATIENT_REPORTED",
        )
        db_session.add(fact)
        vitals = VitalSigns(session_id=session.id, avpu="Unresponsive", entered_by="nurse_test")
        db_session.add(vitals)
        await db_session.commit()

        assessment = await _rebuild_assessment(session.id, db_session)
        assert assessment.consciousness.avpu == "Unresponsive"

    async def test_patient_age_and_pregnancy_reach_assessment(self, db_session):
        patient = Patient(visit_number="P-TEST-5", age=0, pregnancy_status="PREGNANT",
                          preferred_language="ur")
        db_session.add(patient)
        await db_session.flush()
        session = TriageSession(patient_id=patient.id)
        db_session.add(session)
        await db_session.commit()

        assessment = await _rebuild_assessment(session.id, db_session)
        assert assessment.patient_age == 0
        assert assessment.pregnancy_status == "PREGNANT"
        assert assessment.patient_language == "ur"

    async def test_unknown_age_stays_none(self, db_session):
        """Missing intake data must stay unknown, never become a default like 0."""
        patient = Patient(visit_number="P-TEST-6")
        db_session.add(patient)
        await db_session.flush()
        session = TriageSession(patient_id=patient.id)
        db_session.add(session)
        await db_session.commit()

        assessment = await _rebuild_assessment(session.id, db_session)
        assert assessment.patient_age is None
        assert assessment.pregnancy_status == "UNKNOWN"

    async def test_infant_with_fever_fires_orange_rule_end_to_end(self, db_session):
        from app.services.triage.engine import TriageEngine, load_rules
        patient = Patient(visit_number="P-TEST-7", age=0)
        db_session.add(patient)
        await db_session.flush()
        session = TriageSession(patient_id=patient.id)
        db_session.add(session)
        await db_session.flush()
        db_session.add(VitalSigns(session_id=session.id, temperature=38.6, entered_by="nurse_test"))
        await db_session.commit()

        assessment = await _rebuild_assessment(session.id, db_session)
        result = TriageEngine().evaluate(assessment, load_rules("1.0.0"))
        assert "RULE-ORANGE-011" in [r.rule_id for r in result.triggered_rules]
        assert result.colour.value == "ORANGE"

    async def test_pregnant_with_bleeding_fires_orange_rule_end_to_end(self, db_session):
        from app.services.triage.engine import TriageEngine, load_rules
        patient = Patient(visit_number="P-TEST-8", age=29, pregnancy_status="PREGNANT")
        db_session.add(patient)
        await db_session.flush()
        session = TriageSession(patient_id=patient.id)
        db_session.add(session)
        await db_session.flush()
        db_session.add(ClinicalFactORM(
            session_id=session.id, fact_type="SYMPTOM", fact_key="bleeding",
            fact_value="PRESENT", status="PRESENT", confidence=0.9, source="PATIENT_REPORTED",
        ))
        await db_session.commit()

        assessment = await _rebuild_assessment(session.id, db_session)
        result = TriageEngine().evaluate(assessment, load_rules("1.0.0"))
        assert "RULE-ORANGE-010" in [r.rule_id for r in result.triggered_rules]

    async def test_nurse_pain_score_reaches_pain_severity(self, db_session):
        patient = Patient(visit_number="P-TEST-9")
        db_session.add(patient)
        await db_session.flush()
        session = TriageSession(patient_id=patient.id)
        db_session.add(session)
        await db_session.flush()
        db_session.add(VitalSigns(session_id=session.id, pain_score=9, entered_by="nurse_test"))
        await db_session.commit()

        assessment = await _rebuild_assessment(session.id, db_session)
        assert assessment.pain.severity == 9
        assert assessment.pain.present.value == "PRESENT"

    async def test_nurse_pain_score_overrides_patient_reported_severity(self, db_session):
        patient = Patient(visit_number="P-TEST-10")
        db_session.add(patient)
        await db_session.flush()
        session = TriageSession(patient_id=patient.id)
        db_session.add(session)
        await db_session.flush()
        db_session.add(ClinicalFactORM(
            session_id=session.id, fact_type="SYMPTOM", fact_key="pain_severity",
            fact_value="3", status="PRESENT", confidence=0.9, source="PATIENT_REPORTED",
        ))
        db_session.add(VitalSigns(session_id=session.id, pain_score=8, entered_by="nurse_test"))
        await db_session.commit()

        assessment = await _rebuild_assessment(session.id, db_session)
        assert assessment.pain.severity == 8

    async def test_saving_temperature_alone_does_not_assert_alert(self, db_session):
        """
        Regression: the nurse form used to default AVPU to "Alert" and always submit it,
        so recording ANY vital sign silently claimed the patient was alert.
        A vitals entry with no AVPU must leave consciousness unknown.
        """
        patient = Patient(visit_number="P-TEST-11")
        db_session.add(patient)
        await db_session.flush()
        session = TriageSession(patient_id=patient.id)
        db_session.add(session)
        await db_session.flush()
        db_session.add(VitalSigns(session_id=session.id, temperature=37.0, avpu=None, entered_by="n"))
        await db_session.commit()

        assessment = await _rebuild_assessment(session.id, db_session)
        assert assessment.consciousness.avpu is None
        assert assessment.consciousness.status.value == "UNKNOWN"

    async def test_later_partial_entry_does_not_erase_earlier_avpu(self, db_session):
        """An 'Unresponsive' reading must survive a later entry that only records a temperature."""
        from datetime import datetime, timezone, timedelta
        patient = Patient(visit_number="P-TEST-12")
        db_session.add(patient)
        await db_session.flush()
        session = TriageSession(patient_id=patient.id)
        db_session.add(session)
        await db_session.flush()
        t0 = datetime.now(timezone.utc)
        db_session.add(VitalSigns(session_id=session.id, avpu="Unresponsive", entered_by="n",
                                  recorded_at=t0 - timedelta(minutes=10)))
        db_session.add(VitalSigns(session_id=session.id, temperature=37.1, entered_by="n", recorded_at=t0))
        await db_session.commit()

        assessment = await _rebuild_assessment(session.id, db_session)
        assert assessment.consciousness.avpu == "Unresponsive"
        assert assessment.vital_signs.temperature == 37.1

    async def test_newer_value_replaces_older_for_same_field(self, db_session):
        from datetime import datetime, timezone, timedelta
        patient = Patient(visit_number="P-TEST-13")
        db_session.add(patient)
        await db_session.flush()
        session = TriageSession(patient_id=patient.id)
        db_session.add(session)
        await db_session.flush()
        t0 = datetime.now(timezone.utc)
        db_session.add(VitalSigns(session_id=session.id, avpu="Voice", spo2=90, entered_by="n",
                                  recorded_at=t0 - timedelta(minutes=10)))
        db_session.add(VitalSigns(session_id=session.id, avpu="Alert", entered_by="n", recorded_at=t0))
        await db_session.commit()

        assessment = await _rebuild_assessment(session.id, db_session)
        assert assessment.consciousness.avpu == "Alert"   # the nurse re-assessed
        assert assessment.vital_signs.spo2 == 90           # untouched field carried forward

    async def test_no_vitals_leaves_consciousness_unknown(self, db_session):
        """Absence of a vitals entry must never be coerced into a finding either way."""
        patient = Patient(visit_number="P-TEST-4")
        db_session.add(patient)
        await db_session.flush()
        session = TriageSession(patient_id=patient.id)
        db_session.add(session)
        await db_session.commit()

        assessment = await _rebuild_assessment(session.id, db_session)
        assert assessment.consciousness.avpu is None
