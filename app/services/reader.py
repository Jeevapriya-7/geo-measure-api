"""Reading Shapefile (.zip) and KML uploads into GeoDataFrames."""
import zipfile
from pathlib import Path

import geopandas as gpd
import pyogrio

from app.config import MAX_UNZIPPED_BYTES
from .errors import GeoProcessingError

SHAPEFILE_PARTS = {".shp", ".shx", ".dbf", ".prj", ".cpg"}


def safe_extract_shapefile_zip(zip_path: Path, dest: Path) -> list[Path]:
    """Extract only shapefile component files, guarding against zip-slip and zip bombs."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as exc:
        raise GeoProcessingError("Uploaded file is not a valid zip archive.") from exc

    with zf:
        infos = [
            i for i in zf.infolist()
            if not i.is_dir()
            and "__MACOSX" not in i.filename
            and Path(i.filename).suffix.lower() in SHAPEFILE_PARTS
        ]
        if sum(i.file_size for i in infos) > MAX_UNZIPPED_BYTES:
            raise GeoProcessingError("Zip contents exceed the maximum allowed unzipped size.")

        dest = dest.resolve()
        for info in infos:
            target = (dest / info.filename).resolve()
            if dest not in target.parents:
                raise GeoProcessingError("Zip contains an unsafe file path.")
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                out.write(src.read())

    shp_files = sorted(dest.rglob("*.shp"))
    if not shp_files:
        raise GeoProcessingError("No .shp file found inside the zip archive.")
    return shp_files


def read_layers(path: Path, file_type: str, workdir: Path) -> list[tuple[str, gpd.GeoDataFrame]]:
    """Return [(layer_name, GeoDataFrame)] for every layer in the upload."""
    sources: list[Path] = (
        safe_extract_shapefile_zip(path, workdir) if file_type == "shapefile" else [path]
    )
    layers: list[tuple[str, gpd.GeoDataFrame]] = []
    for src in sources:
        try:
            if file_type == "kml":
                # A KML 'Folder' becomes a layer in GDAL; read all of them.
                names = [name for name, _ in pyogrio.list_layers(src)]
            else:
                names = [None]
            for name in names:
                gdf = gpd.read_file(src, layer=name, engine="pyogrio")
                label = name or src.stem
                if file_type == "shapefile" and gdf.crs is None:
                    raise GeoProcessingError(
                        f"'{src.name}' has no CRS (missing .prj file); cannot measure safely."
                    )
                layers.append((label, gdf))
        except GeoProcessingError:
            raise
        except Exception as exc:  # corrupt/unsupported data from GDAL
            raise GeoProcessingError(f"Could not read geospatial data: {exc}") from exc

    if not layers:
        raise GeoProcessingError("No layers found in file.")
    return layers
