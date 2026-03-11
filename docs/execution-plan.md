# Smart Patient Card System — Execution Plan

> Prepared: 11 March 2026 | Hackathon: 20–22 March 2026 | Team: 5 people

---

## Context

- **Event**: Botswana National Open Data Hackathon
- **Track**: Health — Patient Flow & Queue Optimisation + Supply Chain & Stock Management
- **Goal**: Working MVP demonstrating the full patient loop from arrival to pharmacy
- **Team size**: 5 (lead + 4 teammates)

---

## Tech Stack

| Layer | Tech | Rationale |
|---|---|---|
| Backend API | FastAPI (Python) | Fast to build, async, auto OpenAPI docs |
| Database | PostgreSQL 16 | Relational, handles transactions well |
| Cache / Queue state | Redis 7 | Fast queue ops, USSD session storage |
| Frontend (web) | Next.js (React) | SSR + PWA support in one framework |
| Patient channel | PWA (from Next.js) | No app install needed, works on any phone |
| USSD | Africa's Talking | Has Botswana coverage, good free tier |
| Auth | JWT + RBAC | Stateless, easy to implement role checks |
| Hosting | Railway or Fly.io | One-command deploy, free tier for MVP |
| Containers | Docker + docker-compose | Consistent dev/prod environments |
| Migrations | Alembic | FastAPI-native DB migration tool |
| SMS | Africa's Talking SMS | Same account as USSD |

---

## Component Breakdown

### 1. Backend API (Lead — core ownership)

#### 1a. Auth Service
- JWT token issuance and validation
- Roles: `patient`, `receptionist`, `nurse`, `doctor`, `pharmacist`, `admin`
- Refresh token rotation
- Password hashing (bcrypt)
- `services/auth/`

#### 1b. Patient & Card Service
- Patient registration (name, DOB, national ID, phone, consent)
- Card token generation → UUID + checksum stored on card/QR
- `GET /patients/card/{token}` — card lookup
- Card deactivation + reissue flow
- `services/patient/`

#### 1c. Arrival & Visit Service
- `POST /visits/arrive` — card tap creates a visit episode
- Visit state machine: `arrived → triaged → in_consultation → discharged`
- Walk-in support (manual registration without card)
- Queue placement on arrival
- `services/visit/`

#### 1d. Symptom Intake Service
- Questionnaire engine with ordered questions and branching logic
- `POST /symptoms/submit` — receives answers from app or USSD
- Auto-generates triage-ready summary from raw answers
- `services/symptom/`

#### 1e. Queue Engine
- Priority queue per facility and service class (emergency, general, MCH)
- Wait-time estimator: `position × avg_consult_time / available_doctors`
- `GET /queue/{facility_id}` — live queue state
- Redis-backed for speed
- `services/queue/`

#### 1f. Clinical Worklist Service
- Nurse view: prioritised patient list with symptom summaries and urgency tags
- Doctor view: next patient, full visit detail, prescribe action
- `POST /prescriptions` — clinician submits prescription
- `services/clinical/`

#### 1g. Pharmacy & Inventory Service
- `GET /pharmacy/demand` — predicted demand from confirmed visit symptoms
- `POST /stock/dispense` — deducts stock after prescription confirmed
- Low-stock alert triggers using reorder threshold rules
- Medicine catalog, batch tracking, expiry dates
- `services/pharmacy/`

#### 1h. Notification Service
- SMS/USSD callback: wait-time updates to patient
- Pharmacy alert: low stock warning to pharmacist
- Africa's Talking SMS API
- `services/notifications/`

#### 1i. Analytics Endpoints
- `GET /analytics/throughput` — patients per hour per facility
- `GET /analytics/wait-times` — average wait, P90
- `GET /analytics/stockouts` — stockout incidents
- `services/analytics/`

---

### 2. Database Layer

#### PostgreSQL Schema

