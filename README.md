# AI Nurse - Conversational Patient Triage & Severity Assessment System

[![FastAPI](https://img.shields.io/badge/FastAPI-1.0.0-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18.3-61DAFB.svg)](https://reactjs.org)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB.svg)](https://www.python.org)
[![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED.svg)](https://www.docker.com)

A clinical decision-support prototype for conversational patient triage and severity assessment in emergency care settings.

---

## Central Engineering Principle (Spec §45)

$$\text{LLM} = \text{Understand} + \text{Extract} + \text{Converse} \quad \neq \quad \text{Decide Clinical Urgency}$$

The LLM (swappable: Google Gemini 2.5 Flash / OpenAI GPT-4o / Groq / Ollama) extracts structured clinical facts from multilingual conversation. A **deterministic rules engine** evaluates these facts against versioned clinical discriminators to determine triage urgency (RED, ORANGE, YELLOW, GREEN, BLUE).

---

## Key Features

1. **Multilingual Voice & Text**: Full support for English, Urdu (اردو), and Arabic (عربي) with automatic speech-to-text (Whisper), language detection, voice playback (speech synthesis), and English normalisation of every statement - the original is never discarded.
2. **Hallucination Guard**: Every extracted clinical fact must (a) cite a real message ID, (b) exceed a confidence threshold, and (c) have its cited text actually support the fact - a fabricated fact citing an unrelated real message is rejected, not just one citing a nonexistent message.
3. **Deterministic Triage Engine**: Pure rules-based calculation (YAML rules v1.0.0, externally configurable target times). Same facts + same rules version = same severity - every result records a SHA-256 hash of the exact rules content used, so past decisions are provably reproducible.
4. **Swappable LLM & AI Providers**: Supports Google Gemini 2.5 Flash, OpenAI GPT-4o, Groq, Ollama, and built-in Mock NLU via `LLM_PROVIDER` environment configuration.
5. **Human-in-the-Loop**: Clinician review interface with **Confirm**, **Override** (with required reason), **Reassess**, and **Escalate** - all authenticated, role-restricted actions.
6. **Emergency Department Command Center**: Real-time queue view sorted by severity rank and clinical target time, with live deterioration highlighting as new observations change a patient's severity.
7. **Immutable Audit Trail**: Full provenance answering what the patient said, what rules triggered, what the AI recommended, and what the clinician decided.
8. **Two-Part Automated Evaluation Suite**: 50 synthetic clinical cases evaluated both against the rules engine directly (isolates engine correctness) and through the full conversation → extraction → guard → engine pipeline - see `docs/evaluation_report.md`.

---

## Default Seeded Credentials (for Evaluators & Markers)

On startup, the system automatically seeds default staff credentials so evaluators can immediately log in:

| Role | Username | Password | Access Level |
|---|---|---|---|
| **Administrator** | `admin` | `Admin123!` | Full admin access + staff registration |
| **Triage Nurse** | `nurse` | `Nurse123!` | Command Center & Clinician Review |

---

## Quick Start Guide

### Prerequisites
- Python 3.11+
- Node.js 20+ (for frontend dev)
- Docker & Docker Compose (optional for containerized setup)
- Gemini / OpenAI API Key (optional - mock providers fall back automatically if absent)

---

### Running the System Locally

#### 1. Setup Backend
```bash
cd backend
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
# source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
Backend API will be running at `http://localhost:8000`. Interactive docs at `http://localhost:8000/api/docs`.

#### 2. Setup Frontend
```bash
cd frontend
npm install
npm run dev
```
Frontend web application will be running at `http://localhost:5173`.

---

### Running with Docker Compose

To launch the complete stack with a single command:
```bash
docker compose up --build
```
- Patient Kiosk / App: `http://localhost:5173`
- Backend API Docs: `http://localhost:8000/api/docs`

---

### Running the Automated Evaluation Suite

To run all 50 synthetic test cases and generate the quantitative safety metrics report (both the rules-engine-only pass and the full end-to-end conversation pipeline pass - see `docs/evaluation_report.md` for what each measures):
```bash
cd backend
python -m tests.evaluation.run_evaluation
```
To run the end-to-end pass against the real GPT-4o service instead of the deterministic offline mock (requires an API key):
```bash
EVAL_USE_REAL_LLM=1 OPENAI_API_KEY=sk-... python -m tests.evaluation.run_evaluation
```

To run unit tests:
```bash
cd backend
pytest
```

---

## Project Structure

```
ai-nurse/
├── backend/
│   ├── app/
│   │   ├── api/               # REST API endpoints (triage, patients, conversations, staff, audit)
│   │   ├── core/              # Config, security, JWT auth
│   │   ├── models/            # SQLAlchemy database & Pydantic domain models
│   │   ├── rules/             # Versioned synthetic triage rules (YAML)
│   │   └── services/          # Abstracted services (STT, LLM, Extraction, Triage, RAG, Audit)
│   ├── data/
│   │   └── synthetic_cases/   # 50 synthetic evaluation cases
│   ├── tests/                 # Unit tests & evaluation runner
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/               # API client
│   │   ├── components/        # VoiceRecorder, TriageResult, etc.
│   │   ├── pages/             # PatientScreen, NurseScreen, CommandCenter, LoginScreen
│   │   └── types/             # TypeScript interfaces
│   ├── Dockerfile
│   └── vite.config.ts
├── docs/                      # Architecture, threat analysis, evaluation report, API docs
├── docker-compose.yml
└── README.md
```

---

## Governance & Safety Notice
*This repository is a synthetic research/assignment prototype. It is tested exclusively on de-identified synthetic data. No production clinical deployment should occur without formal clinical validation and institutional governance.*
