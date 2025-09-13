import os, json
from datetime import date, timedelta
from typing import Any, Dict, List
import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL env var is not set")

app = FastAPI(title="Irrigation API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

def get_conn():
    # Supabase requires SSL; keep sslmode=require as default
    return psycopg.connect(DATABASE_URL, autocommit=True,
                           sslmode=os.getenv("POSTGRES_SSLMODE","require"))

@app.get("/healthz")
def healthz(): return {"ok": True}

@app.post("/fields")
def create_field(payload: Dict[str, Any]):
    farm_id = payload.get("farm_id")
    name = payload.get("name")
    gj = payload.get("boundary_geojson")
    if not (farm_id and name and gj and gj.get("type") == "Polygon"):
        raise HTTPException(400, "farm_id, name, boundary_geojson(Polygon) required")

    try:
        coords: List[List[float]] = gj["coordinates"][0]
        if coords[0] != coords[-1]:
            coords.append(coords[0])  # close ring if not closed
        ring = ", ".join([f"{lng} {lat}" for lng, lat in coords])
        wkt = f"POLYGON(({ring}))"
    except Exception as e:
        raise HTTPException(400, f"Invalid GeoJSON polygon: {e}")

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            INSERT INTO fields (farm_id, name, boundary)
            VALUES (%s, %s, ST_GeomFromText(%s, 4326))
            RETURNING id, farm_id, name, area_ha,
                      ST_AsGeoJSON(ST_ForcePolygonCCW(boundary)) AS boundary_geojson;
        """, (farm_id, name, wkt))
        row = cur.fetchone()
        if not row: raise HTTPException(500, "insert failed")

    return {
        "id": row[0], "farm_id": row[1], "name": row[2],
        "area_ha": float(row[3]),
        "boundary_geojson": json.loads(row[4]),
    }

@app.patch("/fields/{field_id}")
def update_field(field_id: str, payload: Dict[str, Any]):
    fields, vals = [], []
    for k in ("crop","sowing_date","soil","kc_profile"):
        if k in payload:
            if k == "kc_profile":
                fields.append("kc_profile = %s")
                vals.append(json.dumps(payload[k]) if payload[k] is not None else None)
            else:
                fields.append(f"{k} = %s"); vals.append(payload[k])
    if not fields:
        return {"updated": False}
    vals.append(field_id)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(f"UPDATE fields SET {', '.join(fields)} WHERE id = %s", vals)
    return {"updated": True}

@app.post("/fields/{field_id}/seed-schedule")
def seed_schedule(field_id: str, payload: Dict[str, Any]):
    target = float(payload.get("target_event_mm", 40))
    eff = float(payload.get("system_efficiency", 0.8))
    days = int(payload.get("days", 45))

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT area_ha FROM fields WHERE id=%s", (field_id,))
        r = cur.fetchone()
        if not r: raise HTTPException(404, "field not found")
        area_ha = float(r[0])

    events = []
    d = date.today()
    while len(events) * 7 < days:
        net_mm = target
        gross_mm = round(net_mm/eff, 1)
        vol_m3 = round(gross_mm * area_ha * 10.0, 1)
        events.append({"date": d.isoformat(), "net_mm": net_mm,
                       "gross_mm": gross_mm, "volume_m3": vol_m3})
        d += timedelta(days=7)

    return {"events": events}

@app.post("/fields/{field_id}/schedules")
def save_schedule(field_id: str, payload: Dict[str, Any]):
    events = payload.get("events", [])
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
              field_id UUID REFERENCES fields(id) ON DELETE CASCADE,
              body JSONB NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        cur.execute("INSERT INTO schedules (field_id, body) VALUES (%s, %s)",
                    (field_id, json.dumps(events)))
    return {"saved": True, "count": len(events)}
