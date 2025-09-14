# backend/app/main.py
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException, Depends, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field as PydField
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import get_db, ping


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
    allow_origins=["*"],  # tighten later for production
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========= Health & root =========

@app.get("/")
def root():
    return {"status": "ok", "service": "agri-suite-api"}

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

@app.get("/readyz")
def readyz():
    return {"ok": True}


# ========= Field endpoints =========

@app.post("/fields")
def create_field(payload: FieldCreate, db: Session = Depends(get_db)):
    """
    Store boundary as PostGIS geometry (SRID 4326), but accept GeoJSON from client.
    Returns GeoJSON for boundary & centroid + computed area_ha.
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
    row = db.execute(sql, {
        "farm_id": str(payload.farm_id),
        "name": payload.name,
        "crop": payload.crop,
        "sowing_date": payload.sowing_date,
        "soil": payload.soil,
        "kc_profile": payload.kc_profile,
        # pass as JSON string to satisfy ST_G_
