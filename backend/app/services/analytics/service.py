"""
Analytics service — computes all KPIs from the planning doc.

Key metrics:
  - Throughput: total arrivals, discharged, currently active
  - Visit funnel: breakdown of patients at each stage
  - Digital adoption: % using app/USSD vs untracked
  - Wait times: avg, max, P90 from arrival → triage
  - Stock health: medicines below threshold, % of catalog healthy
  - Symptom intake rate: % of visits with symptoms submitted
"""

from datetime import date, datetime, timezone
from sqlalchemy import case, cast, Float, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pharmacy import Medicine, StockLedger
from app.models.visit import SymptomEntry, TriageEntry, Visit, VisitState


async def get_throughput(db: AsyncSession, facility_id: int, target_date: date) -> dict:
    base = select(func.count(Visit.id)).where(
        Visit.facility_id == facility_id,
        func.date(Visit.arrived_at) == target_date,
    )
    total = (await db.execute(base)).scalar_one()

    by_state = await db.execute(
        select(Visit.state, func.count(Visit.id))
        .where(Visit.facility_id == facility_id, func.date(Visit.arrived_at) == target_date)
        .group_by(Visit.state)
    )
    state_counts = {row[0].value: row[1] for row in by_state.all()}

    active = total - state_counts.get(VisitState.DISCHARGED.value, 0)

    return {
        "date": str(target_date),
        "total_arrivals": total,
        "currently_active": active,
        "discharged": state_counts.get(VisitState.DISCHARGED.value, 0),
        "by_state": state_counts,
    }


async def get_visit_funnel(db: AsyncSession, facility_id: int, target_date: date) -> dict:
    """
    Shows drop-off at each stage — good for identifying bottlenecks.
    E.g. many arrived but few triaged = nurse is the bottleneck.
    """
    states = [
        VisitState.ARRIVED,
        VisitState.SYMPTOMS_SUBMITTED,
        VisitState.TRIAGED,
        VisitState.IN_CONSULTATION,
        VisitState.PRESCRIBED,
        VisitState.AT_PHARMACY,
        VisitState.DISCHARGED,
    ]

    result = await db.execute(
        select(Visit.state, func.count(Visit.id))
        .where(Visit.facility_id == facility_id, func.date(Visit.arrived_at) == target_date)
        .group_by(Visit.state)
    )
    counts = {row[0].value: row[1] for row in result.all()}
    total = sum(counts.values()) or 1

    funnel = []
    for state in states:
        count = counts.get(state.value, 0)
        funnel.append({
            "stage": state.value,
            "count": count,
            "pct_of_total": round(count / total * 100, 1),
        })
    return {"date": str(target_date), "funnel": funnel}


async def get_wait_time_stats(db: AsyncSession, facility_id: int, target_date: date) -> dict:
    """
    Arrival → triage time (minutes). Only counts visits that have been triaged.
    Uses PostgreSQL EXTRACT to compute duration.
    """
    result = await db.execute(
        select(
            func.avg(
                func.extract("epoch", TriageEntry.created_at - Visit.arrived_at) / 60
            ).label("avg_minutes"),
            func.max(
                func.extract("epoch", TriageEntry.created_at - Visit.arrived_at) / 60
            ).label("max_minutes"),
            func.min(
                func.extract("epoch", TriageEntry.created_at - Visit.arrived_at) / 60
            ).label("min_minutes"),
            func.count(TriageEntry.id).label("triaged_count"),
        )
        .select_from(Visit)
        .join(TriageEntry, TriageEntry.visit_id == Visit.id)
        .where(
            Visit.facility_id == facility_id,
            func.date(Visit.arrived_at) == target_date,
        )
    )
    row = result.one()
    return {
        "date": str(target_date),
        "avg_arrival_to_triage_minutes": round(row.avg_minutes or 0, 1),
        "max_arrival_to_triage_minutes": round(row.max_minutes or 0, 1),
        "min_arrival_to_triage_minutes": round(row.min_minutes or 0, 1),
        "triaged_visits": row.triaged_count,
    }


