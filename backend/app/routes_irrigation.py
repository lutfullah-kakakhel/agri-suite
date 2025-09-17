# backend/app/routes_irrigation.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from supabase import create_client, Client
import httpx
import os

# All endpoints will live under /api/v1/...
router = APIRouter(prefix="/api/v1")

# ----- Environment / clients -----
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]  # service role key on Render
OPENWEATHER_KEY = os.environ.get("OPENWEATHER_KEY")

sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ----- Schemas -----
class RecommendationOut(BaseModel):
    recommendation_mm: float
    window_days: int = 3
    inputs: dict

class ConfirmBody(BaseModel):
    recommendation_mm: float = Field(..., gt=0)
    window_days: int = 3
    notes: str | None = None
    inputs: dict

# ----- Helpers -----
async def fetch_weather_et0(lat: float, lon: float) -> dict:
    """Fetch next-24h weather snapshot and a simple ET0 proxy."""
    if not OPENWEATHER_KEY:
        raise HTTPException(500, "OPENWEATHER_KEY not set")
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&appid={OPENWEATHER_KEY}&units=metric"
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()

    temps = [i["main"]["temp"] for i in data["list"][:8]]
    rain = sum(i.get("rain", {}).get("3h", 0.0) for i in data["list"][:8])
    temp_c = round(sum(temps)/len(temps), 1) if temps else 30.0

    # quick placeholder ET0/day (replace with FAO-56 later if you want)
    et0_mm = round(max(0.0, 0.0023 * (temp_c + 17.8)) * 24.0, 1)

    return {
        "temp_c": temp_c,
        "rainfall_forecast_mm": round(rain, 1),
        "et0_mm": et0_mm,
    }

def compute_irrigation_mm(crop: str, temp_c: float, et0_mm: float, rain_mm: float, soil: float | None):
    kc = 0.7
    target = max(0.0, kc * et0_mm - rain_mm)
    if soil is not None:
        if soil >= 40:
            target *= 0.6
        elif soil >= 30:
            target *= 0.8
    crop_l = (crop or "wheat").lower()
    if crop_l in ["rice", "paddy"]:
        target *= 1.2
    elif crop_l in ["chickpea", "gram"]:
        target *= 0.85
    return round(target, 1)

# ----- Routes -----
@router.get("/healthz")
def healthz():
    return {"ok": True}

@router.get("/fields/{field_id}/recommendation", response_model=RecommendationOut)
async def get_recommendation(field_id: str, soil_moisture_pct: float | None = None):
    """
    Reads lat/lon from a helper view 'fields_v' that exposes centroid as lat/lon.
    If you haven't created it yet, run the SQL below once.
    """
    # pull one row with lat/lon and crop
    res = sb.table("fields_v").select("*").eq("id", field_id).limit(1).execute()
    rows = res.data or []
    if not rows:
        raise HTTPException(404, "Field not found")
    f = rows[0]
    lat = f["lat"]
    lon = f["lon"]
    crop = f.get("crop") or "wheat"

    wx = await fetch_weather_et0(lat, lon)
    mm = compute_irrigation_mm(crop, wx["temp_c"], wx["et0_mm"], wx["rainfall_forecast_mm"], soil_moisture_pct)

    return {
        "recommendation_mm": mm,
        "window_days": 3,
        "inputs": {"crop": crop, "soil_moisture_pct": soil_moisture_pct, **wx},
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
