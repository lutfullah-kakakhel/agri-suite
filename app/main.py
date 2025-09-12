# app/main.py
import os
import math
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field as PydField, field_validator
from sqlalchemy import (
    create_engine, Column, Integer, String, Float, Text, DateTime
)
from sqlalchemy.orm import sessionmaker, declarative_base, Session

# ---------------------------
# Configuration / Database
# ---------------------------
# Load DATABASE_URL from environment; default to local SQLite under ./data
DB_URL = os.getenv("DATABASE_URL", "sqlite:///./data/app.db")

# If using local relative SQLite, ensure folder exists
if DB_URL.startswith("sqlite:///./"):
    os.makedirs("./data", exist_ok=True)

# SQLite needs check_same_thread=False for FastAPI sync sessions
engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False} if DB_URL.startswith("sqlite") else {},
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()

# ---------------------------
# SQLAlchemy Model
# ---------------------------
class Field(Base):
    __tablename__ = "fields"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    crop = Column(String(80), nullable=False)
    centroid_lat = Column(Float, nullable=False)
    centroid_lon = Column(Float, nullable=False)
    polygon_geojson = Column(Text, nullable=True)
    last_irrigation_ts = Column(DateTime(timezone=True), nullable=True)

Base.metadata.create_all(bind=engine)

# ---------------------------
# Pydantic Schemas
# ---------------------------
class FieldCreate(BaseModel):
    name: str
    crop: str
    centroid_lat: float = PydField(..., ge=-90, le=90)
    centroid_lon: float = PydField(..., ge=-180, le=180)
    polygon_geojson: Optional[str] = None
    last_irrigation_ts: Optional[datetime] = None

    @field_validator("name", "crop")
    @classmethod
    def nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be empty")
        return v.strip()

class FieldOut(BaseModel):
    id: int
    name: str
    crop: str
    centroid_lat: float
    centroid_lon: float
    polygon_geojson: Optional[str] = None
    last_irrigation_ts: Optional[datetime] = None

    class Config:
        from_attributes = True  # for SQLAlchemy -> Pydantic

# Advice payload
class AdviceToday(BaseModel):
    tmin_c: float
    tmax_c: float
    rain_mm: float
    rain_prob_pct: int
    et0_mm: float

class AdviceMessage(BaseModel):
    en: str
    ur: str

class AdviceOut(BaseModel):
    field: str
    crop: str
    today: AdviceToday
    since_last_irrigation_days: int
    net_deficit_mm: float
    messages: List[AdviceMessage]

# ---------------------------
# FastAPI app
# ---------------------------
app = FastAPI(title="Irrigation Advisory API")

# Allow mobile/web clients (adjust origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # restrict in production
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency to get a DB session per request
def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------------------
# Endpoints
# ---------------------------
@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/fields", response_model=List[FieldOut])
def list_fields(db: Session = Depends(get_db)):
    return db.query(Field).order_by(Field.id.desc()).all()

@app.post("/fields", response_model=FieldOut)
def create_field(payload: FieldCreate, db: Session = Depends(get_db)):
    rec = Field(
        name=payload.name,
        crop=payload.crop,
        centroid_lat=payload.centroid_lat,
        centroid_lon=payload.centroid_lon,
        polygon_geojson=payload.polygon_geojson,
        last_irrigation_ts=payload.last_irrigation_ts,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec

@app.get("/fields/{field_id}", response_model=FieldOut)
def get_field(field_id: int, db: Session = Depends(get_db)):
    rec = db.query(Field).filter(Field.id == field_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Field not found")
    return rec

@app.get("/fields/{field_id}/advice", response_model=AdviceOut)
def get_advice(field_id: int, db: Session = Depends(get_db)):
    rec = db.query(Field).filter(Field.id == field_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Field not found")

    # --- Simple placeholder weather/ET0 logic (replace with real fetch later) ---
    # You can wire your real weather + ET₀ function here.
    # For now we compute a very rough ET0 using Hargreaves-like approximation.
    # Note: these numbers are dummies just to keep the contract stable.
    tmin = 22.0
    tmax = 34.0
    tmean = (tmin + tmax) / 2
    # crude diurnal range
    td = max(0.1, tmax - tmin)
    # rough extraterrestrial radiation scaling for plains (very approximate)
    et0 = 0.0023 * (tmean + 17) * math.sqrt(td) * 10.0  # ~mm/day

    rain_mm = 1.0
    rain_prob = 30

    # days since last irrigation
    if rec.last_irrigation_ts:
        delta_days = max(0, int((datetime.now(timezone.utc) - rec.last_irrigation_ts).total_seconds() // 86400))
    else:
        delta_days = 3  # default assumption

    # very rough crop coefficient and soil bucket
    kc = 0.9
    daily_use = et0 * kc
    net_deficit = max(0.0, daily_use * delta_days - rain_mm)

    # Messages (English + Urdu)
    if net_deficit < 10:
        msgs = [
            AdviceMessage(
                en="Conditions are normal. Monitor the next forecast.",
                ur="صورتحال معمول کی ہے۔ اگلی موسمی پیشن گوئی پر نظر رکھیں۔",
            )
        ]
    elif net_deficit < 25:
        msgs = [
            AdviceMessage(
                en=f"Field is drying (deficit ≈ {net_deficit:.1f} mm). Plan irrigation within 1–2 days.",
                ur=f"کھیت میں نمی کم ہو رہی ہے (کمی تقریباً {net_deficit:.1f} ملی میٹر)۔ ۱–۲ دن میں آبپاشی کیجئے۔",
            )
        ]
    else:
        msgs = [
            AdviceMessage(
                en=f"Deficit high (≈ {net_deficit:.1f} mm). Irrigate now if field is available.",
                ur=f"کمی زیادہ ہے (تقریباً {net_deficit:.1f} ملی میٹر)۔ اگر ممکن ہو تو فوراً آبپاشی کریں۔",
            )
        ]

    today = AdviceToday(
        tmin_c=tmin,
        tmax_c=tmax,
        rain_mm=rain_mm,
        rain_prob_pct=rain_prob,
        et0_mm=round(et0, 1),
    )

    return AdviceOut(
        field=rec.name,
        crop=rec.crop,
        today=today,
        since_last_irrigation_days=delta_days,
        net_deficit_mm=round(net_deficit, 1),
        messages=msgs,
    )