async def get_digital_adoption(db: AsyncSession, facility_id: int, target_date: date) -> dict:
    """
    % of visits where symptoms were submitted digitally (app / USSD / kiosk).
    This is the key KPI proving the system is being used.
    """
    total_result = await db.execute(
        select(func.count(Visit.id)).where(
            Visit.facility_id == facility_id,
            func.date(Visit.arrived_at) == target_date,
        )
    )
    total = total_result.scalar_one() or 1

    # Count visits that have at least one symptom entry, grouped by channel
    channel_result = await db.execute(
        select(SymptomEntry.channel, func.count(func.distinct(SymptomEntry.visit_id)))
        .select_from(SymptomEntry)
        .join(Visit, Visit.id == SymptomEntry.visit_id)
        .where(
            Visit.facility_id == facility_id,
            func.date(Visit.arrived_at) == target_date,
        )
        .group_by(SymptomEntry.channel)
    )
    by_channel = {row[0]: row[1] for row in channel_result.all()}

    digital_total = sum(by_channel.values())
    return {
        "date": str(target_date),
        "total_visits": total,
        "visits_with_digital_intake": digital_total,
        "digital_intake_rate_pct": round(digital_total / total * 100, 1),
        "by_channel": by_channel,
    }


async def get_stock_health(db: AsyncSession, facility_id: int) -> dict:
    result = await db.execute(
        select(StockLedger, Medicine)
        .join(Medicine, StockLedger.medicine_id == Medicine.id)
        .where(StockLedger.facility_id == facility_id)
    )
    rows = result.all()
    if not rows:
        return {"total_medicines": 0, "healthy": 0, "low_stock": 0, "stockout": 0, "health_rate_pct": 0, "items": []}

    items = []
    healthy = low = stockout = 0
    for ledger, medicine in rows:
        if ledger.quantity == 0:
            status = "stockout"
            stockout += 1
        elif ledger.quantity <= medicine.reorder_threshold:
            status = "low"
            low += 1
        else:
            status = "ok"
            healthy += 1
        items.append({
            "medicine_id": medicine.id,
            "name": medicine.name,
            "quantity": ledger.quantity,
            "reorder_threshold": medicine.reorder_threshold,
            "status": status,
        })

    total = len(rows)
    return {
        "total_medicines": total,
        "healthy": healthy,
        "low_stock": low,
        "stockout": stockout,
        "health_rate_pct": round(healthy / total * 100, 1),
        "items": sorted(items, key=lambda x: x["quantity"]),
    }


async def get_dashboard(db: AsyncSession, facility_id: int, target_date: date) -> dict:
    """Single endpoint returning all KPIs — used by the admin dashboard."""
    throughput = await get_throughput(db, facility_id, target_date)
    funnel = await get_visit_funnel(db, facility_id, target_date)
    wait_times = await get_wait_time_stats(db, facility_id, target_date)
    adoption = await get_digital_adoption(db, facility_id, target_date)
    stock = await get_stock_health(db, facility_id)

    return {
        "facility_id": facility_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "throughput": throughput,
        "visit_funnel": funnel,
        "wait_times": wait_times,
        "digital_adoption": adoption,
        "stock_health": stock,
        # Headline KPIs (for the summary cards at the top of the dashboard)
        "kpis": {
            "total_arrivals_today": throughput["total_arrivals"],
            "currently_in_clinic": throughput["currently_active"],
            "avg_wait_to_triage_mins": wait_times["avg_arrival_to_triage_minutes"],
            "digital_intake_rate_pct": adoption["digital_intake_rate_pct"],
            "stock_health_pct": stock["health_rate_pct"],
            "medicines_needing_reorder": stock["low_stock"] + stock["stockout"],
        },
    }
