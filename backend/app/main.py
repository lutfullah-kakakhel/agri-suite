# backend/app/main.py
import json
from datetime import date, timedelta
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import engine, SessionLocal, Base, ping


app = FastAPI(title="Irrigation API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


def get_db() -> Session:
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/healthz")
def healthz():
    ping()
    return {"ok": True}


def _polygon_wkt_from_geojson(gj: Dict[str, Any]) -> str:
    """Expect GeoJSON Polygon with coordinates [[ [lng,lat], ... ]]."""
    if not (gj and gj.get("type") == "Polygon"):
        raise ValueError("boundary_geojson must be a GeoJSON Polygon")
    coords: List[List[float]] = gj["coordinates"][0]
    if coords[0] != coords[-1]:
        coords.append(coords[0])  # close ring
    ring = ", ".join(f"{lng} {lat}" for lng, lat in coords)
    return f"POLYGON(({ring}))"


@app.post("/fields")
def create_field(payload: Dict[str, Any], db: Session = Depends(get_db)):
    farm_id = payload.get("farm_id")
    name = payload.get("name")
    gj = payload.get("boundary_geojson")

    if not farm_id or not name or not gj:
        raise HTTPException(400, "farm_id, name, boundary_geojson are required")

    try:
        wkt = _polygon_wkt_from_geojson(gj)
    except Exception as e:
        raise HTTPException(400, f"Invalid GeoJSON polygon: {e}")

    row = db.execute(
        text("""
            INSERT INTO fields (farm_id, name, boundary)
            VALUES (:farm_id, :name, ST_GeomFromText(:wkt, 4326))
            RETURNING id, farm_id, name,
                      area_ha,
                      ST_AsGeoJSON(ST_ForcePolygonCCW(boundary)) AS boundary_geojson
        """),
        {"farm_id": farm_id, "name": name, "wkt": wkt},
    ).mappings().first()

    if not row:
        raise HTTPException(500, "Insert failed")

    return {
        "id": row["id"],
        "farm_id": row["farm_id"],
        "name": row["name"],
        "area_ha": float(row["area_ha"]) if row["area_ha"] is not None else None,
        "boundary_geojson": json.loads(row["boundary_geojson"]),
    }


@app.patch("/fields/{field_id}")
def update_field(field_id: str, payload: Dict[str, Any], db: Session = Depends(get_db)):
    allowed = ("crop", "sowing_date", "soil", "kc_profile")
    set_clauses = []
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


@app.post("/fields/{field_id}/seed-schedule")
def seed_schedule(field_id: str, payload: Dict[str, Any], db: Session = Depends(get_db)):
    target = float(payload.get("target_event_mm", 40))
    eff = float(payload.get("system_efficiency", 0.8))
    days = int(payload.get("days", 45))

    r = db.execute(text("SELECT area_ha FROM fields WHERE id = :id"), {"id": field_id}).first()
    if not r:
        raise HTTPException(404, "field not found")

    area_ha = float(r[0]) if r[0] is not None else 0.0

    events = []
    d = date.today()
    while len(events) * 7 < days:
        net_mm = target
        gross_mm = round(net_mm / eff, 1)
        vol_m3 = round(gross_mm * area_ha * 10.0, 1) if area_ha else None
        events.append({"date": d.isoformat(), "net_mm": net_mm, "gross_mm": gross_mm, "volume_m3": vol_m3})
        d += timedelta(days=7)

    return {"events": events}


@app.post("/fields/{field_id}/schedules")
def save_schedule(field_id: str, payload: Dict[str, Any], db: Session = Depends(get_db)):
    events = payload.get("events", [])
    db.execute(text("""
        CREATE TABLE IF NOT EXISTS schedules (
          field_id UUID REFERENCES fields(id) ON DELETE CASCADE,
          body JSONB NOT NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    db.execute(text("INSERT INTO schedules (field_id, body) VALUES (:fid, CAST(:body AS JSONB))"),
               {"fid": field_id, "body": json.dumps(events)})
    db.commit()
    return {"saved": True, "count": len(events)}
