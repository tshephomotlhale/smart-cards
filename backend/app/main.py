from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.redis import close_redis, get_redis
from app.db.session import engine
from app.models.base import Base
# Import all models so SQLAlchemy registers them before create_all
from app.models import audit, facility, patient, pharmacy as pharmacy_model, user, visit  # noqa: F401
from app.routes import auth, patients, visits, queue, pharmacy, ussd, analytics, events
from app.services.ussd.handler import set_default_facility
from app.db.session import AsyncSessionLocal
from sqlalchemy import select, func
from app.models.facility import Facility


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # Set default USSD facility to the first active facility
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(func.min(Facility.id)).where(Facility.is_active == True))
        first_id = result.scalar_one_or_none()
        if first_id:
            set_default_facility(first_id)
    yield
    # Shutdown
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description="Smart Patient Card System API — Botswana Health Facilities",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(visits.router)
app.include_router(queue.router)
app.include_router(pharmacy.router)
app.include_router(ussd.router)
app.include_router(analytics.router)
app.include_router(events.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": settings.APP_NAME}
