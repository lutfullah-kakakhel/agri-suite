# backend/app/main.py
from __future__ import annotations

import os
import json
from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException, Depends, Response, status, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field as PydField
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import get_db, ping


# ========= Config (CORS + API key) =========

# CORS: comma-separated list in BACKEND_CORS_ORIGINS, or "*" (default)
_origins_env = os.getenv("BACKEND_CORS_ORIGINS", "*").strip()
if _origins_env in ("", "*"):
    _allow_origins = ["*"]
else:
    _allow_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]

API_KEY_EXPECTED = os.getenv("API_KEY", "").strip()

def require_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> None:
    """Require X-API-Key header only if API_KEY is set in env."""
    if API_KEY_EXPECTED:
        if not x_api_key or x_api_key != API_KEY_EXPECTED:
            raise HTTPException(status_code=401, detail="Missing or invalid API key")
    return None


# ========= Pydantic models =========

class FieldCreate(BaseModel):
    farm_id: UUID
    name: str
    crop: Optional[str] = None
    sowing_date: Optional[date] = None
    soil: Optional[str] = None
    kc_profile: Optional[dict] = None
    boundary_geojson: dict = PydField(..., description="GeoJSON Polygon")

class ScheduleEvent(BaseModel):
    date: date
    net_mm: float
    gross_mm: float
    volume_m3: Optional[float] = None

class ScheduleSave(BaseModel):
    events: List[ScheduleEvent]


# ========= App & middleware =========

app = FastAPI(title="Irrigation API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========= Root / readiness / health =========

@app.api_route("/", methods=["GET", "HEAD"])
def root():
    # For HEAD, FastAPI returns 200 with no body
    return {"status": "ok", "service": "agri-suite-api"}

@app.api_route("/readyz", methods=["GET", "HEAD"])
def readyz():
    # Use this for Render health check (no DB)
    return {"ok": True}

@app.get("/healthz")
def healthz():
    try:
        ping()
        return {"ok": True, "db": "up"}
    except Exception:
        return Response(
            content='{"ok": false, "db": "down"}',
            media_type="application/json",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


# ========= Field endpoints =========

@app.post("/fields")
def create_field(
    payload: FieldCreate,
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
    """
    Accept GeoJSON polygon; store as PostGIS geometry (SRID 4326).
    Return boundary & centroid as GeoJSON and computed area_ha.
    """
    sql = text("""
        INSERT INTO fields (farm_id, name, crop, sowing_date, soil, kc_profile, boundary)
        VALUES (
          :farm_id, :name, :crop, :sowing_date, :soil, :kc_profile,
          ST_SetSRID(ST_GeomFromGeoJSON(:geojson::text), 4326)
        )
        RETURNING
          id, farm_id, name, crop, sowing_date, soil, kc_profile,
          ST_AsGeoJSON(boundary)::json AS boundary_geojson,
          area_ha,
          ST_AsGeoJSON(centroid)::json AS centroid,
          created_at
    """)
    params = {
        "farm_id": str(payload.farm_id),
        "name": payload.name,
        "crop": payload.crop,
        "sowing_date": payload.sowing_date,
        "soil": payload.soil,
        "kc_profile": payload.kc_profile,
        "geojson": json.dumps(payload.boundary_geojson),  # pass as text to ST_GeomFromGeoJSON
    }
    row = db.execute(sql, params).mappings().one()
    db.commit()
    return dict(row)

@app.patch("/fields/{field_id}")
def update_field(
    field_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
    """
    Patch selected attributes (no boundary update here).
    """
    allowed = ("crop", "sowing_date", "soil", "kc_profile")
    set_clauses: List[str] = []
    params: Dict[str, Any] = {"field_id": field_id}

    for key in allowed:
        if key in payload:
            set_clauses.append(f"{key} = :{key}")
            params[key] = json.dumps(payload[key]) if key == "kc_profile" else payload[key]

    if not set_clauses:
        return {"updated": False}

    db.execute(text(f"UPDATE fields SET {', '.join(set_clauses)} WHERE id = :field_id"), params)
    db.commit()
    return {"updated": True}

@app.get("/fields")
def list_fields(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT
          id, farm_id, name, crop, sowing_date, soil, kc_profile,
          ST_AsGeoJSON(boundary)::json AS boundary_geojson,
          area_ha,
          ST_AsGeoJSON(centroid)::json AS centroid,
          created_at
        FROM fields
        ORDER BY created_at DESC
    """)).mappings().all()
    return [dict(r) for r in rows]


# ========= Scheduling =========

@app.post("/fields/{field_id}/seed-schedule")
def seed_schedule(
    field_id: str,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
    """
    Generate weekly events for N days, using area_ha for volume calc.
    """
    target = float(payload.get("target_event_mm", 40))
    eff = float(payload.get("system_efficiency", 0.8))
    days = int(payload.get("days", 45))

    r = db.execute(text("SELECT area_ha FROM fields WHERE id = :id"), {"id": field_id}).first()
    if not r:
        raise HTTPException(404, "field not found")

    area_ha = float(r[0]) if r[0] is not None else 0.0

    events: List[Dict[str, Any]] = []
    d = date.today()
    while len(events) * 7 < days:
        net_mm = target
        gross_mm = round(net_mm / eff, 1)
        vol_m3 = round(gross_mm * area_ha * 10.0, 1) if area_ha else None
        events.append({
            "date": d.isoformat(),
            "net_mm": net_mm,
            "gross_mm": gross_mm,
            "volume_m3": vol_m3
        })
        d += timedelta(days=7)

    return {"events": events}

@app.post("/fields/{field_id}/schedules")
def save_schedule(
    field_id: str,
    payload: ScheduleSave,
    db: Session = Depends(get_db),
    _: None = Depends(require_api_key),
):
    """
    Persist schedule as a JSONB blob in schedules.body.
    """
    sql = text("""
        INSERT INTO schedules (field_id, body)
        VALUES (:fid, to_jsonb(:body::json))
        RETURNING field_id, created_at
    """)
    row = db.execute(sql, {
        "fid": field_id,
        "body": json.dumps(payload.model_dump()),  # {"events":[...]}
    }).mappings().one()
    db.commit()
    return {"ok": True, **dict(row)}

@app.get("/fields/{field_id}/schedules")
def get_schedule(field_id: str, db: Session = Depends(get_db)):
    """
    Return the latest saved schedule for a field (or empty if none).
    """
    row = db.execute(text("""
        SELECT body, created_at
        FROM schedules
        WHERE field_id = :fid
        ORDER BY created_at DESC
        LIMIT 1
    """), {"fid": field_id}).mappings().first()

    if not row:
        return {"field_id": field_id, "created_at": None, "events": []}

    body = row["body"]
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            body = {"events": []}

    events = body.get("events", [])
    return {"field_id": field_id, "created_at": row["created_at"], "events": events}
