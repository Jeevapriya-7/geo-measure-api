import os
import tempfile

# Must be set before the app is imported (repository reads it at import time).
os.environ["GEO_DATA_DIR"] = tempfile.mkdtemp(prefix="geo-test-")

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    return TestClient(app)
