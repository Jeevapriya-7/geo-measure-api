"""Turns an uploaded file into FileInfo + a list of measured features."""
import json
import tempfile
from pathlib import Path

from shapely.geometry import mapping

from app.schemas import FeatureMeasurement
from .crs import crs_label
from .measure import measure_geometry
from .reader import read_layers


def process_file(path: Path, file_type: str) -> tuple[list[dict], str | None]:
    """Read the file and measure every feature.

    Returns (features as dicts, file-level CRS label). Raises GeoProcessingError.
    """
    with tempfile.TemporaryDirectory() as tmp:
        layers = read_layers(path, file_type, Path(tmp))

    features: list[dict] = []
    crs_labels: set[str] = set()
    feature_id = 0

    for layer_name, gdf in layers:
        crs = gdf.crs
        label = crs_label(crs)
        crs_labels.add(label)
        # to_json() yields JSON-safe properties (NaN -> null, timestamps -> str)
        props_list = [
            f["properties"] for f in json.loads(gdf.reset_index(drop=True).to_json())["features"]
        ]
        for geom, props in zip(gdf.geometry, props_list):
            status, measurement, warnings = measure_geometry(geom, crs)
            features.append(
                FeatureMeasurement(
                    feature_id=feature_id,
                    layer=layer_name,
                    geometry_type=geom.geom_type if geom is not None else None,
                    crs=label,
                    properties=props,
                    geometry=mapping(geom) if geom is not None and not geom.is_empty else None,
                    measurement_status=status,
                    measurements=measurement,
                    warnings=warnings,
                ).model_dump(mode="json")
            )
            feature_id += 1

    file_crs = crs_labels.pop() if len(crs_labels) == 1 else "MIXED"
    return features, file_crs
