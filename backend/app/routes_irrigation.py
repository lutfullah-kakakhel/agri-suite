from __future__ import annotations

import os, json, math
from uuid import uuid4
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Depends, Response, status, Body
from pydantic import BaseModel, Field as PydField
from supabase import create_client, Client
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import get_db

# -------- Router (NO prefix) --------
router = APIRouter()

# -------- Env / Clients --------
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
OPENWEATHER_KEY = os.environ.get("OPENWEATHER_KEY")

sb: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# -------- Schemas --------
class RecommendationOut(BaseModel):
    recommendation_mm: float
    window_days: int = 3
    inputs: dict

class ConfirmBody(BaseModel):
    recommendation_mm: float = PydField(..., gt=0)
    window_days: int = 3
    notes: Optional[str] = None
    inputs: dict

# -------- Helpers --------
def _close_ring(coords: list[list[float]]) -> list[list[float]]:
    if coords and coords[0] != coords[-1]:
        return coords + [coords[0]]
    return coords

def _centroid_and_area(positions: list[list[float]]) -> tuple[float, float, float, float]:
    """positions: [[lon,lat], ...] (closed). Returns centroid_lat, centroid_lon, area_ha, area_ac."""
    lats = [p[1] for p in positions]
    lons = [p[0] for p in positions]
    lat0 = sum(lats) / len(lats)
    lon0 = sum(lons) / len(lons)

    m_per_deg_lat = 111_132.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat0))
    xy = [((lon - lon0) * m_per_deg_lon, (lat - lat0) * m_per_deg_lat) for lon, lat in zip(lons, lats)]

    A2 = Cx = Cy = 0.0
    for i in range(len(xy) - 1):
        x1, y1 = xy[i]
        x2, y2 = xy[i + 1]
        cross = x1 * y2 - x2 * y1
        A2 += cross
        Cx += (x1 + x2) * cross
        Cy += (y1 + y2) * cross
    A = abs(A2) / 2.0  # m²
    cx = Cx / (3 * A2) if A2 != 0 else 0.0
    cy = Cy / (3 * A2) if A2 != 0 else 0.0

    centroid_lon = lon0 + (cx / m_per_deg_lon)
    centroid_lat = lat0 + (cy / m_per_deg_lat)
    area_ha = A / 10_000.0
    area_ac = A / 4_046.8564224
    return float(centroid_lat), float(centroid_lon), float(area_ha), float(area_ac)

async def fetch_weather_et0(lat: float, lon: float) -> dict:
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
    steps = data.get("list", [])[:8]  # next 24h
    temps = [i["main"]["temp"] for i in steps]
    rain = sum(i.get("rain", {}).get("3h", 0.0) for i in steps)
    temp_c = round(sum(temps) / len(temps), 1) if temps else 30.0
    et0_mm = round(max(0.0, 0.0023 * (temp_c + 17.8)) * 24.0, 1)
    return {"temp_c": temp_c, "rainfall_forecast_mm": round(rain, 1), "et0_mm": et0_mm}

async def fetch_satellite_soil_moisture(lat: float, lon: float) -> Optional[float]:
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
        sm_pct = round((sm_kg_m2 / 10.0), 1)  # crude %
        if sm_pct < 0 or sm_pct > 60:
            return None
        return sm_pct
    except Exception:
        return None

def compute_irrigation_mm(crop: Optional[str], temp_c: float, et0_mm: float, rain_mm: float, soil: Optional[float]) -> float:
    kc = 0.7
    c = (crop or "").lower().strip()
    if c in ("rice", "paddy"): kc = 1.1
    elif c in ("chickpea", "gram"): kc = 0.6
    elif c in ("maize", "corn"): kc = 0.9
    elif c in ("cotton",): kc = 1.0

    target = max(0.0, kc * et0_mm - rain_mm)
    if soil is not None:
        if soil >= 40: target *= 0.6
        elif soil >= 30: target *= 0.8
    return round(target, 1)

# -------- Routes --------
@router.get("/healthz")
def healthz():
    return {"ok": True, "db": "up"}

@router.post("/fields")
def create_field(body: dict = Body(...), db: Session = Depends(get_db)):
    """
    Accepts:
      { "geometry": {GeoJSON Polygon}, "crop": optional, "client_id": optional }
      OR raw GeoJSON polygon as body.
    Computes centroid/area on server and inserts into public.fields.
    """
    try:
        geometry = None
        crop = None
        client_id = None
        if isinstance(body, dict):
            if "type" in body and "coordinates" in body:
                geometry = body
            else:
                geometry = body.get("geometry")
                crop = body.get("crop")
                client_id = body.get("client_id")

        if not isinstance(geometry, dict) or "type" not in geometry or "coordinates" not in geometry:
            raise HTTPException(status_code=422, detail="Body must include GeoJSON Polygon under 'geometry' or be the GeoJSON itself.")
        if geometry.get("type") != "Polygon":
            raise HTTPException(status_code=422, detail="Only GeoJSON Polygon is supported")

        rings = geometry.get("coordinates") or []
        if not rings or not isinstance(rings[0], list) or len(rings[0]) < 3:
            raise HTTPException(status_code=422, detail="Polygon must have at least 3 coordinates")

        outer = _close_ring(rings[0])
        geometry["coordinates"][0] = outer
        centroid_lat, centroid_lon, area_ha, area_ac = _centroid_and_area(outer)

        new_id = str(uuid4())
        sql = text("""
          insert into public.fields
            (id, client_id, crop, geometry, centroid_lat, centroid_lon, area_ha, area_ac)
          values
            (:id, :client_id, :crop, :geometry::jsonb, :lat, :lon, :area_ha, :area_ac)
          returning id
        """)
        db.execute(sql, {
            "id": new_id,
            "client_id": client_id,
            "crop": crop,
            "geometry": json.dumps(geometry),
            "lat": centroid_lat,
            "lon": centroid_lon,
            "area_ha": area_ha,
            "area_ac": area_ac,
        })
        db.commit()
        return {
            "id": new_id,
            "centroid": {"lat": centroid_lat, "lon": centroid_lon},
            "area_ha": area_ha, "area_ac": area_ac, "crop": crop
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Insert failed: {e}")

@router.get(
    "/fields/{field_id}/recommendation",
    response_model=RecommendationOut,
    responses={202: {"description": "Processing"}}
)
async def get_recommendation(field_id: str, soil_moisture_pct: Optional[float] = None):
    # pull lat/lon + crop from fields_v (or directly from fields if you prefer)
    res = sb.table("fields_v").select("*").eq("id", field_id).limit(1).execute()
    rows = res.data or []
    if not rows:
        raise HTTPException(404, "Field not found")
    f = rows[0]
    lat = f["lat"]
    lon = f["lon"]
    crop = f.get("crop")

    wx = await fetch_weather_et0(lat, lon)
    sm = soil_moisture_pct if soil_moisture_pct is not None else await fetch_satellite_soil_moisture(lat, lon)

    if sm is None:
        body = {"status": "processing", "eta_minutes": 2, "note": "Fetching satellite moisture…"}
        return Response(content=json.dumps(body), media_type="application/json", status_code=status.HTTP_202_ACCEPTED)

    mm = compute_irrigation_mm(crop, wx["temp_c"], wx["et0_mm"], wx["rainfall_forecast_mm"], sm)
    return {"recommendation_mm": mm, "window_days": 3, "inputs": {"crop": crop, "soil_moisture_pct": sm, **wx}}

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

@router.post("/fields2")
def create_field2(body: dict = Body(...), db: Session = Depends(get_db)):
    return create_field(body=body, db=db)





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
