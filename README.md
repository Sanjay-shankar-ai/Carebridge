<<<<<<< HEAD
# CareBridge — Autonomous AI Care Coordinator

> **Future Health Digital Innovation Challenge**  
> *Team: Ai_Mavericks* | *Problem Statement: Closing the Screening-to-Care Loop*

CareBridge is an autonomous, agentic AI healthcare coordination platform that bridges the gap between actionable screening results (e.g., abnormal mammograms, lab alerts) and documented, verified clinical care completion.

Unlike traditional rule-based chatbots or rigid decision trees, CareBridge acts as an **intelligent AI care coordinator**:
- Understands natural language, implicit barriers, and questions across English, Tamil, and Tanglish.
- Maintains deep patient and case memory across care handoffs.
- Reasons dynamically about situations, chooses tools, and runs proactive recovery workflows.
- Strictly separates administrative autonomy from clinical safety boundaries with a 3-tier governance model.

---

## Monorepo Structure

```text
carebridge/
├── frontend/                     # Next.js 14 App Router, TypeScript, Tailwind CSS
│   ├── app/
│   │   ├── dashboard/            # Care coordinator command center & SLA radar
│   │   ├── patients/             # Patient registry & communication profiles
│   │   ├── cases/                # End-to-end case memory & ownership tracker
│   │   ├── appointments/         # Scheduling, booking, and attendance monitor
│   │   ├── referrals/            # FHIR ServiceRequest handoffs & status
│   │   ├── recovery/             # Proactive drop-off & no-show recovery radar
│   │   ├── analytics/            # Outcome metrics, closure rates, language parity
│   │   ├── settings/             # SLA thresholds & governance rules
│   │   ├── layout.tsx            # Navigation shell (Sidebar & Header)
│   │   └── page.tsx              # Portal root redirect
│   ├── components/               # Modular UI components
│   ├── hooks/                    # React hooks for state and queries
│   ├── services/                 # API client services
│   ├── types/                    # TypeScript interfaces & domain types
│   ├── lib/                      # Utility functions
│   └── package.json
│
├── backend/                      # Python FastAPI + LangGraph Agent Core
│   ├── app/
│   │   ├── api/v1/               # Modular REST endpoints (health, cases, etc.)
│   │   ├── core/                 # App configuration & settings
│   │   ├── agents/               # LangGraph cognitive nodes & workflows
│   │   ├── tools/                # 16 autonomous care coordination tools
│   │   ├── memory/               # Case memory & context retrievers
│   │   ├── workflows/            # Clinical pathway definitions
│   │   ├── database/             # SQLAlchemy connection & session management
│   │   ├── models/               # Database ORM models (FHIR aligned)
│   │   ├── schemas/              # Pydantic v2 schemas & validation
│   │   ├── services/             # Domain services & translation engines
│   │   ├── integrations/         # External integrations (FHIR, SMS, WhatsApp)
│   │   ├── scheduler/            # APScheduler background SLA monitors
│   │   ├── security/             # Autonomy gatekeepers & RBAC
│   │   ├── utils/                # Helper utilities
│   │   └── main.py               # FastAPI application entrypoint
│   ├── tests/                    # Backend unit & integration test suite
│   └── requirements.txt
│
├── infrastructure/               # DevOps & deployment configurations
│   ├── docker/                   # Docker Compose & container definitions
│   └── migrations/               # Alembic database migration scripts
│
├── docs/                         # Architecture documentation & specifications
├── tests/                        # Monorepo integration & simulation tests
├── .env.example                  # Environment variable template
├── .gitignore                    # Git ignore definitions
├── package.json                  # Monorepo npm command orchestrator
└── README.md
```

---

## 3-Tier Autonomy & Safety Governance

1. **Level 1 — Fully Autonomous (No Routine Approval):**  
   Language understanding, translation (Tamil/English), answering administrative questions, drafting case summaries, monitoring progress, and sending routine follow-ups.
2. **Level 2 — Autonomous with Constraints (Policy/Permission-Based):**  
   Rescheduling appointments within SLA windows, generating routine referrals, reassigning administrative tasks, and executing recovery playbooks for no-shows.
3. **Level 3 — Human Authorization (Clinical Oversight Interrupt):**  
   Clinical decisions, prescription advice, diagnostic assertions, clinical urgency alterations, and final verified case closure.

---

## Quickstart Guide

### 1. Prerequisites
- **Python**: 3.12+
- **Node.js**: 20+ (with npm)
- **PostgreSQL**: Local instance or Supabase project

### 2. Configure Environment
Copy `.env.example` to `.env` in the root:
```bash
cp .env.example .env
```
Fill in your `DATABASE_URL` and `OPENAI_API_KEY`.

### 3. Running the Backend (FastAPI)
```bash
# Navigate to backend and install dependencies
cd backend
pip install -r requirements.txt

# Start FastAPI development server
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- Interactive API Docs (Swagger): [http://localhost:8000/docs](http://localhost:8000/docs)
- Health Check: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

### 4. Running the Frontend (Next.js)
```bash
# In a separate terminal, navigate to frontend
cd frontend
npm install

# Start Next.js development server
npm run dev
```
- Open [http://localhost:3000](http://localhost:3000) in your browser.

### 5. Running with Docker Compose
To run PostgreSQL, Backend, and Frontend simultaneously:
```bash
docker compose -f infrastructure/docker/docker-compose.yml up --build
```
=======
# Carebridge
>>>>>>> 229ead3ac44ad7ddc2ce0bc68ed9ccbdad8680a2
