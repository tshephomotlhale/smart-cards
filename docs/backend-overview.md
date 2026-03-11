# Backend Overview — Smart Patient Card System

> **Hackathon**: Botswana National Open Data Hackathon, March 20–22 2026 (Health Track)
> **Stack**: FastAPI · PostgreSQL 16 · Redis 7 · Docker

---

## What's Running

| Service | URL | Description |
|---|---|---|
| API | http://localhost:8000 | FastAPI backend |
| Swagger UI | http://localhost:8000/docs | Interactive API docs |
| PostgreSQL | localhost:5432 | Primary database |
| Redis | localhost:6379 | Queue + USSD sessions |

Start everything: `bash start.sh`

---

## Project Structure

```
backend/
├── app/
│   ├── core/
│   │   ├── config.py          # Settings from .env (pydantic-settings)
│   │   └── security.py        # JWT creation, bcrypt hashing
│   ├── db/
│   │   ├── session.py         # Async SQLAlchemy engine + session factory
│   │   ├── redis.py           # Redis connection helper
│   │   └── seed.py            # Idempotent seed script
│   ├── middleware/
│   │   └── auth.py            # JWT decode + RBAC dependency functions
│   ├── models/
│   │   ├── base.py            # Base + TimestampMixin (created_at, updated_at)
│   │   ├── facility.py        # Facility
│   │   ├── user.py            # User, UserRole enum
│   │   ├── patient.py         # Patient, PatientCard, CardStatus enum
│   │   ├── visit.py           # Visit, SymptomEntry, TriageEntry, VisitState enum
│   │   ├── pharmacy.py        # Medicine, StockLedger, StockEvent, Prescription, PrescriptionItem
│   │   └── audit.py           # AuditLog
│   ├── routes/
│   │   ├── auth.py            # POST /auth/login, /auth/register
│   │   ├── patients.py        # Patient + card management
│   │   ├── visits.py          # Visit lifecycle endpoints
│   │   ├── queue.py           # Queue snapshot + position
│   │   ├── pharmacy.py        # Prescriptions + dispensing
│   │   ├── ussd.py            # Africa's Talking USSD webhook
│   │   ├── analytics.py       # Dashboard KPI endpoints
│   │   └── events.py          # SSE real-time stream
│   ├── schemas/               # Pydantic request/response models
│   ├── services/
│   │   ├── auth/service.py    # Login + staff registration logic
│   │   ├── patient/service.py # Patient lookup by card token
│   │   ├── visit/service.py   # Arrive, symptoms, triage
│   │   ├── queue/service.py   # Redis sorted-set queue
│   │   ├── pharmacy/service.py # Prescriptions + stock dispensing
│   │   ├── analytics/service.py # All KPI queries
│   │   ├── ussd/handler.py    # USSD state machine
│   │   └── notifications/
│   │       ├── events.py      # SSE broadcaster
│   │       └── sms.py         # Africa's Talking SMS
│   └── main.py                # FastAPI app, middleware, router registration
├── .env                       # Real credentials (gitignored)
├── .env.example               # Safe template for teammates
└── requirements.txt
```

---

## Authentication & Authorization

**Login**: `POST /auth/login` with `{ email, password }` → returns JWT token.

**Use the token**: Add `Authorization: Bearer <token>` header to all protected requests.

**Roles** (6 levels):

| Role | Access |
|---|---|
| `patient` | Self-service only |
| `receptionist` | Check in patients, view queue |
| `nurse` | Triage, view symptoms |
| `doctor` | Consultations, write prescriptions |
| `pharmacist` | Dispense prescriptions, view stock |
| `admin` | Full access + register staff |

**Default admin**: `admin@smartcards.bw` / `Admin1234!`

---

## Patient Flow (full pipeline)

```
TAP CARD → ARRIVE → SUBMIT SYMPTOMS → TRIAGE → CONSULTATION → PRESCRIPTION → DISPENSE → DISCHARGE
```

Each step:

### 1. Check-in
- **Card tap**: `POST /visits/arrive` with `{ card_token, facility_id, service_class }`
- **Walk-in**: `POST /visits/walkin` with `{ patient_id, facility_id }`
- Patient is added to the Redis priority queue. Queue position + estimated wait returned.

### 2. Symptom Intake
- `POST /visits/symptoms` with answers dict + channel (`app`, `ussd`, `kiosk`)
- Visit state → `SYMPTOMS_SUBMITTED`
- Nurse dashboard receives SSE notification.

### 3. Triage
- `POST /visits/triage` — nurse assigns urgency level
- Urgency levels: `emergency`, `urgent`, `semi_urgent`, `non_urgent`
- Patient re-ranked in queue based on urgency. Doctor dashboard notified via SSE.

### 4. Prescription
- `POST /pharmacy/prescriptions` — doctor creates prescription with items
- Visit state → `PRESCRIBED`. Pharmacy dashboard notified via SSE.

### 5. Dispense
- `POST /pharmacy/dispense` — pharmacist dispenses
- Stock ledger decremented per item. Low-stock SSE alerts triggered if below threshold.
- Patient receives SMS: "Your prescription is ready."

