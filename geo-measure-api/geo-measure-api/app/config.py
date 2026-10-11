from pathlib import Path
import os

DATA_DIR = Path(os.getenv("GEO_DATA_DIR", "data")).resolve()
MAX_UPLOAD_BYTES = int(os.getenv("GEO_MAX_UPLOAD_MB", "50")) * 1024 * 1024
MAX_UNZIPPED_BYTES = int(os.getenv("GEO_MAX_UNZIPPED_MB", "200")) * 1024 * 1024
ALLOWED_EXTENSIONS = {".zip", ".kml"}
