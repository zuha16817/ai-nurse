# AI Nurse API Documentation

The backend service is built using FastAPI and automatically generates OpenAPI 3.0 documentation.

- **Interactive Swagger UI**: `http://localhost:8000/api/docs`
- **ReDoc UI**: `http://localhost:8000/api/redoc`
- **OpenAPI JSON**: `http://localhost:8000/api/openapi.json`

---

## Core Endpoints Overview

### Authentication (`/api/auth`)
- `POST /api/auth/token`: Login for staff (OAuth2 password flow). Returns JWT token.
- `POST /api/auth/register`: Register new staff user.

### Patients (`/api/patients`)
- `POST /api/patients/`: Register patient & auto-create triage session.
- `GET /api/patients/`: List all patients.
- `GET /api/patients/{patient_id}`: Get patient details.

### Conversations (`/api/conversations`) - public, patient-initiated
- `POST /api/conversations/message/text`: Submit typed message.
- `POST /api/conversations/message/audio`: Submit voice audio file (`.webm`/`.wav`/`.mp3`/`.m4a`/`.ogg`, ≤15MB).
- `POST /api/conversations/vitals`: Submit objective vital signs (requires staff auth - nurse-entered).
- `POST /api/conversations/{session_id}/inactivity-alert`: Patient stopped responding - flags the session for clinician attention without inventing a low-acuity result (spec §39).
- `GET /api/conversations/{session_id}/transcript`: Fetch transcript (staff auth required).

### Triage (`/api/triage`)
- `POST /api/triage/{session_id}/compute`: Execute deterministic rules engine. **Public/system-triggered** - this runs as part of the patient's own conversation completing, not a clinician action.
- `POST /api/triage/{triage_result_id}/confirm`: Clinician accepts AI recommendation. **Requires nurse/admin auth.**
- `POST /api/triage/{triage_result_id}/override`: Clinician overrides severity with reason. **Requires nurse/admin auth.**
- `POST /api/triage/{session_id}/reassess`: Initiate re-triage session, keeping full history. **Requires nurse/admin auth.**
- `GET /api/triage/{session_id}/history`: Fetch triage history.

### Staff & Command Center (`/api/staff`) - all require nurse/admin auth
- `GET /api/staff/queue`: ED queue sorted by severity + target wait time.
- `GET /api/staff/patient/{session_id}/full`: Full clinical record view (transcript, facts, vitals, triage, audit trail).
- `POST /api/staff/patient/{session_id}/escalate`: Immediately flag a patient for the clinical team (spec §23 "Escalate" action).

### Audit (`/api/audit`) - requires nurse/admin auth
- `GET /api/audit/{session_id}`: Full provenance log for auditability.

### Auth boundary rationale
Endpoints that are part of the patient's own interview (`message/*`, `vitals` submission by the treating nurse, `compute`) are reachable without a clinician login because they're triggered by the ongoing encounter itself. Endpoints that record or change a *clinical decision* about that encounter (`confirm`, `override`, `reassess`, `escalate`, and anything under `/staff` or `/audit` that exposes the full record) require an authenticated nurse or admin - this was previously inconsistent (some of these had no auth dependency at all) and has been corrected.
