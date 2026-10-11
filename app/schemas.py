from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class Status(str, Enum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class FileInfo(BaseModel):
    id: str
    filename: str
    file_type: str
    feature_count: int
    crs: Optional[str]
    status: Status
    error: Optional[str] = None
    created_at: str


class Measurement(BaseModel):
    area_sq_m: Optional[float] = None
    area_hectares: Optional[float] = None
    area_acres: Optional[float] = None
    length_m: Optional[float] = None
    length_km: Optional[float] = None
    projected_crs: Optional[str] = None


class FeatureMeasurement(BaseModel):
    feature_id: int
    layer: Optional[str]
    geometry_type: Optional[str]
    crs: Optional[str]
    properties: dict[str, Any]
    geometry: Optional[dict[str, Any]]
    measurement_status: str  # MEASURED | NOT_REQUIRED | UNSUPPORTED | SKIPPED
    measurements: Optional[Measurement] = None
    warnings: list[str] = []


class MeasurementsResponse(BaseModel):
    id: str
    feature_count: int
    page: int
    page_size: int
    features: list[FeatureMeasurement]
