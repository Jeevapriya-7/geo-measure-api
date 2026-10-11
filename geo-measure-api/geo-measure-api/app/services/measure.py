"""Measurement logic for individual geometries."""
from shapely import force_2d, make_valid
from shapely.geometry.base import BaseGeometry
from pyproj import CRS

from app.schemas import Measurement
from .crs import to_projected

SQM_PER_HECTARE = 10_000
SQM_PER_ACRE = 4046.8564224

AREA_TYPES = {"Polygon", "MultiPolygon"}
LENGTH_TYPES = {"LineString", "MultiLineString", "LinearRing"}
POINT_TYPES = {"Point", "MultiPoint"}


def measure_geometry(geom: BaseGeometry | None, src_crs: CRS):
    """Return (status, Measurement | None, warnings)."""
    if geom is None or geom.is_empty:
        return "SKIPPED", None, ["Feature has no geometry."]

    gtype = geom.geom_type
    if gtype in POINT_TYPES:
        return "NOT_REQUIRED", None, []
    if gtype not in AREA_TYPES | LENGTH_TYPES:
        return "UNSUPPORTED", None, [f"Measurement not supported for geometry type '{gtype}'."]

    warnings: list[str] = []
    geom = force_2d(geom)  # ignore Z; we measure on the ground plane
    if gtype in AREA_TYPES and not geom.is_valid:
        geom = make_valid(geom)
        warnings.append("Invalid polygon geometry was repaired before measuring.")

    projected, proj_crs, crs_warnings = to_projected(geom, src_crs)
    warnings += crs_warnings
    proj_label = f"EPSG:{proj_crs.to_epsg()}"

    if gtype in AREA_TYPES:
        area = projected.area
        return "MEASURED", Measurement(
            area_sq_m=round(area, 3),
            area_hectares=round(area / SQM_PER_HECTARE, 6),
            area_acres=round(area / SQM_PER_ACRE, 6),
            projected_crs=proj_label,
        ), warnings

    length = projected.length
    return "MEASURED", Measurement(
        length_m=round(length, 3),
        length_km=round(length / 1000, 6),
        projected_crs=proj_label,
    ), warnings
