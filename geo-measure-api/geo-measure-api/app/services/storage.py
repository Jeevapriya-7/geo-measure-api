"""Tiny filesystem-backed repository (one directory per upload).

Layout:  data/<id>/original.<ext> | meta.json | features.json
Swap this class for a DB-backed implementation without touching the API layer.
"""
import json
import shutil
from pathlib import Path

from app.config import DATA_DIR


class FileRepository:
    def __init__(self, root: Path | None = None):
        self.root = root or DATA_DIR
        self.root.mkdir(parents=True, exist_ok=True)

    def dir_for(self, file_id: str) -> Path:
        d = (self.root / file_id).resolve()
        if self.root not in d.parents:  # id comes from the URL
            raise KeyError(file_id)
        return d

    def create(self, file_id: str) -> Path:
        d = self.dir_for(file_id)
        d.mkdir(parents=True, exist_ok=False)
        return d

    def save_meta(self, file_id: str, meta: dict) -> None:
        (self.dir_for(file_id) / "meta.json").write_text(json.dumps(meta))

    def save_features(self, file_id: str, features: list[dict]) -> None:
        (self.dir_for(file_id) / "features.json").write_text(json.dumps(features))

    def get_meta(self, file_id: str) -> dict | None:
        p = self.dir_for(file_id) / "meta.json"
        return json.loads(p.read_text()) if p.exists() else None

    def get_features(self, file_id: str) -> list[dict]:
        p = self.dir_for(file_id) / "features.json"
        return json.loads(p.read_text()) if p.exists() else []

    def delete(self, file_id: str) -> bool:
        d = self.dir_for(file_id)
        if not d.exists():
            return False
        shutil.rmtree(d)
        return True
