import os
import shutil
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


TEST_ROOT = Path(tempfile.mkdtemp(prefix="buildtrack-tests-"))
os.environ["BUILDTRACK_DATABASE_URL"] = f"sqlite:///{TEST_ROOT / 'test.db'}"
os.environ["BUILDTRACK_UPLOAD_DIR"] = str(TEST_ROOT / "uploads")

from app import models  # noqa: E402,F401
from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def reset_database() -> Generator[None, None, None]:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    shutil.rmtree(TEST_ROOT / "uploads", ignore_errors=True)
    yield
    Base.metadata.drop_all(bind=engine)
    shutil.rmtree(TEST_ROOT / "uploads", ignore_errors=True)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        bootstrap = test_client.post(
            "/auth/bootstrap",
            json={
                "email": "test-admin@buildtrack.local",
                "full_name": "Test Administrator",
                "password": "BuildTrack-test-password-2026",
            },
        )
        assert bootstrap.status_code == 201, bootstrap.text
        test_client.headers["Authorization"] = (
            f"Bearer {bootstrap.json()['access_token']}"
        )
        yield test_client
