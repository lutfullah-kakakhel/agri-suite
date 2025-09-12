from sqlalchemy import Column, Integer, String, Float, Text, Date, ForeignKey
from .db import Base

class Field(Base):
    __tablename__ = "fields"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    crop = Column(String(80), nullable=False)
    centroid_lat = Column(Float, nullable=False)
    centroid_lon = Column(Float, nullable=False)
    polygon_geojson = Column(Text, nullable=True)
    last_irrigation_ts = Column(Integer, nullable=True)  # unix seconds

class S2Stat(Base):
    __tablename__ = "s2_stats"

    id = Column(Integer, primary_key=True)
    field_id = Column(Integer, ForeignKey("fields.id"), index=True, nullable=False)
    scene_date = Column(Date, index=True, nullable=False)
    collection = Column(String(40), default="sentinel-2-l2a")
    ndvi_mean = Column(Float, nullable=True)
    ndwi_mean = Column(Float, nullable=True)
    cloud_pct = Column(Float, nullable=True)
    asset_id = Column(String(200), nullable=True)
