from pydantic import BaseModel, Field as PField

class FieldCreate(BaseModel):
    name: str
    crop: str
    centroid_lat: float = PField(ge=-90, le=90)
    centroid_lon: float = PField(ge=-180, le=180)
    polygon_geojson: str | None = None
    last_irrigation_ts: int | None = None

class FieldOut(BaseModel):
    id: int
    name: str
    crop: str
    centroid_lat: float
    centroid_lon: float
    polygon_geojson: str | None
    last_irrigation_ts: int | None
    class Config:
        from_attributes = True
