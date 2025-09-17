# routes_irrigation.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from supabase import create_client, Client
import httpx, os

router = APIRouter(prefix="/api/v1")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]  # service role on Render
OPENWEATHER_KEY = os.environ.get("OPENWEATHER_KEY")
sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class RecommendationOut(BaseModel):
    recommendation_mm: float
    window_days: int = 3
    inputs: dict

async def fetch_weather_et0(lat: float, lon: float) -> dict:
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
    et0_mm = round(max(0.0, 0.0023 * (temp_c + 17.8)) * 24.0, 1)  # placeholder
    return {"temp_c": temp_c, "rainfall_forecast_mm": round(rain, 1), "et0_mm": et0_mm}

def compute_irrigation_mm(crop: str, temp_c: float, et0_mm: float, rain_mm: float, soil: float | None):
    kc = 0.7
    target = max(0.0, kc * et0_mm - rain_mm)
    if soil is not None:
        if soil >= 40: target *= 0.6
        elif soil >= 30: target *= 0.8
    crop_l = (crop or "wheat").lower()
    if crop_l in ["rice", "paddy"]: target *= 1.2
    elif crop_l in ["chickpea", "gram"]: target *= 0.85
    return round(target, 1)

@router.get("/healthz")
def healthz(): return {"ok": True}

@router.get("/fields/{field_id}/recommendation", response_model=RecommendationOut)
async def get_recommendation(field_id: str, soil_moisture_pct: float | None = None):
    # Use a view if you created fields_v; otherwise compute lat/lon here
    row = sb.rpc("exec_sql", {"sql": f"""
        select id, crop, st_y(centroid) as lat, st_x(centroid) as lon
        from public.fields where id = '{field_id}' limit 1;
    """}).execute().data
    if not row: raise HTTPException(404, "Field not found")
    f = row[0]
    wx = await fetch_weather_et0(f["lat"], f["lon"])
    mm = compute_irrigation_mm(f.get("crop") or "wheat", wx["temp_c"], wx["et0_mm"], wx["rainfall_forecast_mm"], soil_moisture_pct)
    return {"recommendation_mm": mm, "window_days": 3,
            "inputs": {"crop": f.get("crop") or "wheat", "soil_moisture_pct": soil_moisture_pct, **wx}}

class ConfirmBody(BaseModel):
    recommendation_mm: float = Field(..., gt=0)
    window_days: int = 3
    notes: str | None = None
    inputs: dict

@router.post("/fields/{field_id}/recommendation/confirm")
def confirm_recommendation(field_id: str, body: ConfirmBody):
    ins = sb.table("schedules").insert({
        "field_id": field_id,
        "recommendation_mm": body.recommendation_mm,
        "window_days": body.window_days,
        "inputs": body.inputs,
        "notes": body.notes,
        "confirmed": True,
    }).execute()
    return {"ok": True, "id": (ins.data or [{}])[0].get("id")}

@router.get("/fields/{field_id}/schedules")
def list_schedules(field_id: str):
    out = (sb.table("schedules")
           .select("*")
           .eq("field_id", field_id)
           .order("created_at", desc=True)
           .limit(50).execute())
    return out.data or []