```sql
patients          — id, national_id, name, dob, phone, consent_at
cards             — id, patient_id, card_token, status, issued_at, deactivated_at
visits            — id, patient_id, facility_id, arrived_at, state, queue_position
symptoms          — id, visit_id, question_id, answer, submitted_at
triage_entries    — id, visit_id, urgency_level, nurse_id, notes, tagged_at
prescriptions     — id, visit_id, doctor_id, medicines[], approved_at
medicine_catalog  — id, name, unit, reorder_threshold, lead_time_days
stock_ledger      — id, facility_id, medicine_id, batch, qty, expiry
stock_events      — id, medicine_id, event_type, qty_delta, timestamp
facilities        — id, name, type, district, location
users             — id, role, facility_id, name, credentials
audit_log         — id, user_id, action, entity, entity_id, timestamp
```

#### Redis Keys

```
queue:{facility_id}       — sorted set, score = priority
session:{token}           — USSD session state
visit_state:{visit_id}    — fast visit state reads
```

---

### 3. USSD Integration (Lead)

Africa's Talking USSD gateway. Session state stored in Redis.

**Flow:**
```
*123# → Welcome
  [1] Register  [2] Check in  [3] My wait time

→ [2] Check in
  "Enter your card number:"
  → Arrival logged
  → "You are #4 in queue. Estimated wait: 22 mins"
  → "Describe symptoms: [1] Fever  [2] Cough  [3] Pain  [4] Other"
  → "Thank you. A nurse will call you shortly."
```

**Files:**
- `services/ussd/session.py` — Redis session state machine
- `services/ussd/flows/` — one file per flow (checkin, symptoms, waittime)
- `routes/ussd.py` — Africa's Talking webhook endpoint

---

### 4. Smart Card / NFC

**Hackathon approach (pragmatic):**
- **QR code on card** → patient scans → opens PWA → triggers arrival (most reliable, no hardware dependency)
- Card token encoded as URL: `https://yourapp.com/checkin?token=<uuid>`
- NFC via Android phone (reader mode) described as Phase 1 hardware upgrade

---

### 5. Frontend — Web Dashboard (Teammate 1)

| View | Users | Key functionality |
|---|---|---|
| `/reception` | Receptionist | Scan QR, register walk-in, live queue |
| `/nurse` | Nurse | Patient list with urgency tags, symptom summaries |
| `/doctor` | Doctor | Worklist, full visit detail, prescription form |
| `/pharmacy` | Pharmacist | Demand predictions, dispense form, stock levels |
| `/admin` | Admin | Facility dashboard, KPIs, analytics charts |
| `/checkin` | Patient (kiosk/phone) | Symptom questionnaire, wait-time display |

**Shared components:**
- `QueueBoard` — live queue with estimated wait times
- `PatientCard` — summary card with urgency badge
- `SymptomSummary` — formatted symptom display
- `StockAlert` — low stock warning banner

---

### 6. Patient Mobile Channel (Teammate 2)

**PWA from Next.js** — no app store install required, works on any phone with a browser.

- Patient scans QR on their card → opens PWA
- Completes symptom questionnaire
- Sees queue position and estimated wait time
- Receives SMS update when called

---

### 7. Security (Lead — baked in from day 1)

- All endpoints require JWT except `/auth/login`, `/ussd/webhook`, `/visits/arrive`
- `/visits/arrive` authenticated via card token (not user session)
- RBAC middleware as decorator on every route
- HTTPS enforced via Railway/Fly.io
- Passwords: bcrypt, never logged
- Card tokens: UUID v4, no PII in token
- Audit log: every record access, every prescription, every stock event
- Rate limiting: 100 req/min per IP on public endpoints
- Input validation: Pydantic models on all request bodies

---

### 8. DevOps / Infrastructure (Teammate 4)

```
docker-compose.yml
├── api          (FastAPI on port 8000)
├── db           (PostgreSQL 16)
├── redis        (Redis 7)
└── nginx        (reverse proxy + SSL termination)
```

- **CI**: GitHub Actions — lint + test on every push to main
- **Deploy**: Railway or Fly.io
- **Migrations**: Alembic
- **Env vars**: `.env.example` with all required keys documented

