CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS farms (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_id text NOT NULL,
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fields (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  farm_id uuid NOT NULL REFERENCES farms(id) ON DELETE CASCADE,
  name text NOT NULL,
  crop text,
  sowing_date date,
  soil text,
  kc_profile jsonb,
  boundary geometry(polygon, 4326) NOT NULL,
  area_ha numeric GENERATED ALWAYS AS (ST_Area(ST_Transform(boundary, 3857))/10000.0) STORED,
  centroid geometry(point, 4326) GENERATED ALWAYS AS (ST_Centroid(boundary)) STORED,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS schedules (
  field_id uuid NOT NULL REFERENCES fields(id) ON DELETE CASCADE,
  body jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
