# app/routes_irrigation.py
from __future__ import annotations

import os
import json
from uuid import uuid4
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Depends, Response, status
from pydantic import BaseModel, Field as PydField
from supabase import create_client, Client
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import get_db

# ---------------- Router (NO prefix) ----------------
router = APIRouter()

# ---------------- Env / Clients ----------------
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]  # service role key on Render
OPENWEATHER_KEY = os.environ.get("OPENWEATHER_KEY")

sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------- Schemas ----------------
class RecommendationOut(BaseModel):
    recommendation_mm: float
    window_days: int = 3
    inputs: dict

class ConfirmBody(BaseModel):
    recommendation_mm: float = PydField(..., gt=0)
    window_days: int = 3
    notes: Optional[str] = None
    inputs: dict

class FieldIn(BaseModel):
    """Minimal field creation: geometry is required; crop is optional."""
    geometry: dict = PydField(..., description="GeoJSON Polygon")
    crop: Optional[str] = PydField(None, description="Optional crop key (e.g., wheat, rice)")

# ---------------- Helpers ----------------
async def fetch_weather_et0(lat: float, lon: float) -> dict:
    """Fetch next-24h weather snapshot and a simple ET0 proxy."""
    if not OPENWEATHER_KEY:
        raise HTTPException(500, "OPENWEATHER_KEY not set")
    url = (
        "https://api.openweathermap.org/data/2.5/forecast"
        f"?lat={lat}&lon={lon}&appid={OPENWEATHER_KEY}&units=metric"
    )
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()

    steps = data.get("list", [])[:8]  # next 24h (3h * 8)
    temps = [i["main"]["temp"] for i in steps]
    rain = sum(i.get("rain", {}).get("3h", 0.0) for i in steps)
    temp_c = round(sum(temps) / len(temps), 1) if temps else 30.0

    # quick ET0/day (Hargreaves-lite; replace with FAO-56 later if needed)
    et0_mm = round(max(0.0, 0.0023 * (temp_c + 17.8)) * 24.0, 1)

    return {
        "temp_c": temp_c,
        "rainfall_forecast_mm": round(rain, 1),
        "et0_mm": et0_mm,
    }

async def fetch_satellite_soil_moisture(lat: float, lon: float) -> Optional[float]:
    """
    Try NASA POWER daily soil moisture (SOILM_TOT, kg/m^2).
    Very rough conversion to % (heuristic). If unavailable/slow, return None.
    """
    url = (
        "https://power.larc.nasa.gov/api/temporal/daily/point"
        f"?parameters=SOILM_TOT&community=AG&longitude={lon}&latitude={lat}"
        "&start=20250101&end=20250101&format=JSON"
    )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            data = r.json()
        vals = data["properties"]["parameter"]["SOILM_TOT"]
        day_key = sorted(vals.keys())[-1]
        sm_kg_m2 = float(vals[day_key])
        # crude: % volumetric ≈ (kg/m^2 over top 10 cm) / 10
        sm_pct = round((sm_kg_m2 / 10.0), 1)
        if sm_pct < 0 or sm_pct > 60:
            return None
        return sm_pct
    except Exception:
        return None

def compute_irrigation_mm(
    crop: Optional[str],
    temp_c: float,
    et0_mm: float,
    rain_mm: float,
    soil: Optional[float],
) -> float:
    """
    Simplified water need:
      target = Kc * ET0 - rain
      soil moisture adjustment reduces target when soil is already wetter.
    """
    kc = 0.7
    crop_l = (crop or "").lower().strip()
    if crop_l in ("rice", "paddy"):
        kc = 1.1
    elif crop_l in ("chickpea", "gram"):
        kc = 0.6
    elif crop_l in ("maize", "corn"):
        kc = 0.9
    elif crop_l in ("cotton",):
        kc = 1.0
    # else wheat/unknown ~0.7

    target = max(0.0, kc * et0_mm - rain_mm)

    if soil is not None:
        if soil >= 40:
            target *= 0.6
        elif soil >= 30:
            target *= 0.8

    return round(target, 1)

# ---------------- Routes (NO prefix) ----------------
@router.get("/healthz")
def healthz():
    return {"ok": True}

@router.post("/fields")
def create_field(field: FieldIn, db: Session = Depends(get_db)):
    """
    Minimal create: only geometry is required (stored as JSONB in fields.geometry).
    crop is optional (nullable).
    """
    try:
        new_id = str(uuid4())
        sql = text("""
          insert into public.fields (id, geometry, crop)
          values (:id, :geometry::jsonb, :crop)
          returning id
        """)
        db.execute(sql, {"id": new_id, "geometry": json.dumps(field.geometry), "crop": field.crop})
        db.commit()
        return {"id": new_id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Insert failed: {e}")

@router.get(
    "/fields/{field_id}/recommendation",
    response_model=RecommendationOut,
    responses={202: {"description": "Processing", "content": {"application/json": {}}}},
)
async def get_recommendation(field_id: str, soil_moisture_pct: Optional[float] = None):
    """
    Reads centroid (lat/lon) + crop from helper view 'fields_v'.
    If soil_moisture_pct not provided, tries satellite SM; if not immediately available,
    returns 202 with an ETA so the app can auto-refresh.
    """
    # pull one row with lat/lon and crop
    res = sb.table("fields_v").select("*").eq("id", field_id).limit(1).execute()
    rows = res.data or []
    if not rows:
        raise HTTPException(404, "Field not found")
    f = rows[0]
    lat = f["lat"]
    lon = f["lon"]
    crop = f.get("crop")  # may be None

    # weather
    wx = await fetch_weather_et0(lat, lon)

    # soil moisture: manual override or satellite
    sm = soil_moisture_pct
    if sm is None:
        sm = await fetch_satellite_soil_moisture(lat, lon)

    if sm is None:
        body = {"status": "processing", "eta_minutes": 2, "note": "Fetching satellite moisture…"}
        return Response(content=json.dumps(body), media_type="application/json", status_code=status.HTTP_202_ACCEPTED)

    mm = compute_irrigation_mm(crop, wx["temp_c"], wx["et0_mm"], wx["rainfall_forecast_mm"], sm)

    return {
        "recommendation_mm": mm,
        "window_days": 3,
        "inputs": {"crop": crop, "soil_moisture_pct": sm, **wx},
    }

@router.post("/fields/{field_id}/recommendation/confirm")
def confirm_recommendation(field_id: str, body: ConfirmBody):
    ins = (
        sb.table("schedules")
        .insert({
            "field_id": field_id,
            "recommendation_mm": body.recommendation_mm,
            "window_days": body.window_days,
            "inputs": body.inputs,
            "notes": body.notes,
            "confirmed": True,
        })
        .execute()
    )
    return {"ok": True, "id": (ins.data or [{}])[0].get("id")}

@router.get("/fields/{field_id}/schedules")
def list_schedules(field_id: str):
    q = (
        sb.table("schedules")
        .select("*")
        .eq("field_id", field_id)
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return q.data or []
