# System Documentation: Auditoria nstech

## 1. System Overview

The `auditoria` project is a full-stack platform designed for the operational auditing of calls and documentary workflows. It acts as an operational governance platform rather than just an isolated AI prototype. The system orchestrates audio triage, multi-provider transcription fallback, AI-driven criteria evaluation, and operational workflows (approval, supervision, dispute, and export).

## 2. System Architecture

The project follows a standard decoupled Client-Server architecture with a unified database and multiple external integrations.

### 2.1. Frontend (React + Vite)
- **Framework:** React 19 with TypeScript, bundled by Vite.
- **Styling:** Tailwind CSS (v4).
- **Structure:** Domain-driven organization inside `src/features/`.
  - `audit`: Core audit flows (configuration, upload, results, editing).
  - `classifier`: Pre-audit audio triage.
  - `dashboard`: Metrics and historical data.
  - `supervisor`: Approval queue, exports.
  - `review`: Technical dispute reviews.
  - `saved-files`: Artifact management.
  - `settings` & `admin`: Configuration and criteria management.

### 2.2. Backend (FastAPI + Python)
- **Framework:** FastAPI (Python 3.11).
- **Architecture Pattern:** Layered architecture (Routers, Core, Services, Repositories).
  - `main.py`: Application bootstrap, CORS, security headers, rate limiting.
  - `routers/`: API route definitions.
  - `core/`: Core business logic (transcription pipeline, AI evaluation, auditing flows).
  - `repositories/`: Data access layer.
  - `db/`: Database migrations and runtime schemas.
- **Audio Processing:** Dedicated module (`audio/`) for diarization, heuristics, and normalization.

### 2.3. Persistence (PostgreSQL)
- **Database:** PostgreSQL 15.
- **Key Tables:** 
  - `audits`, `ligacoes_auditadas`, `resultados_classificacao`, `fila_revisao_classificacao`.
  - `audit_sectors`, `audit_alerts`, `audit_criteria`.
  - `colaboradores`, `gestor_feedbacks`, `arquivos_salvos`.

### 2.4. External Services (AI Integration)
- **Transcription:** Azure Speech, Azure Whisper, GPT-4o Diarize, AssemblyAI.
- **Evaluation:** Azure OpenAI for LLM-based criteria checking.

## 3. Core Components & System Flow

The main operational flow is as follows:

1. **Audio Triage (Optional):**
   - The `classifier` module evaluates audio batches to determine the sector, alert, operator, confidence, and need for manual review.
2. **Upload & Normalization:**
   - Initiated via `POST /api/audit`. Accepts audio or PDF files along with metadata (alert, operator, sector).
3. **Transcription Pipeline (`backend/core/transcription.py`):**
   - Implements a resilient fallback strategy.
   - Attempts Azure Fast Transcription -> GPT-4o Diarize -> AssemblyAI -> Azure Whisper.
   - Validates outputs via heuristics (speaker normalization, diarization quality). Reuses cached results if available.
4. **AI Evaluation (`backend/core/evaluation.py`):**
   - Constructs a prompt based on the specific alert and sector criteria.
   - Queries Azure OpenAI.
   - Requires JSON output and includes logic to repair malformed JSON.
   - Backend applies deterministic rules on top of AI results (e.g., zeroing scores for non-negotiable items, applying safety nets).
5. **Workflow & Persistence:**
   - Saves the audit, transcription, input hashes, and metadata to PostgreSQL.
   - The audit enters the operational queue: Pending Approval -> Waiting for Pairing -> Disputed -> Technical Review -> Approved/Adjusted.

## 4. Data Lifecycle

1. **Ingestion:** Audio/PDF files are uploaded. Audio files undergo diarization and transcription.
2. **Processing:** Extracted text is evaluated by LLMs.
3. **Storage:** Results are stored in the PostgreSQL `audits` table. Audio files are persisted in local volumes (`/app/Ligações`).
4. **Action:** Supervisors review audits. If contested, they enter a review flow.
5. **Archiving/Export:** Data can be exported to Excel, PDF, or DOCX for managerial review.

## 5. Deployment & Execution

- **Environment:** Managed via Docker Compose (`docker-compose.yml`).
- **Containers:** 
  - `app` (FastAPI backend + Vite static build).
  - `db` (PostgreSQL).
- **Local Dev:** Handled via PowerShell scripts (`scripts/start-local.ps1`) and NPM scripts (`npm run up`).