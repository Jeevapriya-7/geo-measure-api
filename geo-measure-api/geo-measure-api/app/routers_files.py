import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.responses import JSONResponse

from app.config import ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES
from app.schemas import FileInfo, MeasurementsResponse, Status
from app.services.errors import GeoProcessingError
from app.services.processor import process_file
from app.services.storage import FileRepository

router = APIRouter(prefix="/api/files", tags=["files"])
repo = FileRepository()


def _load_meta_or_404(file_id: str) -> dict:
    try:
        meta = repo.get_meta(file_id)
    except KeyError:
        meta = None
    if meta is None:
        raise HTTPException(status_code=404, detail="File not found.")
    return meta


@router.post("/", response_model=FileInfo, status_code=201)
def upload_file(file: UploadFile = File(...)):
    """Upload a .kml or a .zip (Shapefile); it is processed synchronously."""
    filename = Path(file.filename or "").name
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, detail="Unsupported file type. Upload a .kml or a .zip containing a Shapefile.")
    file_type = "kml" if ext == ".kml" else "shapefile"

    file_id = uuid.uuid4().hex
    folder = repo.create(file_id)
    saved = folder / f"original{ext}"

    size = 0
    with open(saved, "wb") as out:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                repo.delete(file_id)
                raise HTTPException(413, detail="File too large.")
            out.write(chunk)

    meta = {
        "id": file_id,
        "filename": filename,
        "file_type": file_type,
        "feature_count": 0,
        "crs": None,
        "status": Status.FAILED.value,
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        features, file_crs = process_file(saved, file_type)
    except GeoProcessingError as exc:
        meta["error"] = str(exc)
        repo.save_meta(file_id, meta)
        return JSONResponse(status_code=422, content={"detail": str(exc), "id": file_id, "status": "FAILED"})

    meta.update(feature_count=len(features), crs=file_crs, status=Status.COMPLETED.value)
    repo.save_features(file_id, features)
    repo.save_meta(file_id, meta)
    return meta


@router.get("/{file_id}/", response_model=FileInfo)
def get_file(file_id: str):
    return _load_meta_or_404(file_id)


@router.get("/{file_id}/measurements/", response_model=MeasurementsResponse)
def get_measurements(
    file_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    include_geometry: bool = Query(True, description="Set false for lightweight responses."),
    geometry_type: str | None = Query(None, description="Filter, e.g. Polygon"),
):
    meta = _load_meta_or_404(file_id)
    if meta["status"] != Status.COMPLETED.value:
        raise HTTPException(409, detail="File processing did not complete.")

    features = repo.get_features(file_id)
    if geometry_type:
        features = [f for f in features if f["geometry_type"] == geometry_type]
    total = len(features)
    start = (page - 1) * page_size
    chunk = features[start:start + page_size]
    if not include_geometry:
        chunk = [{**f, "geometry": None} for f in chunk]
    return {"id": file_id, "feature_count": total, "page": page, "page_size": page_size, "features": chunk}


@router.delete("/{file_id}/", status_code=204)
def delete_file(file_id: str):
    try:
        deleted = repo.delete(file_id)
    except KeyError:
        deleted = False
    if not deleted:
        raise HTTPException(404, detail="File not found.")
