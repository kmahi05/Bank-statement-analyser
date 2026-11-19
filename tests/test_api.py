"""The HTTP endpoint is optional, so skip these tests if FastAPI isn't installed."""
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("multipart")
from fastapi.testclient import TestClient  # noqa: E402

from api import app  # noqa: E402

client = TestClient(app)


def test_upload_returns_report():
    data = (Path(__file__).parent.parent / "data" / "statement_A.csv").read_bytes()
    r = client.post("/analyze", files={"file": ("statement_A.csv", data, "text/csv")})
    assert r.status_code == 200
    assert len(r.json()["bounces"]) == 3


def test_bad_header_is_400():
    r = client.post("/analyze", files={"file": ("x.csv", b"foo,bar\n", "text/csv")})
    assert r.status_code == 400