---

### 9. External Integrations (Teammate 4 + Lead)

| Integration | Purpose | Method |
|---|---|---|
| healthfacilities.gov.bw | Seed facility data | Scrape + import as seed SQL |
| Africa's Talking USSD | USSD sessions | Webhook POST to `/ussd/webhook` |
| Africa's Talking SMS | Patient wait-time notifications | REST API call from notification service |
| EHR stub | Patient record sync (demo) | Mock service with structured response |

---

## Team Assignments

| Domain | Owner | Support |
|---|---|---|
| Backend API (all services) | **Lead** | — |
| Database schema + migrations | **Lead** | TM4 |
| USSD integration | **Lead** | TM2 |
| Security + auth | **Lead** | — |
| Smart card / QR | **Lead** | TM2 |
| Frontend (Next.js dashboards) | **TM1** | Lead (API contracts) |
| PWA patient channel | **TM2** | TM1 |
| Pharmacy dashboard UI | **TM3** | TM1 |
| Docker + CI/CD + DevOps | **TM4** | Lead |
| Facility data + integrations | **TM4** | Lead |

---

## Hackathon Build Order (3 Days)

### Day 1 — Core Patient Loop
- [ ] Repo setup, docker-compose, PostgreSQL schema, Alembic
- [ ] Auth service (JWT, RBAC roles)
- [ ] Patient registration + card token generation
- [ ] Arrival endpoint (card/QR tap → visit created → queue entry)
- [ ] USSD symptom intake flow (Africa's Talking)
- [ ] Reception UI + live queue board (TM1)
- [ ] PWA patient questionnaire (TM2)

### Day 2 — Clinical + Pharmacy
- [ ] Nurse dashboard with symptom summaries and triage tags
- [ ] Doctor worklist + prescription endpoint
- [ ] Pharmacy demand signal from confirmed symptoms
- [ ] Stock ledger — dispense endpoint + low-stock alerts
- [ ] Pharmacy dashboard (TM3)
- [ ] Wait-time estimation algorithm
- [ ] SMS notification to patient on queue update

### Day 3 — Polish + Demo
- [ ] Admin dashboard + KPI charts (throughput, wait times, stockouts)
- [ ] Analytics endpoints
- [ ] Seed data: Botswana health facilities
- [ ] End-to-end demo scenario: arrival → symptoms → triage → doctor → pharmacy → discharge
- [ ] Presentation slide deck (4 min pitch)

---

## Pre-Hackathon Checklist (Now → 19 March)

- [ ] Africa's Talking account + USSD shortcode provisioned
- [ ] Railway or Fly.io project created
- [ ] GitHub repo created, team members invited
- [ ] Docker setup tested locally
- [ ] Base FastAPI project scaffolded
- [ ] PostgreSQL schema reviewed and finalised
- [ ] OpenAPI contract documented so TM1 can build frontend against it
- [ ] Figma mockups for nurse / doctor / pharmacy views

---

## Pilot KPIs (from architecture doc)

| KPI | Target |
|---|---|
| Time from arrival to nurse review | < 5 mins with system |
| % visits with complete digital symptom intake | > 80% |
| % visits where correct record found without paper lookup | > 90% |
| Medicine stockout rate for tracked medicines | Reduce by 30% |
| Wait-time estimation error | < ± 10 mins |
| Staff adoption rate | > 70% by end of pilot |

---

## Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| Lost/damaged cards | Patient can't check in | QR backup + manual walk-in flow |
| Poor connectivity | USSD/sync failure | Local cache + retry queue + manual override |
| Low staff adoption | Workarounds undermine pilot | Short screens, super-user training, weekly usage check |
| Data privacy breach | Legal and trust exposure | Minimal card data, encryption, audit log, role separation |
| Wrong medicine from symptom signal | Safety concern | Symptom = preparation signal only; dispensing needs prescription |

---

*Document version: v1.0 | Last updated: 11 March 2026*
