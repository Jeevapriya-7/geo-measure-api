# Geospatial File Measurement API

A FastAPI service that accepts a **Shapefile (.zip)** or **KML**, extracts every feature, and returns
**area** (polygons) and **length** (lines), computed in a properly selected projected CRS.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload          # http://127.0.0.1:8000
```

Interactive docs: http://127.0.0.1:8000/docs  ·  Tests: `pytest`

| Env var | Default | Purpose |
|---|---|---|
| `GEO_DATA_DIR` | `./data` | Where uploads and results are stored |
| `GEO_MAX_UPLOAD_MB` | `50` | Max upload size |
| `GEO_MAX_UNZIPPED_MB` | `200` | Zip-bomb guard |

## API

### `POST /api/files/` — upload & process
```bash
curl -F "file=@survey.kml" http://127.0.0.1:8000/api/files/
```
```json
{ "id": "9f1c...", "filename": "survey.kml", "file_type": "kml", "feature_count": 4,
  "crs": "EPSG:4326", "status": "COMPLETED", "error": null, "created_at": "2026-10-11T08:00:00+00:00" }
```
Errors: `415` unsupported extension · `413` too large · `422` unreadable/invalid file (body contains `detail` and the stored `id`).

### `GET /api/files/{id}/` — file info
Returns the same object as above. `404` if unknown.

### `GET /api/files/{id}/measurements/` — per-feature measurements
Query params: `page`, `page_size` (≤1000), `include_geometry=false`, `geometry_type=Polygon`.
```json
{ "id": "9f1c...", "feature_count": 4, "page": 1, "page_size": 100,
  "features": [{
    "feature_id": 0, "layer": "Document", "geometry_type": "Polygon", "crs": "EPSG:4326",
    "properties": {"Name": "plot"}, "geometry": {"type": "Polygon", "coordinates": [[[77.7, 11.34], "..."]]},
    "measurement_status": "MEASURED",
    "measurements": {"area_sq_m": 1203845.2, "area_hectares": 120.38, "area_acres": 297.47,
                     "length_m": null, "length_km": null, "projected_crs": "EPSG:32643"},
    "warnings": [] }]}
```
`measurement_status`: `MEASURED` · `NOT_REQUIRED` (points) · `UNSUPPORTED` (e.g. GeometryCollection) · `SKIPPED` (empty/null geometry).

### `DELETE /api/files/{id}/` — remove an upload (bonus)

## Architecture

```
app/
  main.py              FastAPI app
  routers_files.py     HTTP layer: validation, upload streaming, responses
  schemas.py           Pydantic response models
  services/
    reader.py          zip extraction (safe) + GDAL reading via geopandas/pyogrio
    crs.py             CRS label, UTM zone selection, reprojection
    measure.py         per-geometry measurement rules
    processor.py       orchestrates read -> measure -> serialisable features
    storage.py         filesystem repository (data/<id>/...)
tests/                 pytest suite (KML, projected + geographic shapefiles, error paths)
```

**File-processing flow:** upload is streamed to disk (size-capped) → `reader` extracts shapefile parts from the zip
(zip-slip and size checks) or opens the KML → every layer is read into a GeoDataFrame → `processor` builds one record per
feature (id, layer, geometry type, geometry, CRS, properties) → results + metadata are persisted → file info returned.

**Measurement flow:** for each feature `measure_geometry` decides by geometry type: Polygon/MultiPolygon → area,
LineString/MultiLineString → length, Point/MultiPoint → nothing needed, anything else → `UNSUPPORTED` with a warning.
Invalid polygons are repaired with `make_valid` (and flagged); Z values are dropped.

**CRS handling:** the source CRS is read from the file (KML is always EPSG:4326; a Shapefile **must** have a `.prj`,
otherwise the file is rejected rather than guessing). Each geometry is normalised to WGS84, its representative point picks the
**UTM zone** (UPS near the poles), and the geometry is reprojected there before `.area` / `.length` are taken. The projected CRS
used is reported per feature. Degrees are never used for measurement.

## Design Decisions

| Decision | Why | Alternatives considered |
|---|---|---|
| FastAPI | Typed schemas, auto OpenAPI docs, light | Django + DRF (heavier; ORM not needed here) |
| Per-feature UTM zone | Accurate for local-scale surveys, simple, standard | One CRS per file (bad for files spanning zones); custom equal-area projection (best for area, but length is then less intuitive); geodesic `pyproj.Geod` (very accurate, but the brief asks for projected CRS — I used it in tests as an independent check) |
| Reject `.prj`-less shapefiles | Silent assumption of EPSG:4326 can produce wrong areas | Optional `assume_crs` parameter |
| Sync processing, `def` endpoints | Fast for typical files; FastAPI runs them in a threadpool | Celery/RQ job queue with `PROCESSING` status |
| JSON files on disk | Zero setup, clear repository seam | SQLite/PostGIS (better for querying and scale) |
| Paginated measurements, optional geometry | Large files give huge responses | Streaming NDJSON |

Known limitations: features spanning more than one UTM zone get a warning (results approximate); multi-GB files will need
async processing; Shapefile zips with several `.shp` are merged as separate layers.

## Learning & Future Scope

**Learned:** GDAL's KML driver exposes each `Folder` as a layer; reprojection with `pyproj` needs `always_xy=True` to avoid
axis-order bugs; geodesic area is a handy independent oracle for testing projected results; zip uploads need explicit
zip-slip/zip-bomb defences.

**Next:**
- Background jobs (Celery/RQ) with `PROCESSING` status and progress
- PostGIS/SQLite storage, auth, rate limits
- KMZ and GeoJSON support
- Local units (cent, guntha, ground) in the response
- Optional geodesic mode and `assume_crs` for `.prj`-less files
- Dockerfile + CI (GitHub Actions)
