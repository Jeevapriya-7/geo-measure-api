"""CRS helpers: pick a projected CRS suited to a geometry and reproject into it."""
from functools import lru_cache

from pyproj import CRS, Transformer
from shapely.geometry.base import BaseGeometry
import numpy as np
import shapely

WGS84 = CRS.from_epsg(4326)


def crs_label(crs: CRS | None) -> str | None:
    """Human friendly CRS id, e.g. 'EPSG:4326' (falls back to the CRS name)."""
    if crs is None:
        return None
    epsg = crs.to_epsg()
    return f"EPSG:{epsg}" if epsg else crs.name


@lru_cache(maxsize=256)
def _transformer(src_wkt: str, dst_wkt: str) -> Transformer:
    return Transformer.from_crs(CRS.from_wkt(src_wkt), CRS.from_wkt(dst_wkt), always_xy=True)


def reproject(geom: BaseGeometry, src: CRS, dst: CRS) -> BaseGeometry:
    if src == dst:
        return geom
    t = _transformer(src.to_wkt(), dst.to_wkt())
    return shapely.transform(
        geom, lambda c: np.column_stack(t.transform(c[:, 0], c[:, 1])), include_z=False
    )


def utm_crs_for(lon: float, lat: float) -> CRS:
    """Pick the UTM zone containing (lon, lat); UPS near the poles."""
    if lat >= 84:
        return CRS.from_epsg(32661)  # UPS North
    if lat <= -80:
        return CRS.from_epsg(32761)  # UPS South
    zone = int((lon + 180) // 6) % 60 + 1
    return CRS.from_epsg((32600 if lat >= 0 else 32700) + zone)


def to_projected(geom: BaseGeometry, src: CRS) -> tuple[BaseGeometry, CRS, list[str]]:
    """Reproject `geom` (in `src`) to the UTM zone of its centre.

    Returns (projected geometry, projected CRS, warnings).
    The geometry is first normalised to WGS84 so the zone can be chosen from
    lon/lat regardless of the source CRS (projected sources work too).
    """
    warnings: list[str] = []
    geographic = reproject(geom, src, WGS84)
    minx, _, maxx, _ = geographic.bounds
    if maxx - minx > 6:
        warnings.append(
            "Feature spans more than one UTM zone (>6 degrees of longitude); "
            "results are approximate."
        )
    c = geographic.representative_point() if not geographic.is_empty else None
    centre_lon, centre_lat = (c.x, c.y) if c else (0.0, 0.0)
    projected_crs = utm_crs_for(centre_lon, centre_lat)
    return reproject(geographic, WGS84, projected_crs), projected_crs, warnings
