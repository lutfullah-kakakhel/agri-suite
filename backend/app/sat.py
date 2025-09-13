from __future__ import annotations
from datetime import datetime, timedelta
from typing import Optional, Tuple
import json, math
import numpy as np
import rioxarray as rxr
import rasterio
from shapely.geometry import shape, Point, mapping
from pystac_client import Client

EARTH_SEARCH = "https://earth-search.aws.element84.com/v1"   # public STAC
COLLECTION = "sentinel-2-l2a"

# Cloud classes in SCL band we want to mask out
# (3: cloud shadow, 8: medium/high probability clouds, 9: high-prob clouds, 10: cirrus)
SCL_MASK = {3, 8, 9, 10}

def _tiny_buffer_from_centroid(lat: float, lon: float, meters: float = 40) -> dict:
    """Make a ~40m radius buffer around a centroid (WGS84).
       Very small to keep Pi memory use tiny."""
    # quick and dirty meters -> degrees at given latitude
    dlat = meters / 111_320.0
    dlon = meters / (111_320.0 * math.cos(math.radians(lat)) + 1e-9)
    return {
        "type":"Polygon",
        "coordinates":[[
            (lon-dlon, lat-dlat),
            (lon+dlon, lat-dlat),
            (lon+dlon, lat+dlat),
            (lon-dlon, lat+dlat),
            (lon-dlon, lat-dlat)
        ]]
    }

def select_item(field_geom_geojson: dict, days_back: int = 30, max_cloud_pct: float = 40.0):
    client = Client.open(EARTH_SEARCH)
    end = datetime.utcnow().date()
    start = end - timedelta(days=days_back)
    search = client.search(
        collections=[COLLECTION],
        intersects=field_geom_geojson,
        datetime=f"{start.isoformat()}/{end.isoformat()}",
        query={"eo:cloud_cover":{"lt": max_cloud_pct}},
        sort=[{"field":"properties.datetime","direction":"desc"}],
        limit=5,
    )
    items = list(search.get_items())
    return items[0] if items else None

def compute_indices(item, geom_geojson: dict) -> Tuple[Optional[float], Optional[float], float, str]:
    """Return (ndvi_mean, ndwi_mean, cloud_cover, item_id) clipped to the geometry."""
    # asset keys for L2A COGs on Earth Search
    b04 = item.assets.get("B04").href  # red
    b08 = item.assets.get("B08").href  # nir
    b11 = item.assets.get("B11").href  # swir
    scl = item.assets.get("SCL").href  # scene classification

    geom = shape(geom_geojson)

    # Open each band lazily, clip to small AOI to keep memory low
    with rasterio.Env(AWS_NO_SIGN_REQUEST="YES"):
        r_b04 = rxr.open_rasterio(b04, masked=True).rio.clip([geom], all_touched=True, drop=True)
        r_b08 = rxr.open_rasterio(b08, masked=True).rio.clip([geom], all_touched=True, drop=True)
        r_b11 = rxr.open_rasterio(b11, masked=True).rio.clip([geom], all_touched=True, drop=True)
        r_scl = rxr.open_rasterio(scl, masked=True).rio.clip([geom], all_touched=True, drop=True)

    # to 2D arrays
    red = np.squeeze(r_b04.data).astype("float32")
    nir = np.squeeze(r_b08.data).astype("float32")
    swir = np.squeeze(r_b11.data).astype("float32")
    scl_arr = np.squeeze(r_scl.data)

    # mask clouds/shadows
    cloud_mask = np.isin(scl_arr, list(SCL_MASK))
    red[cloud_mask] = np.nan
    nir[cloud_mask] = np.nan
    swir[cloud_mask] = np.nan

    # NDVI = (NIR - RED) / (NIR + RED)
    ndvi = (nir - red) / (nir + red + 1e-6)
    # NDWI (actually NDMI with SWIR) = (NIR - SWIR) / (NIR + SWIR)
    ndwi = (nir - swir) / (nir + swir + 1e-6)

    def _nanmean(a):
        v = np.nanmean(a)
        return float(v) if np.isfinite(v) else None

    ndvi_mean = _nanmean(ndvi)
    ndwi_mean = _nanmean(ndwi)
    cloud_pct = float(item.properties.get("eo:cloud_cover", np.nan))
    return ndvi_mean, ndwi_mean, cloud_pct, item.id