---

## Queue System

Built on **Redis sorted sets** — one queue per (facility, service_class).

- Score = urgency number (lower = higher priority): `emergency=1`, `urgent=10`, `semi_urgent=100`, `non_urgent=1000`
- On triage, patient is removed and re-inserted with urgency score
- `GET /queue/{facility_id}` — full queue snapshot for the display board
- `GET /queue/{facility_id}/position/{visit_id}` — individual position + wait estimate

---

## Real-Time Notifications (SSE)

`GET /events/{facility_id}/{role}` — Server-Sent Events stream. Dashboards connect once and receive live updates.

**Valid roles**: `reception`, `nurse`, `doctor`, `pharmacy`, `queue`

**Events published**:

| Trigger | Channel | Event |
|---|---|---|
| Patient arrives | reception, nurse, queue | `new_arrival` |
| Symptoms submitted | nurse | `symptoms_submitted` |
| Patient triaged | doctor, queue | `patient_triaged` |
| Prescription created | pharmacy | `prescription_pending` |
| Stock drops below threshold | pharmacy | `low_stock` |

Heartbeat every 15s to keep connection alive.

---

## SMS Notifications

Powered by **Africa's Talking** (Botswana number: `+267` prefix auto-applied).

| Trigger | Message |
|---|---|
| Check-in | "You are #3 in queue. Estimated wait: 12 minutes." |
| Called for triage | "You've been called. Please proceed to the nurse station." |
| Prescription ready | "Your prescription is ready for collection at the pharmacy." |

Falls back to log-only mode if Africa's Talking credentials are not configured.

---

## USSD (`*123#`)

Africa's Talking webhook at `POST /ussd`. State machine handles:

1. **Main menu** — Check in / Submit symptoms / Check queue position
2. **Check-in** — Enter card number → confirmed in queue
3. **Symptoms** — Answer yes/no health questions (fever, cough, pain, etc.)
4. **Queue status** — Returns current position + wait time

Sessions stored in Redis with 10-minute TTL.

---

## Analytics Endpoints

All require `receptionist` role or above. All accept optional `?target_date=YYYY-MM-DD` (defaults to today).

| Endpoint | What it returns |
|---|---|
| `GET /analytics/dashboard/{facility_id}` | All KPIs in one call — used by admin summary cards |
| `GET /analytics/throughput/{facility_id}` | Total arrivals, currently active, discharged |
| `GET /analytics/funnel/{facility_id}` | Patient count + % at each visit stage |
| `GET /analytics/wait-times/{facility_id}` | Avg / max / min arrival→triage time (minutes) |
| `GET /analytics/adoption/{facility_id}` | % of visits using digital symptom intake, by channel |
| `GET /analytics/stock/{facility_id}` | Per-medicine ok / low / stockout with health rate % |

**Dashboard KPIs block** (headline cards for the frontend):
```json
{
  "kpis": {
    "total_arrivals_today": 47,
    "currently_in_clinic": 12,
    "avg_wait_to_triage_mins": 8.3,
    "digital_intake_rate_pct": 74.5,
    "stock_health_pct": 87.5,
    "medicines_needing_reorder": 3
  }
}
```

---

## Seed Data

Run: `docker compose exec api python -m app.db.seed`
(Safe to re-run — skips anything already present.)

**Facilities seeded** (8 total):

| Name | Type | District |
|---|---|---|
| Princess Marina Hospital | Hospital | South East (Gaborone) |
| Scottish Livingstone Hospital | Hospital | South East (Molepolole) |
| Nyangabgwe Referral Hospital | Hospital | North East (Francistown) |
| Maun General Hospital | Hospital | North West (Maun) |
| Athlone Clinic | Clinic | South East (Gaborone) |
| Bontleng Clinic | Clinic | South East (Gaborone) |
| Broadhurst Clinic | Clinic | South East (Gaborone) |
| Naledi Clinic | Clinic | South East (Gaborone) |

**Medicines seeded** (8 total): Paracetamol, Amoxicillin, Metformin, Atenolol, ORS, Artemether/Lumefantrine, Cotrimoxazole, Ibuprofen

**Stock ledger**: 64 records (8 × 8). Quantities deliberately varied — some low/stockout — so analytics show realistic demo data.

---

## Key Environment Variables (`.env`)

```
DATABASE_URL=postgresql+asyncpg://smartcards:...@db:5432/smartcards
REDIS_URL=redis://redis:6379/0
SECRET_KEY=...                  # Auto-generated by start.sh
AT_USERNAME=...                 # Africa's Talking username
AT_API_KEY=...                  # Africa's Talking API key
AT_SENDER_ID=SmartCard          # SMS sender name
ALLOWED_ORIGINS=http://localhost:3000
```

---

## What's Left

- **Frontend** — Next.js dashboards (reception, nurse, doctor, pharmacy, admin, patient PWA)
- **GitHub + CI/CD** — Repo + GitHub Actions pipeline
- **USSD shortcode** — Provision with Africa's Talking (external step)
- **Alembic migrations** — Currently using `create_all`; migrations needed for production
