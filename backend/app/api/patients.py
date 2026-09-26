"""Patients API - registration and management."""

import uuid
import random
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from app.models.database import get_db
from app.models.models import Patient, TriageSession
from app.core.security import get_current_user
from app.services.audit import get_audit_service, AuditAction

router = APIRouter()
audit = get_audit_service()


def generate_visit_number() -> str:
    return f"P-{random.randint(1000, 9999)}"


class PatientCreate(BaseModel):
    age: Optional[int] = None
    biological_sex: Optional[str] = "UNKNOWN"
    preferred_language: str = "en"
    arrival_method: Optional[str] = None
    pregnancy_status: str = "UNKNOWN"
    is_synthetic: bool = False


class PatientResponse(BaseModel):
    id: str
    visit_number: str
    age: Optional[int]
    biological_sex: Optional[str]
    preferred_language: str
    arrival_method: Optional[str]
    pregnancy_status: str

    class Config:
        from_attributes = True


@router.post("/", status_code=201)
async def register_patient(
    body: PatientCreate,
    db: AsyncSession = Depends(get_db),
):
    """Register a new patient and create their first triage session."""
    # Ensure unique visit number
    for _ in range(10):
        vn = generate_visit_number()
        existing = await db.execute(select(Patient).where(Patient.visit_number == vn))
        if not existing.scalar_one_or_none():
            break

    patient = Patient(
        visit_number=vn,
        age=body.age,
        biological_sex=body.biological_sex,
        preferred_language=body.preferred_language,
        arrival_method=body.arrival_method,
        pregnancy_status=body.pregnancy_status,
        is_synthetic=body.is_synthetic,
    )
    db.add(patient)
    await db.flush()

    # Auto-create first triage session
    session = TriageSession(patient_id=patient.id, session_number=1)
    db.add(session)
    await db.commit()
    await db.refresh(patient)

    await audit.log(
        db, AuditAction.PATIENT_REGISTERED,
        session_id=session.id,
        actor="patient_kiosk",
        detail={"visit_number": vn, "language": body.preferred_language},
    )

    return {
        "id": patient.id,
        "visit_number": patient.visit_number,
        "session_id": session.id,
        "age": patient.age,
        "biological_sex": patient.biological_sex,
        "preferred_language": patient.preferred_language,
        "arrival_method": patient.arrival_method,
        "pregnancy_status": patient.pregnancy_status,
    }


@router.get("/{patient_id}", response_model=PatientResponse)
async def get_patient(
    patient_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    result = await db.execute(select(Patient).where(Patient.id == patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@router.get("/")
async def list_patients(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all active patients - used by Command Center."""
    result = await db.execute(select(Patient).order_by(Patient.arrival_time.desc()))
    patients = result.scalars().all()
    return [
        {
            "id": p.id,
            "visit_number": p.visit_number,
            "age": p.age,
            "preferred_language": p.preferred_language,
            "arrival_time": p.arrival_time,
        }
        for p in patients
    ]
